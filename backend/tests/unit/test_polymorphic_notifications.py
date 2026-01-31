"""
Unit tests for polymorphic notification queue functionality.

Tests the ability of notification_queue to handle both newsletters (daily)
and weekly topic reports (weekly) using dedicated newsletter_id and report_id columns.
"""

import sys
import io
import unittest
from unittest.mock import patch, Mock
from notifications.process_notification_queue import _extract_content_ids


class TestExtractContentIds(unittest.TestCase):
    """Tests for _extract_content_ids() helper function."""

    def test_extracts_newsletter_ids_from_daily_notifications(self):
        """Extracts newsletter_id from daily notifications."""
        # Arrange
        notifications = [
            {"id": "notif-1", "newsletter_id": "nl-1", "rule_id": "rule-1"},
            {"id": "notif-2", "newsletter_id": "nl-2", "rule_id": "rule-1"},
        ]

        # Act
        result = _extract_content_ids(notifications)

        # Assert
        self.assertEqual(len(result), 2)
        self.assertIn("nl-1", result)
        self.assertIn("nl-2", result)

    def test_extracts_report_ids_from_weekly_notifications(self):
        """Extracts report_id from weekly notifications."""
        # Arrange
        notifications = [
            {"id": "notif-1", "report_id": "report-1", "rule_id": "rule-1"},
            {"id": "notif-2", "report_id": "report-2", "rule_id": "rule-1"},
        ]

        # Act
        result = _extract_content_ids(notifications)

        # Assert
        self.assertEqual(len(result), 2)
        self.assertIn("report-1", result)
        self.assertIn("report-2", result)

    def test_handles_mixed_notifications_with_none_values(self):
        """Handles notifications with None values for unused ID field."""
        # Arrange - Weekly notification has newsletter_id=None
        notifications = [
            {
                "id": "notif-1",
                "newsletter_id": "nl-1",
                "report_id": None,
                "rule_id": "rule-1",
            },
            {
                "id": "notif-2",
                "newsletter_id": None,
                "report_id": "report-1",
                "rule_id": "rule-2",
            },
        ]

        # Act
        result = _extract_content_ids(notifications)

        # Assert
        self.assertEqual(len(result), 2)
        self.assertIn("nl-1", result)
        self.assertIn("report-1", result)

    def test_deduplicates_identical_ids(self):
        """Returns unique IDs when multiple notifications reference same content."""
        # Arrange
        notifications = [
            {"id": "notif-1", "newsletter_id": "nl-1", "rule_id": "rule-1"},
            {"id": "notif-2", "newsletter_id": "nl-1", "rule_id": "rule-2"},
            {"id": "notif-3", "newsletter_id": "nl-2", "rule_id": "rule-1"},
        ]

        # Act
        result = _extract_content_ids(notifications)

        # Assert
        self.assertEqual(len(result), 2)
        self.assertIn("nl-1", result)
        self.assertIn("nl-2", result)

    def test_handles_empty_list(self):
        """Returns empty list when given empty notifications."""
        # Act
        result = _extract_content_ids([])

        # Assert
        self.assertEqual(result, [])

    def test_skips_notifications_missing_both_ids(self):
        """Gracefully handles malformed notifications missing both IDs."""
        # Arrange - Edge case that shouldn't happen due to DB constraint
        notifications = [
            {"id": "notif-1", "newsletter_id": "nl-1", "rule_id": "rule-1"},
            {"id": "notif-bad", "rule_id": "rule-2"},  # Missing both IDs
        ]

        # Act
        result = _extract_content_ids(notifications)

        # Assert
        self.assertEqual(len(result), 1)
        self.assertIn("nl-1", result)


class TestWeeklyNotificationQueuing(unittest.TestCase):
    """Tests for weekly notification queuing with report_id."""

    def setUp(self):
        """Suppress print output during tests."""
        self.held_output = io.StringIO()
        sys.stdout = self.held_output

    def tearDown(self):
        """Restore stdout."""
        sys.stdout = sys.__stdout__

    @patch("notifications.weekly_notification_queue.get_supabase_client")
    def test_queues_with_report_id_column(self, mock_get_client):
        """Weekly notifications use report_id column, not newsletter_id."""
        from notifications.weekly_notification_queue import queue_weekly_notifications

        # Arrange
        mock_supabase = Mock()
        mock_get_client.return_value = mock_supabase

        # Mock users with weekly rules
        mock_rules_response = Mock()
        mock_rules_response.data = [
            {"id": "rule-1", "user_id": "user-1", "topics": ["bike_lanes"]},
        ]

        # Mock user profiles (notifications enabled)
        mock_profiles_response = Mock()
        mock_profiles_response.data = [
            {
                "id": "user-1",
                "notification_preferences": {"enabled": True},
            }
        ]

        # Mock reports for the week
        mock_reports_response = Mock()
        mock_reports_response.data = [
            {"id": "report-1", "topic": "bike_lanes", "week_id": "2026-W05"}
        ]

        # Track insert calls
        insert_calls = []

        # Setup mock chain for multiple queries
        def table_side_effect(table_name):
            if table_name == "notification_rules":
                return Mock(
                    select=Mock(
                        return_value=Mock(
                            eq=Mock(
                                return_value=Mock(
                                    eq=Mock(
                                        return_value=Mock(
                                            execute=Mock(
                                                return_value=mock_rules_response
                                            )
                                        )
                                    )
                                )
                            )
                        )
                    )
                )
            elif table_name == "user_profiles":
                return Mock(
                    select=Mock(
                        return_value=Mock(
                            in_=Mock(
                                return_value=Mock(
                                    execute=Mock(return_value=mock_profiles_response)
                                )
                            )
                        )
                    )
                )
            elif table_name == "weekly_topic_reports":
                return Mock(
                    select=Mock(
                        return_value=Mock(
                            eq=Mock(
                                return_value=Mock(
                                    execute=Mock(return_value=mock_reports_response)
                                )
                            )
                        )
                    )
                )
            elif table_name == "notification_queue":
                # Mock insert and track calls
                def track_insert(data):
                    insert_calls.append(data)
                    return Mock(execute=Mock(return_value=Mock()))

                return Mock(insert=track_insert)

        mock_supabase.table.side_effect = table_side_effect

        # Act
        result = queue_weekly_notifications("2026-W05")

        # Assert
        self.assertEqual(result["queued"], 1)
        self.assertEqual(len(insert_calls), 1, "Should have one insert call")

        # Verify the inserted data uses report_id
        inserted_data = insert_calls[0]
        self.assertIn("report_id", inserted_data)
        self.assertEqual(inserted_data["report_id"], "report-1")
        self.assertNotIn("newsletter_id", inserted_data)


class TestWeeklyNotificationFetching(unittest.TestCase):
    """Tests for fetching weekly notifications with proper joins."""

    @patch("notifications.process_notification_queue.get_supabase_client")
    def test_fetches_with_report_join(self, mock_get_client):
        """Weekly notification fetching joins to weekly_topic_reports via report_id."""
        from notifications.process_notification_queue import _fetch_weekly_notifications

        # Arrange
        mock_supabase = Mock()
        mock_get_client.return_value = mock_supabase

        mock_response = Mock()
        mock_response.data = [
            {
                "id": "notif-1",
                "user_id": "user-1",
                "report_id": "report-1",
                "rule_id": "rule-1",
                "report": {
                    "id": "report-1",
                    "topic": "bike_lanes",
                    "week_id": "2026-W05",
                    "report_summary": "Test summary",
                    "newsletter_ids": ["nl-1", "nl-2"],
                },
                "rule": {"name": "Test Rule"},
            }
        ]

        # Setup mock chain
        mock_supabase.table.return_value.select.return_value.eq.return_value.eq.return_value.eq.return_value.execute.return_value = mock_response

        # Act
        result = _fetch_weekly_notifications("2026-W05")

        # Assert
        self.assertEqual(len(result), 1)
        self.assertIn("user-1", result)
        self.assertEqual(len(result["user-1"]), 1)

        notification = result["user-1"][0]
        self.assertEqual(notification["report_id"], "report-1")
        self.assertIn("report", notification)
        self.assertEqual(notification["report"]["topic"], "bike_lanes")

        # Verify select used report_id and joined to weekly_topic_reports
        select_call = mock_supabase.table.return_value.select.call_args
        select_string = select_call[0][0]
        self.assertIn("report_id", select_string)
        self.assertIn("report:weekly_topic_reports", select_string)


if __name__ == "__main__":
    unittest.main()
