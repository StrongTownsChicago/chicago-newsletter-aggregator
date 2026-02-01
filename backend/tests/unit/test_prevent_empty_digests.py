"""
Unit tests for preventing empty digest emails.

Tests that send_digest returns an error when no content is available after
preparation, and that process_digests handles this error by skipping.
"""

import unittest
from unittest.mock import patch, MagicMock
from notifications.email_sender import send_digest, DigestType
from notifications.process_notification_queue import process_digests


class TestPreventEmptyDigests(unittest.TestCase):
    """Tests for empty digest prevention logic."""

    @patch("notifications.email_sender._prepare_newsletter_data")
    @patch("notifications.email_sender._build_unsubscribe_url")
    def test_send_digest_empty_daily(self, mock_unsub, mock_prepare):
        """send_digest returns error when daily preparation results in no content."""
        # Arrange
        mock_prepare.return_value = []
        mock_unsub.return_value = "https://example.com/unsub"
        notifications = [{"id": "notif_1", "newsletter_id": "nl_1"}]

        # Act
        result = send_digest(
            user_id="user_123",
            user_email="test@example.com",
            notifications=notifications,
            digest_type=DigestType.DAILY,
        )

        # Assert
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Empty digest content")
        mock_prepare.assert_called_once()

    @patch("notifications.email_sender._prepare_weekly_report_data")
    @patch("notifications.email_sender._build_unsubscribe_url")
    def test_send_digest_empty_weekly(self, mock_unsub, mock_prepare):
        """send_digest returns error when weekly preparation results in no content."""
        # Arrange
        mock_prepare.return_value = []
        mock_unsub.return_value = "https://example.com/unsub"
        notifications = [{"id": "notif_1", "report_id": "rep_1"}]

        # Act
        result = send_digest(
            user_id="user_123",
            user_email="test@example.com",
            notifications=notifications,
            digest_type=DigestType.WEEKLY,
        )

        # Assert
        self.assertFalse(result["success"])
        self.assertEqual(result["error"], "Empty digest content")
        mock_prepare.assert_called_once()

    @patch("builtins.print")
    @patch("notifications.process_notification_queue.get_supabase_client")
    @patch("notifications.process_notification_queue.send_digest")
    def test_process_digests_handles_empty_result(
        self, mock_send, mock_supabase, mock_print
    ):
        """process_digests increments skipped stat and updates DB for empty content."""
        # Arrange
        mock_sb = MagicMock()
        mock_supabase.return_value = mock_sb

        # Mock notifications by user fetch
        config_mock = MagicMock()
        config_mock.fetch_notifications.return_value = {
            "user_123": [
                {"id": "notif_1", "rule_id": "rule_1", "newsletter_id": "nl_1"}
            ]
        }
        config_mock.batch_id_calculator.return_value = "2026-01-31"
        config_mock.digest_type = DigestType.DAILY
        config_mock.delivery_type = "daily_digest"

        # Mock user profile fetch
        mock_sb.table().select().eq().single().execute.return_value.data = {
            "email": "test@example.com",
            "notification_preferences": {"enabled": True},
        }

        # Mock send_digest to return empty error
        mock_send.return_value = {"success": False, "error": "Empty digest content"}

        # Patch the DIGEST_CONFIGS to use our mock
        with patch(
            "notifications.process_notification_queue.DIGEST_CONFIGS",
            {DigestType.DAILY: config_mock},
        ):
            # Act
            stats = process_digests(DigestType.DAILY, batch_id="2026-01-31")

            # Assert
            self.assertEqual(stats["skipped"], 1)
            self.assertEqual(stats["sent"], 0)
            self.assertEqual(stats["failed"], 0)

            # Verify notification_queue was updated with error
            mock_sb.table.assert_any_call("notification_queue")
            mock_sb.table().update.assert_called_with(
                {"status": "failed", "error_message": "Empty digest content"}
            )

            # Verify notification_history was recorded
            mock_sb.table.assert_any_call("notification_history")
            mock_sb.table().insert.assert_called()
            history_data = mock_sb.table().insert.call_args[0][0]
            self.assertEqual(history_data["success"], False)
            self.assertEqual(history_data["error_message"], "Empty digest content")


if __name__ == "__main__":
    unittest.main()
