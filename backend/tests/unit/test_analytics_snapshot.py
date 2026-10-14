"""Unit tests for analytics/snapshot.py row format, merging, and cursor rules."""

import unittest
from dataclasses import replace
from datetime import UTC, date, datetime

from analytics.records import NewsletterRecord, SourceRecord
from analytics.snapshot import (
    advance_cursor,
    apply_llm_metadata,
    ids_missing_llm_metadata,
    merge_newsletters,
    newest_created_at,
    newsletter_from_row,
    newsletter_to_row,
    source_from_row,
    source_to_row,
)


def make_newsletter(newsletter_id: str, day: date, subject: str = "Update"):
    return NewsletterRecord(
        id=newsletter_id,
        received_date=day,
        source_id=1,
        subject=subject,
        plain_text="Text",
        topics=None,
        relevance_score=None,
    )


class TestRowRoundTrip(unittest.TestCase):
    def test_newsletter_round_trips_without_shifting_the_date(self):
        newsletter = NewsletterRecord(
            id="abc",
            received_date=date(2026, 9, 30),
            source_id=7,
            subject="Ward news",
            plain_text="Bike lanes",
            topics=["bike_lanes"],
            relevance_score=4,
        )
        row = newsletter_to_row(newsletter)
        self.assertEqual(row["received_date"], "2026-09-30")
        self.assertEqual(newsletter_from_row(row), newsletter)

    def test_newsletter_from_row_tolerates_missing_optional_fields(self):
        newsletter = newsletter_from_row(
            {"id": 5, "received_date": "2026-01-02", "source_id": None}
        )
        self.assertEqual(newsletter.id, "5")
        self.assertIsNone(newsletter.source_id)
        self.assertEqual(newsletter.subject, "")
        self.assertEqual(newsletter.plain_text, "")

    def test_source_round_trips(self):
        for source in (
            SourceRecord(1, "Ada", "1", "alderman"),
            SourceRecord(51, "CTA", None, "agency"),
        ):
            self.assertEqual(source_from_row(source_to_row(source)), source)


class TestMergeNewsletters(unittest.TestCase):
    def test_fetched_rows_replace_existing_rows_with_the_same_id(self):
        existing = [make_newsletter("a", date(2026, 1, 1), "Old subject")]
        updates = [make_newsletter("a", date(2026, 1, 1), "New subject")]
        merged = merge_newsletters(existing, updates)
        self.assertEqual([item.subject for item in merged], ["New subject"])

    def test_keeps_existing_rows_and_sorts_by_date_then_id(self):
        existing = [
            make_newsletter("b", date(2026, 2, 1)),
            make_newsletter("z", date(2026, 1, 1)),
        ]
        updates = [make_newsletter("a", date(2026, 2, 1))]
        merged = merge_newsletters(existing, updates)
        self.assertEqual([item.id for item in merged], ["z", "a", "b"])


class TestLlmMetadata(unittest.TestCase):
    def test_ids_missing_llm_metadata_flags_null_topics_or_score(self):
        processed = replace(
            make_newsletter("done", date(2026, 1, 1)), topics=[], relevance_score=0
        )
        no_topics = replace(processed, id="no_topics", topics=None)
        no_score = replace(processed, id="no_score", relevance_score=None)
        self.assertEqual(
            ids_missing_llm_metadata([processed, no_topics, no_score]),
            ["no_topics", "no_score"],
        )

    def test_apply_llm_metadata_updates_only_matching_newsletters(self):
        pending = make_newsletter("pending", date(2026, 1, 1))
        other = make_newsletter("other", date(2026, 1, 2))
        rows = [{"id": "pending", "topics": ["transit"], "relevance_score": 6}]
        updated = apply_llm_metadata([pending, other], rows)
        self.assertEqual(
            updated[0], replace(pending, topics=["transit"], relevance_score=6)
        )
        self.assertEqual(updated[1], other)


class TestCursor(unittest.TestCase):
    def test_newest_created_at_parses_supabase_timestamps(self):
        rows = [
            {"created_at": "2026-10-12T01:02:03.12345+00:00"},
            {"created_at": "2026-10-13T00:00:00+00:00"},
            {"created_at": None},
        ]
        self.assertEqual(newest_created_at(rows), datetime(2026, 10, 13, tzinfo=UTC))

    def test_newest_created_at_is_none_without_timestamps(self):
        self.assertIsNone(newest_created_at([]))
        self.assertIsNone(newest_created_at([{"id": 1}]))

    def test_advance_cursor_moves_forward(self):
        current = datetime(2026, 10, 11, tzinfo=UTC)
        rows = [{"created_at": "2026-10-12T00:00:00+00:00"}]
        self.assertEqual(
            advance_cursor(current, rows), datetime(2026, 10, 12, tzinfo=UTC)
        )

    def test_advance_cursor_never_moves_backwards(self):
        current = datetime(2026, 10, 11, tzinfo=UTC)
        # Rows from the overlap window are older than the cursor.
        rows = [{"created_at": "2026-10-10T12:00:00+00:00"}]
        self.assertEqual(advance_cursor(current, rows), current)
        self.assertEqual(advance_cursor(current, []), current)


if __name__ == "__main__":
    unittest.main()
