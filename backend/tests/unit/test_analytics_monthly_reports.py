"""Unit tests for analytics/monthly_reports.py."""

import unittest
from datetime import date

from analytics.monthly_reports import (
    MonthlyReportSettings,
    build_monthly_report,
    build_monthly_reports,
    pick_topic_examples,
    summarize_month_topics,
    summarize_rising_terms,
)
from analytics.terms import NewsletterTerms
from analytics.topic_reach import TopicNewsletter

SETTINGS = MonthlyReportSettings(
    examples_per_topic=2,
    rising_baseline_months=2,
    rising_min_latest_wards=2,
    rising_min_ward_gain=1,
    rising_top_n=5,
)


def item(
    newsletter_id: str,
    ward: str | None,
    day: date,
    topics: dict[str, int] | None = None,
    readable: bool = True,
) -> TopicNewsletter:
    return TopicNewsletter(
        id=newsletter_id,
        ward=ward,
        received_date=day,
        subject=f"Subject {newsletter_id}",
        readable=readable,
        topic_mentions=topics or {},
    )


def doc(newsletter_id: str, ward: str, month: str, terms: set[str]) -> NewsletterTerms:
    return NewsletterTerms(newsletter_id, 1, ward, month, frozenset(terms))


class TestPickTopicExamples(unittest.TestCase):
    def test_prefers_most_mentions_and_one_newsletter_per_ward(self):
        items = [
            item("a", "1", date(2026, 9, 5), {"schools": 2}),
            item("b", "1", date(2026, 9, 6), {"schools": 9}),
            item("c", "2", date(2026, 9, 7), {"schools": 3}),
            item("d", "3", date(2026, 9, 1), {"schools": 3}),
            item("e", "4", date(2026, 9, 1), {"schools": 9}, readable=False),
            item("f", "5", date(2026, 9, 1), {"parks": 9}),
        ]
        examples = pick_topic_examples(items, "schools", limit=3)
        # Ties on mentions go to the earlier newsletter.
        self.assertEqual([example.id for example in examples], ["b", "d", "c"])


class TestSummarizeMonthTopics(unittest.TestCase):
    def test_orders_topics_by_ward_reach_then_display_order(self):
        items = [
            item("a", "1", date(2026, 9, 1), {"parks": 2, "schools": 2}),
            item("b", "2", date(2026, 9, 1), {"schools": 2}),
            item("c", "2", date(2026, 9, 2), {"schools": 2, "zoning": 2}),
        ]
        topics = summarize_month_topics(
            items, ["parks", "zoning", "schools", "budget"], 1
        )
        self.assertEqual(
            [topic["id"] for topic in topics], ["schools", "parks", "zoning"]
        )
        self.assertEqual(topics[0]["wards"], 2)
        self.assertEqual(topics[0]["newsletters"], 3)
        self.assertEqual(len(topics[0]["examples"]), 1)
        self.assertEqual(
            set(topics[0]["examples"][0]), {"id", "subject", "ward", "date"}
        )


class TestSummarizeRisingTerms(unittest.TestCase):
    documents = [
        doc("a", "1", "2026-07", {"budget"}),
        doc("b", "1", "2026-08", {"budget"}),
        doc("c", "1", "2026-09", {"budget", "labor day"}),
        doc("d", "2", "2026-09", {"labor day"}),
        doc("e", "2", "2026-08", {"park"}),
    ]

    def test_reports_terms_more_wards_used_than_in_the_baseline(self):
        rising = summarize_rising_terms(
            "2026-09",
            self.documents,
            {"budget", "labor day", "park"},
            broad_months={"2026-07", "2026-08", "2026-09"},
            settings=SETTINGS,
        )
        assert rising is not None
        self.assertEqual(rising["baseline_months"], ["2026-07", "2026-08"])
        self.assertEqual(
            rising["terms"], [{"term": "labor day", "wards": 2, "baseline_wards": 0.0}]
        )

    def test_omitted_when_a_baseline_month_lacks_broad_coverage(self):
        rising = summarize_rising_terms(
            "2026-09",
            self.documents,
            {"labor day"},
            broad_months={"2026-08", "2026-09"},
            settings=SETTINGS,
        )
        self.assertIsNone(rising)


class TestBuildMonthlyReport(unittest.TestCase):
    def test_names_sending_and_absent_wards(self):
        items = [
            item("a", "1", date(2026, 9, 1), {"schools": 2}),
            item("b", "10", date(2026, 9, 2), readable=False),
            item("c", "2", date(2026, 8, 2), {"schools": 2}),
        ]
        report = build_monthly_report(
            "2026-09",
            items,
            [],
            set(),
            ["schools"],
            ["1", "2", "10"],
            broad_months={"2026-09"},
            settings=SETTINGS,
        )
        self.assertEqual(report["newsletters"], 2)
        self.assertEqual(report["sending_wards"], ["1", "10"])
        self.assertEqual(report["absent_wards"], ["2"])
        self.assertEqual(report["readable_wards"], 1)
        self.assertEqual(report["topics"][0]["wards"], 1)
        self.assertIsNone(report["rising"])

    def test_builds_newest_month_first(self):
        items = [
            item("a", "1", date(2026, 8, 1)),
            item("b", "1", date(2026, 9, 1)),
        ]
        reports = build_monthly_reports(
            ["2026-08", "2026-09"], items, [], set(), [], ["1"], SETTINGS
        )
        self.assertEqual(
            [report["month"] for report in reports], ["2026-09", "2026-08"]
        )


if __name__ == "__main__":
    unittest.main()
