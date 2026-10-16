"""Unit tests for analytics/monthly_reports.py."""

import unittest
from datetime import date

from analytics.monthly_reports import (
    MonthlyReportSettings,
    build_monthly_report,
    build_monthly_reports,
    pick_topic_examples,
    summarize_month_topics,
)
from analytics.topic_reach import TopicNewsletter

SETTINGS = MonthlyReportSettings(examples_per_topic=2)


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


class TestPickTopicExamples(unittest.TestCase):
    def test_prefers_most_mentions_and_one_newsletter_per_ward(self) -> None:
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

    def test_prefers_newsletters_not_shown_for_another_topic(self) -> None:
        items = [
            item("roundup", "1", date(2026, 9, 1), {"schools": 9}),
            item("short", "2", date(2026, 9, 2), {"schools": 2}),
        ]
        examples = pick_topic_examples(
            items, "schools", limit=1, shown_ids=frozenset({"roundup"})
        )
        self.assertEqual([example.id for example in examples], ["short"])
        # A shown newsletter is still used when nothing else qualifies.
        examples = pick_topic_examples(
            items, "schools", limit=2, shown_ids=frozenset({"roundup"})
        )
        self.assertEqual([example.id for example in examples], ["short", "roundup"])


class TestSummarizeMonthTopics(unittest.TestCase):
    def test_orders_topics_by_ward_reach_then_display_order(self) -> None:
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


class TestBuildMonthlyReport(unittest.TestCase):
    def test_counts_sending_and_readable_wards(self) -> None:
        items = [
            item("a", "1", date(2026, 9, 1), {"schools": 2}),
            item("b", "10", date(2026, 9, 2), readable=False),
            item("c", "2", date(2026, 8, 2), {"schools": 2}),
        ]
        report = build_monthly_report("2026-09", items, ["schools"], SETTINGS)
        self.assertEqual(report["newsletters"], 2)
        self.assertEqual(report["sending_wards"], ["1", "10"])
        # Absent wards are not named: missing from the archive is not silence.
        self.assertNotIn("absent_wards", report)
        self.assertEqual(report["readable_wards"], 1)
        self.assertEqual(report["topics"][0]["wards"], 1)
        self.assertNotIn("rising", report)

    def test_builds_newest_month_first(self) -> None:
        items = [
            item("a", "1", date(2026, 8, 1)),
            item("b", "1", date(2026, 9, 1)),
        ]
        reports = build_monthly_reports(["2026-08", "2026-09"], items, [], SETTINGS)
        self.assertEqual(
            [report["month"] for report in reports], ["2026-09", "2026-08"]
        )


if __name__ == "__main__":
    unittest.main()
