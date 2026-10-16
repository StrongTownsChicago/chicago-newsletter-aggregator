"""Unit tests for analytics/topic_reach.py."""

import unittest
from datetime import date
from typing import ClassVar

from analytics.lenses import Lens
from analytics.records import NewsletterRecord, SourceRecord
from analytics.topic_reach import (
    TopicNewsletter,
    build_topic_labels,
    build_topic_newsletters,
    group_sending_wards_by_month,
    group_topic_wards,
    list_months_ending,
    select_broad_complete_months,
)


def item(
    newsletter_id: str,
    ward: str | None,
    day: date,
    readable: bool = True,
    topics: dict[str, int] | None = None,
) -> TopicNewsletter:
    return TopicNewsletter(
        id=newsletter_id,
        ward=ward,
        received_date=day,
        subject=f"Subject {newsletter_id}",
        readable=readable,
        topic_mentions=topics or {},
    )


class TestBuildTopicNewsletters(unittest.TestCase):
    def test_attaches_ward_readability_and_only_mentioned_topics(self):
        newsletters = [
            NewsletterRecord("a", date(2026, 9, 1), 1, "  Hello  ", "text"),
            NewsletterRecord("b", date(2026, 9, 2), None, "No source", "text"),
        ]
        sources = {1: SourceRecord(1, "Ada", "7", "alderman")}
        result = build_topic_newsletters(
            newsletters,
            sources,
            unavailable_ids={"b"},
            lens_mentions_by_newsletter={"a": {"schools": 3, "parks": 1}},
            lenses_by_newsletter={"a": ["schools"]},
        )
        first, second = result
        self.assertEqual(first.ward, "7")
        self.assertEqual(first.subject, "Hello")
        self.assertTrue(first.readable)
        self.assertEqual(dict(first.topic_mentions), {"schools": 3})
        self.assertEqual(first.month, "2026-09")
        self.assertIsNone(second.ward)
        self.assertFalse(second.readable)
        self.assertEqual(dict(second.topic_mentions), {})


class TestGrouping(unittest.TestCase):
    items: ClassVar = [
        item("a", "1", date(2026, 8, 1), topics={"schools": 2}),
        item("b", "2", date(2026, 8, 2), readable=False),
        item("c", "2", date(2026, 9, 2), topics={"schools": 2}),
        item("d", None, date(2026, 9, 3), topics={"schools": 2}),
    ]

    def test_sending_wards_count_unreadable_newsletters_unless_asked(self):
        self.assertEqual(
            group_sending_wards_by_month(self.items),
            {"2026-08": {"1", "2"}, "2026-09": {"2"}},
        )
        self.assertEqual(
            group_sending_wards_by_month(self.items, readable_only=True),
            {"2026-08": {"1"}, "2026-09": {"2"}},
        )

    def test_topic_wards_ignore_newsletters_without_a_ward(self):
        self.assertEqual(group_topic_wards(self.items), {"schools": {"1", "2"}})


class TestSelectBroadCompleteMonths(unittest.TestCase):
    def test_keeps_complete_months_with_enough_sending_wards(self):
        items = [
            item("a", "1", date(2026, 7, 1)),
            item("b", "1", date(2026, 8, 1)),
            item("c", "2", date(2026, 8, 1)),
            item("d", "1", date(2026, 9, 1)),
            item("e", "2", date(2026, 9, 1)),
            item("f", "1", date(2026, 10, 1)),
            item("g", "2", date(2026, 10, 1)),
        ]
        self.assertEqual(
            select_broad_complete_months(items, "2026-10", min_sending_wards=2),
            ["2026-08", "2026-09"],
        )


class TestHelpers(unittest.TestCase):
    def test_list_months_ending_crosses_years(self):
        self.assertEqual(
            list_months_ending("2026-02", 3), ["2025-12", "2026-01", "2026-02"]
        )

    def test_topic_labels_keep_display_order(self):
        topics = [
            Lens("b", "Bee", "", ("bee",)),
            Lens("a", "Ay", "", ("ay",)),
        ]
        self.assertEqual(
            list(build_topic_labels(topics).items()), [("b", "Bee"), ("a", "Ay")]
        )


if __name__ == "__main__":
    unittest.main()
