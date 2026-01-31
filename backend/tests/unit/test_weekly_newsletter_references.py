"""
Unit tests for referenced newsletters in weekly digest emails.
"""

import unittest
from unittest.mock import MagicMock, patch

from notifications.email_sender import (
    _fetch_newsletter_details,
    _prepare_weekly_report_data,
    _render_weekly_content_html,
    _render_weekly_content_text,
)


class TestFetchNewsletterDetails(unittest.TestCase):
    """Tests for _fetch_newsletter_details() function."""

    @patch("notifications.email_sender.get_supabase_client")
    def test_fetches_and_sorts_by_ward(self, mock_get_client):
        """Fetches newsletter details and sorts by ward number."""
        # Arrange
        mock_supabase = MagicMock()
        mock_get_client.return_value = mock_supabase

        mock_response = MagicMock()
        mock_response.data = [
            {
                "id": "nl-3",
                "subject": "Ward 48 Newsletter",
                "received_date": "2026-01-24T00:00:00Z",
                "source": {"ward_number": 48},
            },
            {
                "id": "nl-1",
                "subject": "Ward 40 Newsletter",
                "received_date": "2026-01-20T00:00:00Z",
                "source": {"ward_number": 40},
            },
            {
                "id": "nl-2",
                "subject": "Ward 43 Newsletter",
                "received_date": "2026-01-22T00:00:00Z",
                "source": {"ward_number": 43},
            },
        ]

        mock_supabase.table.return_value.select.return_value.in_.return_value.execute.return_value = mock_response

        # Act
        result = _fetch_newsletter_details(["nl-1", "nl-2", "nl-3"])

        # Assert
        self.assertEqual(len(result), 3)
        # Should be sorted by ward number
        self.assertEqual(result[0]["ward_number"], 40)
        self.assertEqual(result[1]["ward_number"], 43)
        self.assertEqual(result[2]["ward_number"], 48)

    @patch("notifications.email_sender.get_supabase_client")
    def test_handles_empty_list(self, mock_get_client):
        """Returns empty list for empty input."""
        result = _fetch_newsletter_details([])
        self.assertEqual(result, [])


class TestPrepareWeeklyReportData(unittest.TestCase):
    """Tests for _prepare_weekly_report_data() with newsletter references."""

    @patch("notifications.email_sender._fetch_newsletter_details")
    def test_includes_referenced_newsletters(self, mock_fetch):
        """Prepared data includes referenced newsletters."""
        # Arrange
        mock_fetch.return_value = [
            {
                "id": "nl-1",
                "subject": "Test Newsletter",
                "received_date": "2026-01-20T00:00:00Z",
                "ward_number": 40,
            }
        ]

        notifications = [
            {
                "report": {
                    "topic": "bike_lanes",
                    "week_id": "2026-W04",
                    "report_summary": "Test summary",
                    "newsletter_ids": ["nl-1"],
                },
                "rule": {"name": "Test Rule"},
            }
        ]

        # Act
        result = _prepare_weekly_report_data(notifications)

        # Assert
        self.assertEqual(len(result), 1)
        self.assertIn("referenced_newsletters", result[0])
        self.assertEqual(len(result[0]["referenced_newsletters"]), 1)
        self.assertEqual(result[0]["referenced_newsletters"][0]["id"], "nl-1")


class TestRenderWeeklyContentWithReferences(unittest.TestCase):
    """Tests for weekly content rendering with newsletter references."""

    def test_html_includes_referenced_section(self):
        """HTML output includes referenced newsletters section."""
        # Arrange
        prepared = [
            {
                "topic": "bike_lanes",
                "topic_display": "Bike Lanes",
                "summary": "Test summary",
                "newsletter_count": 1,
                "week_range": "Jan 20-26",
                "week_id": "2026-W04",
                "matched_rules": ["Test Rule"],
                "referenced_newsletters": [
                    {
                        "id": "nl-1",
                        "subject": "Ward 40 Updates",
                        "received_date": "2026-01-20T00:00:00Z",
                        "ward_number": 40,
                    }
                ],
            }
        ]

        # Act
        html = _render_weekly_content_html(prepared)

        # Assert
        self.assertIn("Referenced newsletters:", html)
        self.assertIn("Ward 40:", html)
        self.assertIn("Ward 40 Updates", html)
        self.assertIn("/newsletter/nl-1", html)

    def test_text_includes_referenced_section(self):
        """Plain text output includes referenced newsletters section."""
        # Arrange
        prepared = [
            {
                "topic": "bike_lanes",
                "topic_display": "Bike Lanes",
                "summary": "Test summary",
                "newsletter_count": 1,
                "week_range": "Jan 20-26",
                "week_id": "2026-W04",
                "matched_rules": ["Test Rule"],
                "referenced_newsletters": [
                    {
                        "id": "nl-1",
                        "subject": "Ward 40 Updates",
                        "received_date": "2026-01-20T00:00:00Z",
                        "ward_number": 40,
                    }
                ],
            }
        ]

        # Act
        text = _render_weekly_content_text(prepared)

        # Assert
        self.assertIn("Referenced newsletters:", text)
        self.assertIn("Ward 40:", text)
        self.assertIn("Ward 40 Updates", text)
        self.assertIn("/newsletter/nl-1", text)


if __name__ == "__main__":
    unittest.main()
