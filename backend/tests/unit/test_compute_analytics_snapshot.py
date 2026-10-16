"""Unit tests for utils/compute_analytics.py snapshot fetching and refresh (fake database)."""

import argparse
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, patch

from analytics.records import NewsletterRecord, SourceRecord
from analytics.snapshot import Snapshot
from utils.analytics_snapshot import SnapshotNotFoundError, load_snapshot, save_snapshot
from utils.compute_analytics import (
    FETCH_PAGE_SIZE,
    FETCH_PAUSE_SECONDS,
    INCREMENTAL_OVERLAP,
    NEWSLETTER_COLUMNS,
    build_full_snapshot,
    fetch_rows,
    load_or_refresh_snapshot,
    refresh_snapshot,
)


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
