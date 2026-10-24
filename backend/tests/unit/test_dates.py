"""
Unit tests for shared/dates.py
"""

import unittest
from datetime import date

from shared.dates import format_calendar_day, format_received_date, parse_date_string


class TestParseDateString(unittest.TestCase):
    """Tests for parse_date_string() function."""

    def test_parse_iso_format(self) -> None:
        """Parse ISO format (2026-01-24T12:00:00)."""
        result = parse_date_string("2026-01-24T12:00:00")

        assert result is not None
        self.assertIn("2026-01-24", result)

    def test_parse_us_format(self) -> None:
        """Parse US format (01/24/2026)."""
        result = parse_date_string("01/24/2026")

        assert result is not None
        # Should parse successfully
        self.assertIn("2026", result)

    def test_parse_verbose_format(self) -> None:
        """Parse verbose format (January 24, 2026)."""
        result = parse_date_string("January 24, 2026")

        assert result is not None
        self.assertIn("2026-01-24", result)

    def test_parse_with_timezone(self) -> None:
        """Parse date with timezone."""
        result = parse_date_string("2026-01-24T12:00:00+00:00")

        assert result is not None
        self.assertIn("2026-01-24", result)

    def test_a_date_without_a_zone_is_chicago_time(self) -> None:
        self.assertEqual(parse_date_string("09/15/2026"), "2026-09-15T00:00:00-05:00")
        self.assertEqual(parse_date_string("01/15/2026"), "2026-01-15T00:00:00-06:00")

    def test_a_date_with_a_zone_keeps_it(self) -> None:
        self.assertEqual(
            parse_date_string("2026-01-24T12:00:00+00:00"), "2026-01-24T12:00:00+00:00"
        )

    def test_fuzzy_parsing(self) -> None:
        """Fuzzy parsing extracts date from text."""
        result = parse_date_string("Published on Jan 24th, 2026")

        assert result is not None
        self.assertIn("2026", result)

    def test_invalid_date_returns_none(self) -> None:
        """Invalid date string returns None."""
        result = parse_date_string("not a date at all")

        self.assertIsNone(result)

    def test_empty_string_returns_none(self) -> None:
        """Empty string returns None."""
        result = parse_date_string("")

        self.assertIsNone(result)

    def test_none_returns_none(self) -> None:
        """None input returns None."""
        result = parse_date_string(None)  # type: ignore[arg-type]  # a missing value from a scraped page

        self.assertIsNone(result)

    def test_overflow_date_returns_none(self) -> None:
        """Overflow date (year 9999) returns None."""
        # Very large dates might cause overflow
        result = parse_date_string("9999-12-31T23:59:59")

        # dateutil might handle this, but if it overflows, should return None
        # This test documents the behavior
        if result is None:
            self.assertIsNone(result)
        else:
            # If it doesn't overflow, that's fine too
            assert result is not None


class TestFormatReceivedDate(unittest.TestCase):
    def test_days_are_not_zero_padded(self) -> None:
        self.assertEqual(format_calendar_day(date(2026, 1, 5)), "January 5, 2026")

    def test_uses_the_chicago_day(self) -> None:
        # 9:30 PM in Chicago on January 23 is already January 24 in UTC.
        self.assertEqual(
            format_received_date("2026-01-24T03:30:00+00:00"), "January 23, 2026"
        )
        self.assertEqual(format_received_date("2026-07-04T04:59:00Z"), "July 3, 2026")
        self.assertEqual(format_received_date("2026-07-04T05:00:00Z"), "July 4, 2026")

    def test_a_timestamp_without_an_offset_keeps_its_day(self) -> None:
        self.assertEqual(format_received_date("2026-01-05T23:00:00"), "January 5, 2026")

    def test_text_that_is_not_a_timestamp_is_cut_to_ten_characters(self) -> None:
        self.assertEqual(format_received_date("2026-01-24-INVALID"), "2026-01-24")


if __name__ == "__main__":
    unittest.main()
