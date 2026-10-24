"""Reads of every newsletter get past the API's row cap (max_rows in config.toml)."""

import argparse
import io
import tempfile
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar
from unittest.mock import patch

import cli.find_unprocessed_emails as find_cli
import cli.process_llm_metadata as llm_cli
import cli.reprocess_newsletters_privacy as privacy_cli
from analytics.io import snapshot_refresh
from analytics.snapshot import Snapshot
from shared.db import API_ROW_CAP
from tests.db_integration.local_supabase import LocalSupabaseTestCase
from tests.fixtures.newsletter_factory import insert_newsletter, insert_source

#: More newsletters than one API response can hold.
NEWSLETTER_COUNT = API_ROW_CAP + 50
#: The newest rows were created later, for the incremental snapshot refresh.
LATER_ROWS = 50


class ManyNewslettersTestCase(LocalSupabaseTestCase):
    """NEWSLETTER_COUNT newsletters from one source, the newest LATER_ROWS created later."""

    source_id: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.source_id = insert_source(cls.db, name="Ward 11 Office", ward_number=11)[
            "id"
        ]
        cls.run_sql(
            """
            INSERT INTO newsletters
                (source_id, subject, plain_text, received_date, email_uid, created_at)
            SELECT %(source)s, 'Issue ' || n, 'Text of issue ' || n,
                   timestamptz '2026-01-01' + n * interval '1 hour', 'uid-' || n,
                   CASE WHEN n > %(earlier)s THEN timestamptz '2026-06-01'
                        ELSE timestamptz '2026-01-01' END
            FROM generate_series(1, %(count)s) AS n
            """,
            {
                "source": cls.source_id,
                "earlier": NEWSLETTER_COUNT - LATER_ROWS,
                "count": NEWSLETTER_COUNT,
            },
        )


class TestRowCap(ManyNewslettersTestCase):
    def test_the_api_caps_an_unpaged_read(self) -> None:
        self.assertEqual(len(self.rows("newsletters", "id")), API_ROW_CAP)

    def test_llm_metadata_selects_every_matching_newsletter(self) -> None:
        for args, expected in (
            (["--missing-metadata"], NEWSLETTER_COUNT),
            (["--all"], NEWSLETTER_COUNT),
            (["--all", "--skip", "10"], NEWSLETTER_COUNT - 10),
            (["--source-id", str(self.source_id)], NEWSLETTER_COUNT),
            (["--latest", "5", "--skip", str(API_ROW_CAP + 10)], 5),
            (["--latest", str(API_ROW_CAP + 20)], API_ROW_CAP + 20),
        ):
            with self.subTest(args=args):
                newsletters = llm_cli.fetch_newsletters(
                    self.db, llm_cli.build_parser().parse_args(args)
                )
                self.assertEqual(len(newsletters), expected)
                self.assertEqual(len({row["id"] for row in newsletters}), expected)

    def test_privacy_reprocessing_reads_every_newsletter(self) -> None:
        newsletters = privacy_cli.fetch_all_newsletters(self.db)

        self.assertEqual(len({row["id"] for row in newsletters}), NEWSLETTER_COUNT)

    def test_stored_email_uids_are_all_read(self) -> None:
        self.assertEqual(
            len(find_cli.fetch_stored_email_uids(self.db)), NEWSLETTER_COUNT
        )


class TestSnapshotRefresh(ManyNewslettersTestCase):
    """The analytics snapshot, built in full and then refreshed incrementally."""

    def setUp(self) -> None:
        self.directory = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.enterContext(patch.object(snapshot_refresh, "FETCH_PAUSE_SECONDS", 0))

    def load(self, full_refresh: bool) -> tuple[Snapshot, str]:
        """Run the analytics CLI's snapshot step; returns the snapshot and its output."""
        args = argparse.Namespace(
            snapshot_dir=self.directory, full_refresh=full_refresh, offline=False
        )
        output = io.StringIO()
        with redirect_stdout(output):
            snapshot = snapshot_refresh.load_or_refresh_snapshot(
                args, datetime.now(UTC), lambda: self.db
            )
        return snapshot, output.getvalue()

    def test_full_then_incremental_refresh_reads_each_row_once(self) -> None:
        full, _ = self.load(full_refresh=True)
        self.assertEqual(len({n.id for n in full.newsletters}), NEWSLETTER_COUNT)
        self.assertEqual(full.fetched_through, datetime(2026, 6, 1, tzinfo=UTC))

        added = insert_newsletter(self.db, self.source_id)
        refreshed, output = self.load(full_refresh=False)

        # Only rows created since the cursor (less a day's overlap) are read again.
        self.assertIn(f"Fetched {LATER_ROWS + 1} recent newsletter rows", output)
        ids = [n.id for n in refreshed.newsletters]
        self.assertEqual(len(ids), NEWSLETTER_COUNT + 1)
        self.assertEqual(len(set(ids)), len(ids))
        self.assertIn(added["id"], ids)
