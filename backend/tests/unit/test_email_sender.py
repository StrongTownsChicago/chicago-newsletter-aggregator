"""Unit tests for notifications/email_sender.py: sending a daily digest through Resend."""

import unittest
from unittest.mock import MagicMock, patch

from notifications.digest_config import DigestType
from notifications.email_sender import send_digest
from tests.fixtures.newsletter_factory import create_test_newsletter


class TestSendDailyDigest(unittest.TestCase):
    """Tests for send_digest() with DigestType.DAILY."""

    def setUp(self) -> None:
        """Set up test environment with secret key."""
        import os

        self.original_secret = os.environ.get("UNSUBSCRIBE_SECRET_KEY")
        os.environ["UNSUBSCRIBE_SECRET_KEY"] = (
            "test-secret-key-for-testing-must-be-at-least-32-chars-long"
        )

    def tearDown(self) -> None:
        """Restore original environment."""
        import os

        if self.original_secret:
            os.environ["UNSUBSCRIBE_SECRET_KEY"] = self.original_secret
        else:
            os.environ.pop("UNSUBSCRIBE_SECRET_KEY", None)

    @patch("notifications.email_sender.resend.Emails.send")
    def test_send_success(self, mock_send: MagicMock) -> None:
        """Email sent successfully via Resend API."""
        mock_send.return_value = {"id": "email_123"}

        newsletter = create_test_newsletter()
        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = send_digest(
            "user-123", "user@example.com", notifications, DigestType.DAILY
        )

        self.assertTrue(result["success"])
        self.assertEqual(result["email_id"], "email_123")
        mock_send.assert_called_once()

    @patch("notifications.email_sender.resend.Emails.send")
    def test_send_failure(self, mock_send: MagicMock) -> None:
        """Resend API error handled gracefully."""
        mock_send.side_effect = Exception("API Error")

        newsletter = create_test_newsletter()
        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = send_digest(
            "user-123", "user@example.com", notifications, DigestType.DAILY
        )

        self.assertFalse(result["success"])
        self.assertIn("API Error", result["error"])

    def test_empty_notifications_returns_error(self) -> None:
        """Empty notifications list returns error."""
        result = send_digest("user-123", "user@example.com", [], DigestType.DAILY)

        self.assertFalse(result["success"])
        self.assertIn("No notifications", result["error"])

    @patch("notifications.email_sender.resend.Emails.send")
    def test_uses_default_preferences_url(self, mock_send: MagicMock) -> None:
        """Default preferences URL used when not provided."""
        mock_send.return_value = {"id": "email_123"}

        newsletter = create_test_newsletter()
        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        send_digest("user-123", "user@example.com", notifications, DigestType.DAILY)

        # Check that HTML contains preferences link
        call_args = mock_send.call_args[0][0]
        self.assertIn("/preferences", call_args["html"])

    @patch("notifications.email_sender.resend.Emails.send")
    def test_uses_custom_preferences_url(self, mock_send: MagicMock) -> None:
        """Custom preferences URL used when provided."""
        mock_send.return_value = {"id": "email_123"}

        newsletter = create_test_newsletter()
        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        send_digest(
            "user-123",
            "user@example.com",
            notifications,
            DigestType.DAILY,
            preferences_url="https://custom.com/prefs",
        )

        call_args = mock_send.call_args[0][0]
        self.assertIn("https://custom.com/prefs", call_args["html"])

    @patch("notifications.email_sender.resend.Emails.send")
    def test_subject_includes_count(self, mock_send: MagicMock) -> None:
        """Subject line includes newsletter count."""
        mock_send.return_value = {"id": "email_123"}

        newsletter1 = create_test_newsletter(id="nl_1")
        newsletter2 = create_test_newsletter(id="nl_2")
        notifications = [
            {"newsletter": newsletter1, "rule": {"name": "Rule 1"}},
            {"newsletter": newsletter2, "rule": {"name": "Rule 1"}},
        ]

        send_digest("user-123", "user@example.com", notifications, DigestType.DAILY)

        call_args = mock_send.call_args[0][0]
        self.assertIn("2 newsletters", call_args["subject"])

    @patch("notifications.email_sender.resend.Emails.send")
    def test_calls_resend_api(self, mock_send: MagicMock) -> None:
        """Resend API called with correct parameters."""
        mock_send.return_value = {"id": "email_123"}

        newsletter = create_test_newsletter()
        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        send_digest("user-123", "user@example.com", notifications, DigestType.DAILY)

        self.assertTrue(mock_send.called)
        call_args = mock_send.call_args[0][0]
        self.assertEqual(call_args["to"], "user@example.com")
        self.assertIn("from", call_args)
        self.assertIn("subject", call_args)
        self.assertIn("html", call_args)
        self.assertIn("text", call_args)
