"""Unit tests for ingest/summary.py"""

import unittest
from unittest.mock import MagicMock, patch

from ingest.summary import print_summary


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
