"""Unit tests for utils/analytics_snapshot.py (temporary directories only)."""

import gzip
import json
import tempfile
import unittest
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from analytics.records import NewsletterRecord, SourceRecord
from analytics.snapshot import Snapshot
from utils.analytics_snapshot import (
    METADATA_FILE,
    NEWSLETTERS_FILE,
    SOURCES_FILE,
    SnapshotError,
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
            NewsletterRecord("a", date(2026, 1, 5), 1, "Snow", "Plows: café"),
            NewsletterRecord("b", date(2026, 2, 6), None, "Bus", "Route 9"),
        ],
        fetched_through=datetime(2026, 10, 12, 20, 31, 2, 123456, tzinfo=UTC),
    )


class TestSnapshotStore(unittest.TestCase):
    def test_save_then_load_round_trips(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "nested" / "snapshot"
            snapshot = make_snapshot()
            save_snapshot(path, snapshot, SAVED_AT)
            self.assertEqual(load_snapshot(path), snapshot)
            self.assertEqual(
                sorted(item.name for item in path.iterdir()),
                ["metadata.json", "newsletters.jsonl.gz", "sources.json"],
            )

    def test_metadata_summarizes_the_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            save_snapshot(path, make_snapshot(), SAVED_AT)
            metadata = json.loads((path / METADATA_FILE).read_text(encoding="utf-8"))
            self.assertEqual(metadata["newsletter_count"], 2)
            self.assertEqual(metadata["source_count"], 2)
            self.assertEqual(metadata["received_date_min"], "2026-01-05")
            self.assertEqual(metadata["received_date_max"], "2026-02-06")
            self.assertEqual(metadata["saved_at"], SAVED_AT.isoformat())

    def test_newsletters_file_is_plain_gzipped_json_lines(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            save_snapshot(path, make_snapshot(), SAVED_AT)
            with gzip.open(path / NEWSLETTERS_FILE, "rt", encoding="utf-8") as file:
                rows = [json.loads(line) for line in file]
            self.assertEqual([row["id"] for row in rows], ["a", "b"])
            self.assertEqual(rows[0]["plain_text"], "Plows: café")

    def test_saves_an_empty_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            empty = Snapshot([], [], SAVED_AT)
            save_snapshot(path, empty, SAVED_AT)
            self.assertEqual(load_snapshot(path), empty)

    def test_missing_snapshot_raises_a_clear_error(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(SnapshotNotFoundError) as context:
                load_snapshot(Path(directory) / "absent")
            self.assertIn("metadata.json", str(context.exception))

    def edit_metadata(self, path: Path, **changes: Any) -> None:
        metadata_path = path / METADATA_FILE
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        metadata.update(changes)
        metadata_path.write_text(json.dumps(metadata), encoding="utf-8")

    def test_rejects_unknown_format_versions(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            save_snapshot(path, make_snapshot(), SAVED_AT)
            self.edit_metadata(path, format_version=99)
            with self.assertRaisesRegex(SnapshotError, "Unsupported snapshot format"):
                load_snapshot(path)

    def test_rejects_a_cursor_without_a_timezone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            save_snapshot(path, make_snapshot(), SAVED_AT)
            self.edit_metadata(path, fetched_through="2026-10-12T20:31:02")
            with self.assertRaisesRegex(SnapshotError, "timezone"):
                load_snapshot(path)

    def test_corrupt_files_raise_snapshot_error(self) -> None:
        corruptions = {
            "truncated newsletters": (NEWSLETTERS_FILE, b"\x1f\x8b\x08\x00"),
            "not gzip": (NEWSLETTERS_FILE, b"plain text"),
            "malformed metadata": (METADATA_FILE, b"{not json"),
            "metadata without cursor": (METADATA_FILE, b'{"format_version": 1}'),
            "malformed sources": (SOURCES_FILE, b"[{"),
        }
        for label, (file_name, content) in corruptions.items():
            with self.subTest(label), tempfile.TemporaryDirectory() as directory:
                path = Path(directory)
                save_snapshot(path, make_snapshot(), SAVED_AT)
                (path / file_name).write_bytes(content)
                with self.assertRaisesRegex(SnapshotError, "unreadable"):
                    load_snapshot(path)

    def test_missing_snapshot_is_a_snapshot_error(self) -> None:
        self.assertTrue(issubclass(SnapshotNotFoundError, SnapshotError))

    def test_leftover_temp_files_do_not_block_a_save(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / f"{NEWSLETTERS_FILE}.tmp").write_bytes(b"partial")
            (path / f"{METADATA_FILE}.tmp").write_text("partial", encoding="utf-8")
            save_snapshot(path, make_snapshot(), SAVED_AT)
            self.assertEqual(load_snapshot(path), make_snapshot())
            self.assertEqual(list(path.glob("*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
