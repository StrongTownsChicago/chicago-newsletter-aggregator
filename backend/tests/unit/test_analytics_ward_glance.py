"""Unit tests for analytics/ward_glance.py."""

import unittest
from datetime import date

from analytics.terms import NewsletterTerms
from analytics.topic_reach import TopicNewsletter
from analytics.ward_glance import (
    WardGlanceSettings,
    average_per_month,
    build_ward_glances,
    count_recent_months,
    is_non_topical_term,
    select_recent_terms,
    summarize_ward_topics,
)

SETTINGS = WardGlanceSettings(
    window_months=3,
    top_topics=2,
    top_terms=3,
    distinctive_candidates=10,
    distinctive_min_ward_newsletters=1,
    distinctive_min_term_newsletters_in_ward=1,
    distinctive_max_ward_share=1.0,
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
        subject="Update",
        readable=readable,
        topic_mentions=topics or {},
    )


def doc(newsletter_id: str, ward: str, month: str, terms: set[str]) -> NewsletterTerms:
    return NewsletterTerms(newsletter_id, 1, ward, month, frozenset(terms))


class TestCadence(unittest.TestCase):
    def test_months_before_the_first_newsletter_are_unknown_not_zero(self):
        ward_items = [
            item("a", "1", date(2026, 8, 20)),
            item("b", "1", date(2026, 8, 21)),
        ]
        recent = count_recent_months(ward_items, ["2026-07", "2026-08", "2026-09"])
        self.assertEqual(recent, [None, 2, 0])
        self.assertEqual(average_per_month(recent), 1.0)

    def test_average_is_none_without_tracked_months(self):
        self.assertIsNone(average_per_month([None, None]))


class TestSummarizeWardTopics(unittest.TestCase):
    def test_counts_readable_newsletters_and_adds_city_reach(self):
        window_items = [
            item("a", "1", date(2026, 9, 1), {"schools": 2, "parks": 2}),
            item("b", "1", date(2026, 9, 2), {"schools": 2}),
            item("c", "1", date(2026, 9, 3), {"zoning": 2}),
            item("d", "1", date(2026, 9, 4), {"zoning": 2}, readable=False),
        ]
        topics = summarize_ward_topics(
            window_items,
            ["parks", "zoning", "schools"],
            {"schools": {"1", "2", "3"}},
            top_n=2,
        )
        self.assertEqual(
            topics,
            [
                {"id": "schools", "newsletters": 2, "city_wards": 3},
                {"id": "parks", "newsletters": 1, "city_wards": 0},
            ],
        )


class TestSelectRecentTerms(unittest.TestCase):
    def test_drops_non_topical_and_overlapping_terms(self):
        self.assertTrue(is_non_topical_term("5th ward"))
        self.assertTrue(is_non_topical_term("warm regards"))
        self.assertFalse(is_non_topical_term("wicker park"))

        documents = [
            doc("a", "1", "2026-09", {"wicker park", "wicker", "1st ward", "budget"}),
            doc("b", "2", "2026-09", {"budget"}),
        ]
        terms = select_recent_terms(
            documents,
            {"wicker park", "wicker", "1st ward", "budget"},
            name_tokens_by_ward={},
            settings=SETTINGS,
        )
        self.assertEqual(len(terms["1"]), 1)
        self.assertIn(terms["1"][0], {"wicker park", "wicker"})
        self.assertEqual(terms.get("2", []), [])


class TestBuildWardGlances(unittest.TestCase):
    def test_describes_each_ward_with_newsletters_over_the_window(self):
        items = [
            item("old", "1", date(2026, 3, 1), {"schools": 2}),
            item("a", "1", date(2026, 8, 1), {"schools": 2}),
            item("b", "1", date(2026, 9, 1), {"schools": 2}),
            item("c", "2", date(2026, 9, 1), {"parks": 2}),
            item("d", "3", date(2026, 9, 1), readable=False),
        ]
        glance = build_ward_glances(
            items, [], set(), ["schools", "parks"], {}, "2026-09", SETTINGS
        )
        self.assertEqual(glance["window_months"], ["2026-07", "2026-08", "2026-09"])
        # Ward 3's only newsletter was unreadable, so it is not in the denominator.
        self.assertEqual(glance["city_readable_wards"], 2)
        self.assertEqual(set(glance["wards"]), {"1", "2", "3"})

        ward_one = glance["wards"]["1"]
        self.assertEqual(ward_one["first_date"], "2026-03-01")
        self.assertEqual(ward_one["newsletters"], 3)
        self.assertEqual(ward_one["recent_months"], [0, 1, 1])
        self.assertEqual(ward_one["per_month"], 0.7)
        self.assertEqual(ward_one["topic_newsletters"], 2)
        self.assertEqual(
            ward_one["topics"], [{"id": "schools", "newsletters": 2, "city_wards": 1}]
        )
        self.assertEqual(glance["wards"]["3"]["topics"], [])
        self.assertEqual(glance["wards"]["3"]["topic_newsletters"], 0)


if __name__ == "__main__":
    unittest.main()
