"""Unit tests for utils/compute_analytics.py orchestration (no database)."""

import argparse
import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any, ClassVar
from unittest.mock import MagicMock, patch

from analytics.facts import MIN_EXTRACTED_WORDS
from analytics.records import NewsletterRecord, SourceRecord
from analytics.snapshot import Snapshot
from utils.analytics_snapshot import SnapshotNotFoundError, load_snapshot, save_snapshot
from utils.compute_analytics import (
    BOILERPLATE_MIN_SOURCE_NEWSLETTERS,
    FETCH_PAGE_SIZE,
    FETCH_PAUSE_SECONDS,
    INCREMENTAL_OVERLAP,
    LENS_MIN_MENTIONS,
    MATCH_LENSES_ON_CLEANED_TEXT,
    NEWSLETTER_COLUMNS,
    analyze_archive,
    build_full_snapshot,
    compute_outputs,
    compute_site_outputs,
    fetch_rows,
    load_or_refresh_snapshot,
    refresh_snapshot,
    write_outputs,
)


def make_newsletter(
    newsletter_id: str, day: date, source_id: int, text: str
) -> NewsletterRecord:
    return NewsletterRecord(
        id=newsletter_id,
        received_date=day,
        source_id=source_id,
        subject="Update",
        plain_text=text,
    )


class TestComputeOutputs(unittest.TestCase):
    def test_produces_every_output_file(self) -> None:
        sources = [
            SourceRecord(1, "Ada Alder", "1", "alderman"),
            SourceRecord(2, "Bo Alder", "2", "alderman"),
        ]
        newsletters = [
            make_newsletter("a", date(2026, 8, 3), 1, "Protected bike lanes"),
            make_newsletter("b", date(2026, 9, 3), 2, "Protected bike lanes"),
            # An October newsletter shows the snapshot holds all of September.
            make_newsletter("c", date(2026, 10, 2), 1, "Leaf pickup"),
        ]
        outputs = compute_outputs(
            analyze_archive(sources, newsletters, 2, datetime(2026, 10, 11))
        )

        self.assertEqual(
            set(outputs),
            {
                "metadata",
                "newsletters",
                "sources",
                "terms",
                "distinctive",
                "rising",
                "lenses",
            },
        )
        self.assertEqual(outputs["metadata"]["newsletter_count"], 3)
        self.assertEqual(len(outputs["newsletters"]["newsletters"]), 3)
        self.assertIn("bike lanes", outputs["terms"]["terms"])
        self.assertEqual(outputs["terms"]["min_newsletters"], 2)
        self.assertEqual(outputs["rising"]["latest_month"], "2026-09")

    def test_term_metrics_exclude_text_a_source_repeats_in_every_issue(self) -> None:
        sources = [SourceRecord(1, "Ada Alder", "1", "alderman")]
        footer = "Ada Alder | 1 Main St | Unsubscribe | Update Profile | Constant Contact Data Notice"
        newsletters = [
            make_newsletter(
                str(index),
                date(2026, 9, 1 + index),
                1,
                f"Zoning item {index}. {footer}",
            )
            for index in range(BOILERPLATE_MIN_SOURCE_NEWSLETTERS)
        ]
        outputs = compute_outputs(
            analyze_archive(sources, newsletters, 1, datetime(2026, 10, 11))
        )

        self.assertNotIn("data notice", outputs["terms"]["terms"])
        self.assertIn("zoning", outputs["terms"]["terms"])
        # Facts still describe the newsletter as received.
        fact_words = outputs["newsletters"]["newsletters"][0]["words"]
        self.assertEqual(fact_words, len(newsletters[0].plain_text.split()))

    def test_flags_each_newsletter_with_the_lenses_it_mentions(self) -> None:
        sources = [SourceRecord(1, "Ada Alder", "1", "alderman")]
        filler = "word " * MIN_EXTRACTED_WORDS
        mention = " ".join(["New speed humps."] * LENS_MIN_MENTIONS)
        newsletters = [
            make_newsletter("calming", date(2026, 9, 1), 1, f"{mention} {filler}"),
            make_newsletter("passing", date(2026, 9, 2), 1, f"A speed hump. {filler}"),
            # Image-only issue: too little text to say what it mentions.
            make_newsletter("image", date(2026, 9, 3), 1, mention),
        ]
        outputs = compute_outputs(
            analyze_archive(sources, newsletters, 1, datetime(2026, 10, 11))
        )

        lenses_by_id = {
            fact["id"]: fact["lenses"] for fact in outputs["newsletters"]["newsletters"]
        }
        self.assertIn("street_safety", lenses_by_id["calming"])
        self.assertEqual(lenses_by_id["passing"], [])
        self.assertEqual(lenses_by_id["image"], [])
        self.assertNotIn("topics", outputs["newsletters"]["newsletters"][0])

        summary = outputs["lenses"]
        self.assertEqual(summary["readable_newsletters"], 2)
        self.assertEqual(summary["min_mentions"], LENS_MIN_MENTIONS)
        street_safety = next(
            lens for lens in summary["lenses"] if lens["id"] == "street_safety"
        )
        self.assertEqual(street_safety["newsletters"], 1)

    @unittest.skipUnless(MATCH_LENSES_ON_CLEANED_TEXT, "lenses match raw text")
    def test_lenses_ignore_a_standing_block_repeated_in_every_issue(self) -> None:
        sources = [SourceRecord(1, "Ada Alder", "1", "alderman")]
        standing_block = (
            "Immigration resources: know your rights workshops for immigrant "
            "neighbors every week at the ward office on Main Street"
        )
        newsletters = [
            make_newsletter(
                str(index),
                date(2026, 9, 1 + index),
                1,
                f"Item {index} " + "word " * MIN_EXTRACTED_WORDS + standing_block,
            )
            for index in range(BOILERPLATE_MIN_SOURCE_NEWSLETTERS)
        ]
        outputs = compute_outputs(
            analyze_archive(sources, newsletters, 1, datetime(2026, 10, 11))
        )

        self.assertEqual(outputs["lenses"]["text"], "cleaned")
        for fact in outputs["newsletters"]["newsletters"]:
            self.assertNotIn("immigration", fact["lenses"])

    def test_handles_dataset_without_complete_month(self) -> None:
        sources = [SourceRecord(1, "Ada Alder", "1", "alderman")]
        newsletters = [make_newsletter("a", date(2026, 10, 3), 1, "Bike lanes")]
        outputs = compute_outputs(
            analyze_archive(sources, newsletters, 1, datetime(2026, 10, 11))
        )
        self.assertIsNone(outputs["rising"]["latest_month"])
        self.assertEqual(outputs["rising"]["terms"], [])


class TestComputeSiteOutputs(unittest.TestCase):
    sources: ClassVar = [
        SourceRecord(1, "Ada Alder", "1", "alderman"),
        SourceRecord(2, "Bo Alder", "2", "alderman"),
        SourceRecord(3, "Cy Alder", "3", "alderman"),
        SourceRecord(4, "Transit agency", None, "agency"),
    ]
    filler = "word " * MIN_EXTRACTED_WORDS
    mention = " ".join(["New speed humps."] * LENS_MIN_MENTIONS)

    def test_summarizes_wards_and_broad_complete_months(self) -> None:
        newsletters = [
            make_newsletter("a", date(2026, 8, 3), 1, self.filler),
            make_newsletter("b", date(2026, 9, 3), 1, f"{self.mention} {self.filler}"),
            make_newsletter("c", date(2026, 9, 4), 2, f"{self.mention} {self.filler}"),
            # The current month is incomplete, so it gets no report yet.
            make_newsletter("d", date(2026, 10, 2), 1, self.filler),
            make_newsletter("e", date(2026, 10, 2), 2, self.filler),
        ]
        with patch("utils.compute_analytics.REPORT_MIN_SENDING_WARDS", 2):
            outputs = compute_site_outputs(
                analyze_archive(self.sources, newsletters, 1, datetime(2026, 10, 11))
            )

        glance = outputs["ward-glance"]
        self.assertEqual(glance["data_through"], "2026-10-02")
        self.assertEqual(glance["latest_month"], "2026-09")
        self.assertEqual(set(glance["wards"]), {"1", "2"})
        self.assertEqual(
            glance["topics"]["street_safety"], "Street safety & traffic calming"
        )
        ward_one_topics = glance["wards"]["1"]["topics"]
        self.assertIn(
            {"id": "street_safety", "newsletters": 1, "city_wards": 2}, ward_one_topics
        )

        reports = outputs["monthly-reports"]["reports"]
        self.assertEqual([report["month"] for report in reports], ["2026-09"])
        self.assertEqual(reports[0]["sending_wards"], ["1", "2"])
        street_safety = next(
            topic for topic in reports[0]["topics"] if topic["id"] == "street_safety"
        )
        self.assertEqual(street_safety["wards"], 2)

    def test_without_a_complete_month_both_summaries_are_empty(self) -> None:
        newsletters = [make_newsletter("a", date(2026, 10, 3), 1, self.filler)]
        outputs = compute_site_outputs(
            analyze_archive(self.sources, newsletters, 1, datetime(2026, 10, 11))
        )
        self.assertEqual(outputs["ward-glance"]["wards"], {})
        self.assertIsNone(outputs["ward-glance"]["latest_month"])
        self.assertEqual(outputs["monthly-reports"]["reports"], [])

    def test_a_stale_snapshot_leaves_its_newest_month_out(self) -> None:
        # Refreshed mid-September but computed in October: September is partial.
        newsletters = [
            make_newsletter("a", date(2026, 8, 3), 1, self.filler),
            make_newsletter("b", date(2026, 8, 4), 2, self.filler),
            make_newsletter("c", date(2026, 9, 14), 1, self.filler),
            make_newsletter("d", date(2026, 9, 15), 2, self.filler),
        ]
        with patch("utils.compute_analytics.REPORT_MIN_SENDING_WARDS", 2):
            outputs = compute_site_outputs(
                analyze_archive(self.sources, newsletters, 1, datetime(2026, 10, 11))
            )
        self.assertEqual(outputs["ward-glance"]["latest_month"], "2026-08")
        self.assertEqual(
            [report["month"] for report in outputs["monthly-reports"]["reports"]],
            ["2026-08"],
        )


class TestWriteOutputs(unittest.TestCase):
    def test_writes_compact_json_and_reports_sizes(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "nested"
            sizes = write_outputs({"metadata": {"a": 1}}, output_dir)
            written = (output_dir / "metadata.json").read_text(encoding="utf-8")
            self.assertEqual(written, '{"a":1}')
            self.assertEqual(json.loads(written), {"a": 1})
            self.assertEqual(sizes, {"metadata.json": len(written)})


class FakeQuery:
    """Minimal stand-in for a PostgREST select query over in-memory rows."""

    def __init__(self, database: "FakeSupabase", table: str) -> None:
        self.database = database
        self.table = table
        self.created_since: str | None = None
        self.order_column: str | None = None
        self.start = 0
        self.end = 0

    def select(self, columns: str) -> "FakeQuery":
        self.columns = columns
        return self

    def gte(self, column: str, value: str) -> "FakeQuery":
        assert column == "created_at"
        self.created_since = value
        return self

    def order(self, column: str) -> "FakeQuery":
        self.order_column = column
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self.start, self.end = start, end
        return self

    def execute(self) -> SimpleNamespace:
        self.database.executed.append(self)
        rows = sorted(self.database.tables[self.table], key=lambda row: row["id"])
        if self.created_since is not None:
            since = datetime.fromisoformat(self.created_since)
            rows = [
                row
                for row in rows
                if datetime.fromisoformat(row["created_at"]) >= since
            ]
        return SimpleNamespace(data=rows[self.start : self.end + 1])


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict[str, Any]]]) -> None:
        self.tables = tables
        self.executed: list[FakeQuery] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


def newsletter_row(
    newsletter_id: str,
    created_at: str,
    subject: str = "News",
) -> dict[str, Any]:
    return {
        "id": newsletter_id,
        "created_at": created_at,
        "received_date": created_at,
        "source_id": 1,
        "subject": subject,
        "plain_text": "Bike lanes",
    }


SOURCE_ROWS = [
    {"id": 1, "name": "Ada Alder", "ward_number": "1", "source_type": "alderman"}
]


class TestFetchRows(unittest.TestCase):
    def test_paginates_with_a_pause_between_full_pages(self) -> None:
        rows = [{"id": f"{index:05d}"} for index in range(FETCH_PAGE_SIZE + 1)]
        supabase = FakeSupabase({"newsletters": rows})
        sleep = MagicMock()
        fetched = fetch_rows(supabase, "newsletters", "id", sleep=sleep)
        self.assertEqual(fetched, rows)
        self.assertEqual(
            [(query.start, query.end) for query in supabase.executed],
            [(0, FETCH_PAGE_SIZE - 1), (FETCH_PAGE_SIZE, 2 * FETCH_PAGE_SIZE - 1)],
        )
        self.assertTrue(all(q.order_column == "id" for q in supabase.executed))
        sleep.assert_called_once_with(FETCH_PAUSE_SECONDS)

    def test_single_short_page_does_not_pause(self) -> None:
        supabase = FakeSupabase({"sources": SOURCE_ROWS})
        sleep = MagicMock()
        self.assertEqual(
            fetch_rows(supabase, "sources", "id", sleep=sleep), SOURCE_ROWS
        )
        sleep.assert_not_called()

    def test_filters_on_created_at_when_given(self) -> None:
        supabase = FakeSupabase(
            {
                "newsletters": [
                    newsletter_row("old", "2026-10-01T00:00:00+00:00"),
                    newsletter_row("new", "2026-10-12T00:00:00+00:00"),
                ]
            }
        )
        since = datetime(2026, 10, 10, tzinfo=UTC)
        fetched = fetch_rows(supabase, "newsletters", "*", since, MagicMock())
        self.assertEqual([row["id"] for row in fetched], ["new"])
        self.assertEqual(supabase.executed[0].created_since, since.isoformat())

    def test_errors_are_not_retried(self) -> None:
        supabase = MagicMock()
        supabase.table.return_value.select.return_value.order.return_value.range.return_value.execute.side_effect = RuntimeError(
            "522"
        )
        with self.assertRaises(RuntimeError):
            fetch_rows(supabase, "newsletters", "id", sleep=MagicMock())
        self.assertEqual(supabase.table.call_count, 1)


class TestRefreshSnapshot(unittest.TestCase):
    def setUp(self) -> None:
        self.cursor = datetime(2026, 10, 11, 20, 0, tzinfo=UTC)
        self.snapshot = Snapshot(
            sources=[],
            newsletters=[
                newsletter_record("kept", date(2026, 9, 1), "Kept"),
                newsletter_record("edited", date(2026, 10, 11), "Before edit"),
            ],
            fetched_through=self.cursor,
        )

    def test_fetches_only_rows_since_cursor_minus_overlap_and_merges(self) -> None:
        supabase = FakeSupabase(
            {
                "sources": SOURCE_ROWS,
                "newsletters": [
                    newsletter_row("kept", "2026-09-01T15:00:00+00:00", "Kept"),
                    newsletter_row("edited", "2026-10-11T15:00:00+00:00", "After edit"),
                    newsletter_row("added", "2026-10-12T15:00:00+00:00"),
                ],
            }
        )
        updated, fetched = refresh_snapshot(supabase, self.snapshot, MagicMock())

        newsletter_queries = [
            query for query in supabase.executed if query.table == "newsletters"
        ]
        # One query for recent rows only; older rows are never re-read.
        self.assertEqual(len(newsletter_queries), 1)
        self.assertEqual(
            newsletter_queries[0].created_since,
            (self.cursor - INCREMENTAL_OVERLAP).isoformat(),
        )
        self.assertEqual(newsletter_queries[0].columns, NEWSLETTER_COLUMNS)
        self.assertNotIn("topics", NEWSLETTER_COLUMNS)
        self.assertEqual(fetched, 2)
        self.assertEqual(
            {item.id: item.subject for item in updated.newsletters},
            {"kept": "Kept", "edited": "After edit", "added": "News"},
        )
        self.assertEqual(
            updated.fetched_through, datetime(2026, 10, 12, 15, 0, tzinfo=UTC)
        )
        self.assertEqual([source.name for source in updated.sources], ["Ada Alder"])

    def test_no_new_rows_keeps_snapshot_and_cursor(self) -> None:
        supabase = FakeSupabase({"sources": SOURCE_ROWS, "newsletters": []})
        updated, fetched = refresh_snapshot(supabase, self.snapshot, MagicMock())
        self.assertEqual(fetched, 0)
        self.assertEqual(updated.newsletters, self.snapshot.newsletters)
        self.assertEqual(updated.fetched_through, self.cursor)


class TestBuildFullSnapshot(unittest.TestCase):
    def test_reads_every_newsletter_and_sets_cursor_to_newest(self) -> None:
        supabase = FakeSupabase(
            {
                "sources": SOURCE_ROWS,
                "newsletters": [
                    newsletter_row("a", "2024-01-01T00:00:00+00:00"),
                    newsletter_row("b", "2026-10-12T00:00:00+00:00"),
                ],
            }
        )
        now = datetime(2026, 10, 13, tzinfo=UTC)
        snapshot = build_full_snapshot(supabase, now, MagicMock())
        self.assertEqual([item.id for item in snapshot.newsletters], ["a", "b"])
        self.assertEqual(snapshot.fetched_through, datetime(2026, 10, 12, tzinfo=UTC))
        self.assertTrue(all(q.created_since is None for q in supabase.executed))

    def test_empty_table_starts_the_cursor_now(self) -> None:
        supabase = FakeSupabase({"sources": SOURCE_ROWS, "newsletters": []})
        now = datetime(2026, 10, 13, tzinfo=UTC)
        self.assertEqual(
            build_full_snapshot(supabase, now, MagicMock()).fetched_through, now
        )


class TestLoadOrRefreshSnapshot(unittest.TestCase):
    NOW = datetime(2026, 10, 13, tzinfo=UTC)

    def setUp(self) -> None:
        # Progress messages are for the CLI; keep test output clean.
        silence = patch("builtins.print")
        silence.start()
        self.addCleanup(silence.stop)

    def make_args(self, directory: Path, **flags: Any) -> argparse.Namespace:
        return argparse.Namespace(
            snapshot_dir=directory,
            offline=flags.get("offline", False),
            full_refresh=flags.get("full_refresh", False),
        )

    def save_seed(self, directory: Path) -> Snapshot:
        seed = Snapshot(
            sources=[SourceRecord(1, "Ada Alder", "1", "alderman")],
            newsletters=[newsletter_record("kept", date(2026, 9, 1), "Kept")],
            fetched_through=datetime(2026, 10, 11, tzinfo=UTC),
        )
        save_snapshot(directory, seed, self.NOW)
        return seed

    def test_offline_never_creates_a_database_client(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            seed = self.save_seed(path)
            with patch("utils.compute_analytics.get_supabase_client") as client:
                snapshot = load_or_refresh_snapshot(
                    self.make_args(path, offline=True), self.NOW
                )
            client.assert_not_called()
            self.assertEqual(snapshot, seed)

    def test_default_mode_refreshes_and_saves_the_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            self.save_seed(path)
            supabase = FakeSupabase(
                {
                    "sources": SOURCE_ROWS,
                    "newsletters": [
                        newsletter_row("added", "2026-10-12T15:00:00+00:00")
                    ],
                }
            )
            with (
                patch(
                    "utils.compute_analytics.get_supabase_client", return_value=supabase
                ),
                patch("utils.compute_analytics.time.sleep"),
            ):
                snapshot = load_or_refresh_snapshot(self.make_args(path), self.NOW)
            self.assertEqual(
                [item.id for item in snapshot.newsletters], ["kept", "added"]
            )
            self.assertEqual(load_snapshot(path), snapshot)

    def test_default_mode_without_snapshot_does_not_touch_the_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with (
                patch("utils.compute_analytics.get_supabase_client") as client,
                self.assertRaises(SnapshotNotFoundError),
            ):
                load_or_refresh_snapshot(
                    self.make_args(Path(directory) / "absent"), self.NOW
                )
            client.assert_not_called()

    def test_full_refresh_builds_and_saves_a_new_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "fresh"
            supabase = FakeSupabase(
                {
                    "sources": SOURCE_ROWS,
                    "newsletters": [newsletter_row("a", "2026-10-12T00:00:00+00:00")],
                }
            )
            with (
                patch(
                    "utils.compute_analytics.get_supabase_client", return_value=supabase
                ),
                patch("utils.compute_analytics.time.sleep"),
            ):
                snapshot = load_or_refresh_snapshot(
                    self.make_args(path, full_refresh=True), self.NOW
                )
            self.assertEqual(load_snapshot(path), snapshot)
            self.assertEqual([item.id for item in snapshot.newsletters], ["a"])


def newsletter_record(newsletter_id: str, day: date, subject: str) -> NewsletterRecord:
    return NewsletterRecord(
        id=newsletter_id,
        received_date=day,
        source_id=1,
        subject=subject,
        plain_text="Bike lanes",
    )


if __name__ == "__main__":
    unittest.main()
