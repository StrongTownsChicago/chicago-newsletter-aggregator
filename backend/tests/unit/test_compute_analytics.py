"""Unit tests for utils/compute_analytics.py orchestration (no database)."""

import argparse
import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from analytics.records import NewsletterRecord, SourceRecord
from analytics.snapshot import Snapshot
from utils.analytics_snapshot import SnapshotNotFoundError, load_snapshot, save_snapshot
from utils.compute_analytics import (
    BOILERPLATE_MIN_SOURCE_NEWSLETTERS,
    FETCH_PAGE_SIZE,
    FETCH_PAUSE_SECONDS,
    INCREMENTAL_OVERLAP,
    LLM_METADATA_COLUMNS,
    RefreshCounts,
    build_full_snapshot,
    compute_outputs,
    fetch_rows,
    fetch_rows_by_id,
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
        topics=["bike_lanes"],
    )


class TestComputeOutputs(unittest.TestCase):
    def test_produces_every_output_file(self):
        sources = [
            SourceRecord(1, "Ada Alder", "1", "alderman"),
            SourceRecord(2, "Bo Alder", "2", "alderman"),
        ]
        newsletters = [
            make_newsletter("a", date(2026, 8, 3), 1, "Protected bike lanes"),
            make_newsletter("b", date(2026, 9, 3), 2, "Protected bike lanes"),
        ]
        outputs = compute_outputs(sources, newsletters, 2, datetime(2026, 10, 11))

        self.assertEqual(
            set(outputs),
            {"metadata", "newsletters", "sources", "terms", "distinctive", "rising"},
        )
        self.assertEqual(outputs["metadata"]["newsletter_count"], 2)
        self.assertEqual(len(outputs["newsletters"]["newsletters"]), 2)
        self.assertIn("bike lanes", outputs["terms"]["terms"])
        self.assertEqual(outputs["terms"]["min_newsletters"], 2)
        self.assertEqual(outputs["rising"]["latest_month"], "2026-09")

    def test_term_metrics_exclude_text_a_source_repeats_in_every_issue(self):
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
        outputs = compute_outputs(sources, newsletters, 1, datetime(2026, 10, 11))

        self.assertNotIn("data notice", outputs["terms"]["terms"])
        self.assertIn("zoning", outputs["terms"]["terms"])
        # Facts still describe the newsletter as received.
        fact_words = outputs["newsletters"]["newsletters"][0]["words"]
        self.assertEqual(fact_words, len(newsletters[0].plain_text.split()))

    def test_handles_dataset_without_complete_month(self):
        sources = [SourceRecord(1, "Ada Alder", "1", "alderman")]
        newsletters = [make_newsletter("a", date(2026, 10, 3), 1, "Bike lanes")]
        outputs = compute_outputs(sources, newsletters, 1, datetime(2026, 10, 11))
        self.assertIsNone(outputs["rising"]["latest_month"])
        self.assertEqual(outputs["rising"]["terms"], [])


class TestWriteOutputs(unittest.TestCase):
    def test_writes_compact_json_and_reports_sizes(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory) / "nested"
            sizes = write_outputs({"metadata": {"a": 1}}, output_dir)
            written = (output_dir / "metadata.json").read_text(encoding="utf-8")
            self.assertEqual(written, '{"a":1}')
            self.assertEqual(json.loads(written), {"a": 1})
            self.assertEqual(sizes, {"metadata.json": len(written)})


class FakeQuery:
    """Minimal stand-in for a PostgREST select query over in-memory rows."""

    def __init__(self, database: "FakeSupabase", table: str):
        self.database = database
        self.table = table
        self.created_since: str | None = None
        self.ids: list[str] | None = None
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

    def in_(self, column: str, values: list[str]) -> "FakeQuery":
        assert column == "id"
        self.ids = values
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
        if self.ids is not None:
            # in_() queries are not paged; return every matching row.
            return SimpleNamespace(data=[row for row in rows if row["id"] in self.ids])
        return SimpleNamespace(data=rows[self.start : self.end + 1])


class FakeSupabase:
    def __init__(self, tables: dict[str, list[dict]]):
        self.tables = tables
        self.executed: list[FakeQuery] = []

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)


def newsletter_row(
    newsletter_id: str,
    created_at: str,
    subject: str = "News",
    topics: list[str] | None = None,
    has_llm_metadata: bool = True,
):
    return {
        "id": newsletter_id,
        "created_at": created_at,
        "received_date": created_at,
        "source_id": 1,
        "subject": subject,
        "plain_text": "Bike lanes",
        "topics": topics if topics is not None else ([] if has_llm_metadata else None),
    }


SOURCE_ROWS = [
    {"id": 1, "name": "Ada Alder", "ward_number": "1", "source_type": "alderman"}
]


class TestFetchRows(unittest.TestCase):
    def test_paginates_with_a_pause_between_full_pages(self):
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

    def test_single_short_page_does_not_pause(self):
        supabase = FakeSupabase({"sources": SOURCE_ROWS})
        sleep = MagicMock()
        self.assertEqual(
            fetch_rows(supabase, "sources", "id", sleep=sleep), SOURCE_ROWS
        )
        sleep.assert_not_called()

    def test_filters_on_created_at_when_given(self):
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

    def test_errors_are_not_retried(self):
        supabase = MagicMock()
        supabase.table.return_value.select.return_value.order.return_value.range.return_value.execute.side_effect = RuntimeError(
            "522"
        )
        with self.assertRaises(RuntimeError):
            fetch_rows(supabase, "newsletters", "id", sleep=MagicMock())
        self.assertEqual(supabase.table.call_count, 1)


class TestFetchRowsById(unittest.TestCase):
    def test_batches_ids_with_a_pause_between_batches(self):
        ids = [f"{index:05d}" for index in range(FETCH_PAGE_SIZE + 1)]
        supabase = FakeSupabase({"newsletters": [{"id": item} for item in ids]})
        sleep = MagicMock()
        fetched = fetch_rows_by_id(supabase, "newsletters", "id", ids, sleep)
        self.assertEqual([row["id"] for row in fetched], ids)
        self.assertEqual(
            [len(query.ids or []) for query in supabase.executed],
            [FETCH_PAGE_SIZE, 1],
        )
        sleep.assert_called_once_with(FETCH_PAUSE_SECONDS)

    def test_no_ids_means_no_queries(self):
        supabase = FakeSupabase({"newsletters": []})
        self.assertEqual(fetch_rows_by_id(supabase, "newsletters", "id", []), [])
        self.assertEqual(supabase.executed, [])


class TestRefreshSnapshot(unittest.TestCase):
    def setUp(self):
        self.cursor = datetime(2026, 10, 11, 20, 0, tzinfo=UTC)
        self.snapshot = Snapshot(
            sources=[],
            newsletters=[
                newsletter_record("kept", date(2026, 9, 1), "Kept"),
                newsletter_record("edited", date(2026, 10, 11), "Before edit"),
            ],
            fetched_through=self.cursor,
        )

    def test_fetches_only_rows_since_cursor_minus_overlap_and_merges(self):
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
        updated, counts = refresh_snapshot(supabase, self.snapshot, MagicMock())

        newsletter_query = next(
            query for query in supabase.executed if query.table == "newsletters"
        )
        self.assertEqual(
            newsletter_query.created_since,
            (self.cursor - INCREMENTAL_OVERLAP).isoformat(),
        )
        self.assertEqual(counts, RefreshCounts(new_rows=2, metadata_rows=0))
        self.assertEqual(
            {item.id: item.subject for item in updated.newsletters},
            {"kept": "Kept", "edited": "After edit", "added": "News"},
        )
        self.assertEqual(
            updated.fetched_through, datetime(2026, 10, 12, 15, 0, tzinfo=UTC)
        )
        self.assertEqual([source.name for source in updated.sources], ["Ada Alder"])

    def test_no_new_rows_keeps_snapshot_and_cursor(self):
        supabase = FakeSupabase({"sources": SOURCE_ROWS, "newsletters": []})
        updated, counts = refresh_snapshot(supabase, self.snapshot, MagicMock())
        self.assertEqual(counts, RefreshCounts(new_rows=0, metadata_rows=0))
        self.assertEqual(updated.newsletters, self.snapshot.newsletters)
        self.assertEqual(updated.fetched_through, self.cursor)
        # Nothing was waiting on LLM metadata, so only the cursor query ran.
        self.assertEqual(
            [query.ids for query in supabase.executed if query.table == "newsletters"],
            [None],
        )

    def test_picks_up_llm_metadata_added_after_the_overlap_window(self):
        # Ingested weeks ago without LLM metadata; processed since then.
        pending = newsletter_record(
            "pending", date(2026, 9, 2), "Pending", has_llm_metadata=False
        )
        snapshot = Snapshot([], [*self.snapshot.newsletters, pending], self.cursor)
        supabase = FakeSupabase(
            {
                "sources": SOURCE_ROWS,
                "newsletters": [
                    newsletter_row(
                        "pending",
                        "2026-09-02T15:00:00+00:00",
                        topics=["bike_lanes"],
                    )
                ],
            }
        )
        updated, counts = refresh_snapshot(supabase, snapshot, MagicMock())

        self.assertEqual(counts, RefreshCounts(new_rows=0, metadata_rows=1))
        refreshed = next(item for item in updated.newsletters if item.id == "pending")
        self.assertEqual(refreshed.topics, ["bike_lanes"])
        metadata_query = next(q for q in supabase.executed if q.ids is not None)
        self.assertEqual(metadata_query.ids, ["pending"])
        # Old text is never re-read; only the metadata columns are requested.
        self.assertEqual(metadata_query.columns, LLM_METADATA_COLUMNS)
        self.assertNotIn("plain_text", metadata_query.columns)

    def test_rows_fetched_by_the_cursor_are_not_fetched_again(self):
        supabase = FakeSupabase(
            {
                "sources": SOURCE_ROWS,
                "newsletters": [
                    newsletter_row(
                        "fresh", "2026-10-12T15:00:00+00:00", has_llm_metadata=False
                    )
                ],
            }
        )
        _, counts = refresh_snapshot(supabase, self.snapshot, MagicMock())
        self.assertEqual(counts, RefreshCounts(new_rows=1, metadata_rows=0))
        self.assertTrue(all(q.ids is None for q in supabase.executed))


class TestBuildFullSnapshot(unittest.TestCase):
    def test_reads_every_newsletter_and_sets_cursor_to_newest(self):
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

    def test_empty_table_starts_the_cursor_now(self):
        supabase = FakeSupabase({"sources": SOURCE_ROWS, "newsletters": []})
        now = datetime(2026, 10, 13, tzinfo=UTC)
        self.assertEqual(
            build_full_snapshot(supabase, now, MagicMock()).fetched_through, now
        )


class TestLoadOrRefreshSnapshot(unittest.TestCase):
    NOW = datetime(2026, 10, 13, tzinfo=UTC)

    def setUp(self):
        # Progress messages are for the CLI; keep test output clean.
        silence = patch("builtins.print")
        silence.start()
        self.addCleanup(silence.stop)

    def make_args(self, directory: Path, **flags) -> argparse.Namespace:
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

    def test_offline_never_creates_a_database_client(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            seed = self.save_seed(path)
            with patch("utils.compute_analytics.get_supabase_client") as client:
                snapshot = load_or_refresh_snapshot(
                    self.make_args(path, offline=True), self.NOW
                )
            client.assert_not_called()
            self.assertEqual(snapshot, seed)

    def test_default_mode_refreshes_and_saves_the_snapshot(self):
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

    def test_default_mode_without_snapshot_does_not_touch_the_database(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch("utils.compute_analytics.get_supabase_client") as client:
                with self.assertRaises(SnapshotNotFoundError):
                    load_or_refresh_snapshot(
                        self.make_args(Path(directory) / "absent"), self.NOW
                    )
            client.assert_not_called()

    def test_full_refresh_builds_and_saves_a_new_snapshot(self):
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


def newsletter_record(
    newsletter_id: str, day: date, subject: str, has_llm_metadata: bool = True
) -> NewsletterRecord:
    return NewsletterRecord(
        id=newsletter_id,
        received_date=day,
        source_id=1,
        subject=subject,
        plain_text="Bike lanes",
        topics=[] if has_llm_metadata else None,
    )


if __name__ == "__main__":
    unittest.main()
