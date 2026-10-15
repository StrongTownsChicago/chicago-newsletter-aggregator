"""Unit tests for analytics/records.py parsing and date bucketing."""

import unittest
from datetime import date

from analytics.records import (
    month_key,
    parse_newsletter_row,
    parse_source_row,
    select_as_of_month,
    shift_month,
    to_chicago_date,
    ward_sort_key,
)


class TestToChicagoDate(unittest.TestCase):
    def test_converts_utc_to_chicago_calendar_date(self):
        # 03:00 UTC on Oct 1 is still Sept 30 in Chicago.
        self.assertEqual(
            to_chicago_date("2026-10-01T03:00:00+00:00"), date(2026, 9, 30)
        )

    def test_naive_timestamp_is_treated_as_local(self):
        self.assertEqual(to_chicago_date("2026-10-01T03:00:00"), date(2026, 10, 1))


class TestMonthHelpers(unittest.TestCase):
    def test_month_key(self):
        self.assertEqual(month_key(date(2026, 3, 9)), "2026-03")

    def test_shift_month_backwards_across_year(self):
        self.assertEqual(shift_month("2026-02", -3), "2025-11")

    def test_shift_month_forwards_across_year(self):
        self.assertEqual(shift_month("2025-12", 1), "2026-01")

    def test_as_of_month_is_the_current_month_for_a_fresh_snapshot(self):
        today = date(2026, 10, 14)
        self.assertEqual(select_as_of_month([date(2026, 10, 13)], today), "2026-10")
        self.assertEqual(select_as_of_month([], today), "2026-10")

    def test_as_of_month_is_the_newest_newsletter_month_for_a_stale_snapshot(self):
        dates = [date(2026, 8, 1), date(2026, 9, 15)]
        self.assertEqual(select_as_of_month(dates, date(2026, 10, 14)), "2026-09")


class TestParseRows(unittest.TestCase):
    def test_parse_source_row_blank_ward_becomes_none(self):
        source = parse_source_row(
            {"id": 7, "name": "Mayor", "ward_number": "  ", "source_type": "mayor"}
        )
        self.assertIsNone(source.ward)
        self.assertEqual(source.id, 7)

    def test_parse_source_row_keeps_ward(self):
        source = parse_source_row(
            {"id": 1, "name": "A", "ward_number": "32", "source_type": "alderman"}
        )
        self.assertEqual(source.ward, "32")

    def test_parse_newsletter_row_handles_missing_optional_fields(self):
        newsletter = parse_newsletter_row(
            {
                "id": "abc",
                "received_date": "2026-01-05T12:00:00+00:00",
                "source_id": 3,
                "subject": None,
                "plain_text": None,
            }
        )
        self.assertEqual(newsletter.received_date, date(2026, 1, 5))
        self.assertEqual(newsletter.subject, "")
        self.assertEqual(newsletter.plain_text, "")


class TestWardSortKey(unittest.TestCase):
    def test_numeric_wards_sort_numerically_before_labels(self):
        self.assertEqual(
            sorted(["10", "Citywide", "2", "1"], key=ward_sort_key),
            ["1", "2", "10", "Citywide"],
        )


if __name__ == "__main__":
    unittest.main()
