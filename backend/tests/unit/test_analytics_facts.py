"""Unit tests for analytics/facts.py shaping functions."""

import unittest
from datetime import date, datetime

from analytics.facts import (
    build_metadata,
    build_newsletter_fact,
    build_newsletter_facts,
    build_source_coverage,
)
from analytics.records import NewsletterRecord, SourceRecord

ALDER = SourceRecord(id=1, name="Ada Alder", ward="1", source_type="alderman")
QUIET = SourceRecord(id=2, name="Quiet Alder", ward="2", source_type="alderman")


def make_newsletter(
    newsletter_id: str, day: date, source_id: int | None = 1
) -> NewsletterRecord:
    return NewsletterRecord(
        id=newsletter_id,
        received_date=day,
        source_id=source_id,
        subject="Subject",
        plain_text="three word body",
        topics=["bike_lanes"],
        relevance_score=6,
    )


class TestBuildNewsletterFact(unittest.TestCase):
    def test_shapes_fact_without_body_text(self):
        fact = build_newsletter_fact(make_newsletter("n1", date(2026, 1, 2)), ALDER)
        self.assertEqual(
            fact,
            {
                "id": "n1",
                "date": "2026-01-02",
                "source_id": 1,
                "ward": "1",
                "alder": "Ada Alder",
                "topics": ["bike_lanes"],
                "relevance": 6,
                "words": 3,
            },
        )
        self.assertNotIn("plain_text", fact)

    def test_missing_source_yields_null_ward_and_alder(self):
        fact = build_newsletter_fact(
            make_newsletter("n1", date(2026, 1, 2), None), None
        )
        self.assertIsNone(fact["ward"])
        self.assertIsNone(fact["alder"])


class TestBuildNewsletterFacts(unittest.TestCase):
    def test_orders_by_date_and_joins_sources(self):
        facts = build_newsletter_facts(
            [
                make_newsletter("late", date(2026, 2, 1)),
                make_newsletter("early", date(2026, 1, 1), source_id=99),
            ],
            {1: ALDER},
        )
        self.assertEqual([fact["id"] for fact in facts], ["early", "late"])
        self.assertIsNone(facts[0]["ward"])
        self.assertEqual(facts[1]["ward"], "1")


class TestBuildSourceCoverage(unittest.TestCase):
    def test_reports_span_and_count_including_sources_without_newsletters(self):
        coverage = build_source_coverage(
            [QUIET, ALDER],
            [
                make_newsletter("a", date(2025, 6, 1)),
                make_newsletter("b", date(2024, 1, 15)),
            ],
        )
        self.assertEqual(
            coverage[0],
            {
                "id": 1,
                "name": "Ada Alder",
                "ward": "1",
                "source_type": "alderman",
                "first_date": "2024-01-15",
                "last_date": "2025-06-01",
                "newsletters": 2,
            },
        )
        self.assertEqual(coverage[1]["newsletters"], 0)
        self.assertIsNone(coverage[1]["first_date"])


class TestBuildMetadata(unittest.TestCase):
    def test_summarizes_counts_and_span(self):
        generated_at = datetime(2026, 10, 11, 9, 0)
        metadata = build_metadata(
            [
                make_newsletter("a", date(2025, 6, 1)),
                make_newsletter("b", date(2024, 1, 15)),
            ],
            [ALDER, QUIET],
            term_count=42,
            min_term_newsletters=20,
            generated_at=generated_at,
        )
        self.assertEqual(metadata["newsletter_count"], 2)
        self.assertEqual(metadata["source_count"], 2)
        self.assertEqual(metadata["first_date"], "2024-01-15")
        self.assertEqual(metadata["last_date"], "2025-06-01")
        self.assertEqual(metadata["term_count"], 42)
        self.assertEqual(metadata["generated_at"], generated_at.isoformat())

    def test_empty_dataset_has_null_span(self):
        metadata = build_metadata([], [], 0, 20, datetime(2026, 1, 1))
        self.assertIsNone(metadata["first_date"])
        self.assertIsNone(metadata["last_date"])


if __name__ == "__main__":
    unittest.main()
