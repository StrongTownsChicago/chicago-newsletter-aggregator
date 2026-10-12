"""Unit tests for utils/compute_analytics.py orchestration (no database)."""

import json
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock

from analytics.records import NewsletterRecord, SourceRecord
from utils.compute_analytics import (
    FETCH_PAGE_SIZE,
    compute_outputs,
    fetch_all_rows,
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
        relevance_score=5,
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


class TestFetchAllRows(unittest.TestCase):
    def test_paginates_until_short_page(self):
        supabase = MagicMock()
        query = supabase.table.return_value.select.return_value.order.return_value
        full_page = [{"id": i} for i in range(FETCH_PAGE_SIZE)]
        query.range.return_value.execute.side_effect = [
            MagicMock(data=full_page),
            MagicMock(data=[{"id": FETCH_PAGE_SIZE}]),
        ]
        rows = fetch_all_rows(supabase, "newsletters", "id", "id")
        self.assertEqual(len(rows), FETCH_PAGE_SIZE + 1)
        query.range.assert_any_call(0, FETCH_PAGE_SIZE - 1)
        query.range.assert_any_call(FETCH_PAGE_SIZE, 2 * FETCH_PAGE_SIZE - 1)


if __name__ == "__main__":
    unittest.main()
