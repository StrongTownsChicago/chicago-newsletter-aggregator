"""
Unit tests for referenced newsletters in weekly digest emails.
"""

import unittest
from typing import Any
from unittest.mock import MagicMock, patch

from notifications.digest_data import (
    fetch_newsletter_details,
    prepare_weekly_report_data,
)
from notifications.digest_html import _render_weekly_content_html
from notifications.digest_text import _render_weekly_content_text


class TestFetchNewsletterDetails(unittest.TestCase):
    """Tests for fetch_newsletter_details() function."""

    @patch("notifications.digest_data.get_supabase_client")
    def test_fetches_and_sorts_by_ward(self, mock_get_client: MagicMock) -> None:
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
        result = fetch_newsletter_details(["nl-1", "nl-2", "nl-3"])

        # Assert
        self.assertEqual(len(result), 3)
        # Should be sorted by ward number
        self.assertEqual(result[0]["ward_number"], 40)
        self.assertEqual(result[1]["ward_number"], 43)
        self.assertEqual(result[2]["ward_number"], 48)

    @patch("notifications.digest_data.get_supabase_client")
    def test_handles_empty_list(self, mock_get_client: MagicMock) -> None:
        """Returns empty list for empty input."""
        result = fetch_newsletter_details([])
        self.assertEqual(result, [])

    @patch("notifications.digest_data.get_supabase_client")
    def test_citywide_newsletters_come_after_ward_newsletters(
        self, mock_get_client: MagicMock
    ) -> None:
        query = mock_get_client.return_value.table.return_value.select.return_value
        query.in_.return_value.execute.return_value.data = [
            {"id": "c", "subject": "s", "received_date": "d", "source": None},
            {
                "id": "w",
                "subject": "s",
                "received_date": "d",
                "source": {"ward_number": 50},
            },
            {"id": "x", "subject": "s", "received_date": "d", "source": "not a dict"},
            {
                "id": "v",
                "subject": "s",
                "received_date": "d",
                "source": {"ward_number": 1},
            },
        ]

        result = fetch_newsletter_details(["c", "w", "x", "v"])

        self.assertEqual([nl["id"] for nl in result], ["v", "w", "c", "x"])
        self.assertEqual([nl["ward_number"] for nl in result], [1, 50, None, None])

    @patch("notifications.digest_data.get_supabase_client")
    def test_a_failed_query_returns_no_newsletters(
        self, mock_get_client: MagicMock
    ) -> None:
        mock_get_client.return_value.table.side_effect = RuntimeError("down")

        with self.assertLogs("notifications.digest_data", level="WARNING"):
            self.assertEqual(fetch_newsletter_details(["nl-1"]), [])


class TestPrepareWeeklyReportData(unittest.TestCase):
    """Tests for prepare_weekly_report_data() with newsletter references."""

    @patch("notifications.digest_data.fetch_newsletter_details")
    def test_includes_referenced_newsletters(self, mock_fetch: MagicMock) -> None:
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
        result = prepare_weekly_report_data(notifications)

        # Assert
        self.assertEqual(len(result), 1)
        self.assertIn("referenced_newsletters", result[0])
        self.assertEqual(len(result[0]["referenced_newsletters"]), 1)
        self.assertEqual(result[0]["referenced_newsletters"][0]["id"], "nl-1")


def weekly_notification(
    topic: str, rule: dict[str, str] | None, newsletter_ids: list[str] | None = None
) -> dict[str, Any]:
    return {
        "report": {
            "topic": topic,
            "week_id": "2026-W04",
            "report_summary": f"{topic} summary",
            "newsletter_ids": newsletter_ids,
        },
        "rule": rule,
    }


@patch("notifications.digest_data.fetch_newsletter_details", return_value=[])
class TestPrepareWeeklyReportGrouping(unittest.TestCase):
    def test_reports_are_sorted_by_topic(self, _fetch: MagicMock) -> None:
        notifications = [
            weekly_notification("zoning", {"name": "Z"}),
            weekly_notification("bike_lanes", {"name": "B"}),
        ]

        result = prepare_weekly_report_data(notifications)

        self.assertEqual(
            [report["topic"] for report in result], ["bike_lanes", "zoning"]
        )

    def test_each_rule_is_listed_once_per_topic(self, _fetch: MagicMock) -> None:
        notifications = [
            weekly_notification("zoning", {"name": "Housing"}),
            weekly_notification("zoning", {"name": "Housing"}),
            weekly_notification("zoning", {"name": "Land use"}),
        ]

        result = prepare_weekly_report_data(notifications)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["matched_rules"], ["Housing", "Land use"])

    def test_a_missing_rule_is_named_unknown(self, _fetch: MagicMock) -> None:
        result = prepare_weekly_report_data(
            [weekly_notification("zoning", None), weekly_notification("zoning", {})]
        )

        self.assertEqual(result[0]["matched_rules"], ["Unknown Rule"])

    def test_counts_the_reports_newsletters(self, _fetch: MagicMock) -> None:
        result = prepare_weekly_report_data(
            [
                weekly_notification("bike_lanes", {"name": "B"}, ["a", "b"]),
                weekly_notification("zoning", {"name": "Z"}, None),
            ]
        )

        self.assertEqual([report["newsletter_count"] for report in result], [2, 0])

    def test_records_without_a_report_or_topic_are_skipped(
        self, _fetch: MagicMock
    ) -> None:
        notifications: list[dict[str, Any]] = [
            {"report": None, "rule": {"name": "R"}},
            {"report": {"topic": ""}, "rule": {"name": "R"}},
            weekly_notification("zoning", {"name": "Z"}),
        ]

        result = prepare_weekly_report_data(notifications)

        self.assertEqual([report["topic"] for report in result], ["zoning"])
        self.assertEqual(result[0]["week_range"], "January 19 - 25, 2026")


class TestRenderWeeklyContentWithReferences(unittest.TestCase):
    """Tests for weekly content rendering with newsletter references."""

    def test_html_includes_referenced_section(self) -> None:
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
        # Midnight UTC on January 20 is the evening of January 19 in Chicago.
        self.assertIn("January 19, 2026", html)

    def test_text_includes_referenced_section(self) -> None:
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
        # Midnight UTC on January 20 is the evening of January 19 in Chicago.
        self.assertIn("January 19, 2026", text)


if __name__ == "__main__":
    unittest.main()
