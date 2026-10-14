"""Unit tests for utils/analytics_snapshot.py (temporary directories only)."""

import gzip
import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path

from analytics.records import NewsletterRecord, SourceRecord
from analytics.snapshot import Snapshot
from utils.analytics_snapshot import (
    METADATA_FILE,
    NEWSLETTERS_FILE,
    SnapshotNotFoundError,
    load_snapshot,
    save_snapshot,
)

SAVED_AT = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


def make_snapshot() -> Snapshot:
    return Snapshot(
        sources=[
            SourceRecord(1, "Ada", "1", "alderman"),
            SourceRecord(51, "CTA", None, "agency"),
        ],
        newsletters=[
            NewsletterRecord(
                "a", date(2026, 1, 5), 1, "Snow", "Plows: café", ["snow"], 3
            ),
            NewsletterRecord("b", date(2026, 2, 6), None, "Bus", "Route 9", None, None),
        ],
        fetched_through=datetime(2026, 10, 12, 20, 31, 2, 123456, tzinfo=UTC),
    )


class TestSnapshotStore(unittest.TestCase):
    def test_save_then_load_round_trips(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "snapshot"
            snapshot = make_snapshot()
            save_snapshot(path, snapshot, SAVED_AT)
            self.assertEqual(load_snapshot(path), snapshot)
            self.assertEqual(
                sorted(item.name for item in path.iterdir()),
                ["metadata.json", "newsletters.jsonl.gz", "sources.json"],
            )

    def test_metadata_summarizes_the_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            save_snapshot(path, make_snapshot(), SAVED_AT)
            metadata = json.loads((path / METADATA_FILE).read_text(encoding="utf-8"))
            self.assertEqual(metadata["newsletter_count"], 2)
            self.assertEqual(metadata["source_count"], 2)
            self.assertEqual(metadata["received_date_min"], "2026-01-05")
            self.assertEqual(metadata["received_date_max"], "2026-02-06")
            self.assertEqual(metadata["saved_at"], SAVED_AT.isoformat())

    def test_newsletters_file_is_plain_gzipped_json_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            save_snapshot(path, make_snapshot(), SAVED_AT)
            with gzip.open(path / NEWSLETTERS_FILE, "rt", encoding="utf-8") as file:
                rows = [json.loads(line) for line in file]
            self.assertEqual([row["id"] for row in rows], ["a", "b"])
            self.assertEqual(rows[0]["plain_text"], "Plows: café")

    def test_saves_an_empty_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            empty = Snapshot([], [], SAVED_AT)
            save_snapshot(path, empty, SAVED_AT)
            self.assertEqual(load_snapshot(path), empty)

    def test_missing_snapshot_raises_a_clear_error(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SnapshotNotFoundError) as context:
                load_snapshot(Path(directory) / "absent")
            self.assertIn("metadata.json", str(context.exception))

    def test_rejects_unknown_format_versions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            save_snapshot(path, make_snapshot(), SAVED_AT)
            metadata_path = path / METADATA_FILE
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
            metadata["format_version"] = 99
            metadata_path.write_text(json.dumps(metadata), encoding="utf-8")
            with self.assertRaises(ValueError):
                load_snapshot(path)


if __name__ == "__main__":
    unittest.main()
