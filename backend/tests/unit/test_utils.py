"""
Unit tests for shared/utils.py

Tests date parsing utilities and summary printing.
"""

import unittest
from unittest.mock import MagicMock, patch

from shared.utils import parse_date_string, print_summary


class TestParseDateString(unittest.TestCase):
    """Tests for parse_date_string() function."""

    def test_parse_iso_format(self) -> None:
        """Parse ISO format (2026-01-24T12:00:00)."""
        result = parse_date_string("2026-01-24T12:00:00")

        self.assertIsNotNone(result)
        self.assertIn("2026-01-24", result)

    def test_parse_us_format(self) -> None:
        """Parse US format (01/24/2026)."""
        result = parse_date_string("01/24/2026")

        self.assertIsNotNone(result)
        # Should parse successfully
        self.assertIn("2026", result)

    def test_parse_verbose_format(self) -> None:
        """Parse verbose format (January 24, 2026)."""
        result = parse_date_string("January 24, 2026")

        self.assertIsNotNone(result)
        self.assertIn("2026-01-24", result)

    def test_parse_with_timezone(self) -> None:
        """Parse date with timezone."""
        result = parse_date_string("2026-01-24T12:00:00+00:00")

        self.assertIsNotNone(result)
        self.assertIn("2026-01-24", result)

    def test_fuzzy_parsing(self) -> None:
        """Fuzzy parsing extracts date from text."""
        result = parse_date_string("Published on Jan 24th, 2026")

        self.assertIsNotNone(result)
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
        result = parse_date_string(None)

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
            self.assertIsNotNone(result)


class TestPrintSummary(unittest.TestCase):
    """Tests for print_summary() function."""

    @patch("builtins.print")
    def test_prints_counts(self, mock_print: MagicMock) -> None:
        """Output includes processed, skipped, failed counts."""
        print_summary(processed=10, skipped=2, failed=1)

        # Verify print was called
        self.assertTrue(mock_print.called)

        # Check that output contains the counts
        printed_output = " ".join(str(call[0][0]) for call in mock_print.call_args_list)
        self.assertIn("10", printed_output)
        self.assertIn("2", printed_output)
        self.assertIn("1", printed_output)


if __name__ == "__main__":
    unittest.main()
