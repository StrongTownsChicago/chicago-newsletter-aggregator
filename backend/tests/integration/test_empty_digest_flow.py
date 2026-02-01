"""
Integration test for the empty digest prevention flow.

Verifies that when a notification queue entry points to a missing newsletter,
the system correctly skips sending the email and marks the notification as failed.
"""

import unittest
from unittest.mock import patch, MagicMock
from notifications.process_notification_queue import process_daily_digests


class TestEmptyDigestFlow(unittest.TestCase):
    """Integration tests for end-to-end empty digest handling."""

    @patch("builtins.print")
    @patch("notifications.process_notification_queue.get_supabase_client")
    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.email_sender.resend.Emails.send")
    @patch("notifications.email_sender._build_unsubscribe_url")
    def test_empty_daily_digest_flow(
        self, mock_unsub, mock_resend, mock_sb_matcher, mock_sb_process, mock_print
    ):
        """
        Test flow where a notification in the queue references a missing newsletter.
        Expected: No email sent, status updated to failed with 'Empty digest content'.
        """
        # Arrange
        mock_sb = MagicMock()
        mock_sb_matcher.return_value = mock_sb
        mock_sb_process.return_value = mock_sb
        mock_unsub.return_value = "https://example.com/unsub"

        batch_id = "2026-01-31"
        user_id = "user_123"
        newsletter_id = "nl_999"  # Non-existent newsletter

        # 1. Mock fetch of pending notifications
        mock_queue_response = MagicMock()
        mock_queue_response.data = [
            {
                "id": "notif_1",
                "user_id": user_id,
                "newsletter_id": newsletter_id,
                "rule_id": "rule_1",
                "newsletter": None,  # Key part: newsletter is missing from join
                "rule": {"name": "Test Rule"},
            }
        ]

        # Route table calls
        mock_queue_table = MagicMock()

        # Simplify the chain mock using configure_mock or just return values
        mock_queue_table.select.return_value.eq.return_value.order.return_value.eq.return_value.execute.return_value = mock_queue_response

        # 2. Mock user profile fetch
        mock_user_response = MagicMock()
        mock_user_response.data = {
            "email": "test@example.com",
            "notification_preferences": {"enabled": True},
        }

        mock_user_table = MagicMock()
        mock_user_table.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_user_response

        # 3. Mock updates and inserts
        mock_history_table = MagicMock()

        def table_router(name):
            if name == "notification_queue":
                return mock_queue_table
            if name == "user_profiles":
                return mock_user_table
            if name == "notification_history":
                return mock_history_table
            return MagicMock()

        mock_sb.table.side_effect = table_router

        # Act
        with patch(
            "notifications.process_notification_queue.ZoneInfo"
        ):  # Avoid TZ issues
            stats = process_daily_digests(batch_id=batch_id)

        # Assert
        # Verify stats
        self.assertEqual(stats["skipped"], 1)
        self.assertEqual(stats["sent"], 0)

        # Verify Resend was NOT called
        mock_resend.assert_not_called()

        # Verify DB update to notification_queue
        mock_queue_table.update.assert_called_with(
            {"status": "failed", "error_message": "Empty digest content"}
        )

        # Verify history record
        mock_history_table.insert.assert_called_once()
        history_call_data = mock_history_table.insert.call_args[0][0]
        self.assertEqual(history_call_data["success"], False)
        self.assertEqual(history_call_data["error_message"], "Empty digest content")


if __name__ == "__main__":
    unittest.main()
