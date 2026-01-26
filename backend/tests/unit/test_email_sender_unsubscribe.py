"""
Unit tests for email sender unsubscribe functionality.
"""

import os
import unittest
from unittest.mock import patch
from notifications.email_sender import (
    send_daily_digest,
    _build_unsubscribe_url,
)
from notifications.unsubscribe_tokens import validate_unsubscribe_token


class TestEmailSenderUnsubscribe(unittest.TestCase):
    """Test email sending with unsubscribe functionality."""

    def setUp(self):
        """Set up test environment."""
        self.original_secret = os.environ.get("UNSUBSCRIBE_SECRET_KEY")
        os.environ["UNSUBSCRIBE_SECRET_KEY"] = (
            "test-secret-key-for-testing-must-be-at-least-32-chars-long"
        )
        self.original_base_url = os.environ.get("FRONTEND_BASE_URL")
        os.environ["FRONTEND_BASE_URL"] = "https://test.example.com"

    def tearDown(self):
        """Restore original environment."""
        if self.original_secret:
            os.environ["UNSUBSCRIBE_SECRET_KEY"] = self.original_secret
        else:
            os.environ.pop("UNSUBSCRIBE_SECRET_KEY", None)

        if self.original_base_url:
            os.environ["FRONTEND_BASE_URL"] = self.original_base_url
        else:
            os.environ.pop("FRONTEND_BASE_URL", None)

    def test_build_unsubscribe_url_includes_valid_token(self):
        """Test that URL contains properly formatted token."""
        user_id = "test-user-123"
        url = _build_unsubscribe_url(user_id)

        # Check URL structure
        self.assertTrue(url.startswith("https://test.example.com"))
        self.assertIn("/unsubscribe", url)
        self.assertIn("?token=", url)

        # Extract and validate token
        token = url.split("?token=")[1]
        self.assertGreater(len(token), 0)
        # Token should have JWT format (header.payload.signature)
        self.assertEqual(token.count("."), 2)

        # Validate extracted token
        validated_user_id = validate_unsubscribe_token(token)
        self.assertEqual(validated_user_id, user_id)

    @patch("notifications.email_sender.resend")
    def test_send_daily_digest_requires_user_id_parameter(self, mock_resend):
        """Test that function signature includes user_id."""
        # Create test notification data
        notifications = [
            {
                "id": "notif-1",
                "newsletter": {
                    "id": "news-1",
                    "subject": "Test Newsletter",
                    "received_date": "2026-01-25T10:00:00Z",
                    "source": {"name": "Test Source", "ward_number": "1"},
                },
                "rule": {"name": "Test Rule"},
            }
        ]

        # Attempt to call without user_id should fail
        with self.assertRaises(TypeError):
            send_daily_digest(
                user_email="test@example.com", notifications=notifications
            )

    @patch("notifications.email_sender.resend")
    def test_send_daily_digest_includes_list_unsubscribe_header(self, mock_resend):
        """Test that email includes List-Unsubscribe header."""
        # Mock Resend response
        mock_resend.Emails.send.return_value = {"id": "email-123"}

        # Create test notification
        notifications = [
            {
                "id": "notif-1",
                "newsletter": {
                    "id": "news-1",
                    "subject": "Test Newsletter",
                    "received_date": "2026-01-25T10:00:00Z",
                    "source": {"name": "Test Source", "ward_number": "1"},
                },
                "rule": {"name": "Test Rule"},
            }
        ]

        # Send digest
        result = send_daily_digest(
            user_id="test-user-456",
            user_email="test@example.com",
            notifications=notifications,
        )

        # Verify email was sent
        self.assertTrue(result["success"])
        mock_resend.Emails.send.assert_called_once()

        # Extract call arguments
        call_args = mock_resend.Emails.send.call_args[0][0]

        # Verify headers present
        self.assertIn("headers", call_args)
        self.assertIn("List-Unsubscribe", call_args["headers"])

        # Verify List-Unsubscribe format
        list_unsub = call_args["headers"]["List-Unsubscribe"]
        self.assertTrue(list_unsub.startswith("<https://"))
        self.assertTrue(list_unsub.endswith(">"))
        self.assertIn("/unsubscribe?token=", list_unsub)

    @patch("notifications.email_sender.resend")
    def test_send_daily_digest_includes_list_unsubscribe_post_header(self, mock_resend):
        """Test that email includes List-Unsubscribe-Post header."""
        mock_resend.Emails.send.return_value = {"id": "email-123"}

        notifications = [
            {
                "id": "notif-1",
                "newsletter": {
                    "id": "news-1",
                    "subject": "Test Newsletter",
                    "received_date": "2026-01-25T10:00:00Z",
                    "source": {"name": "Test Source", "ward_number": "1"},
                },
                "rule": {"name": "Test Rule"},
            }
        ]

        result = send_daily_digest(
            user_id="test-user-789",
            user_email="test@example.com",
            notifications=notifications,
        )

        self.assertTrue(result["success"])

        # Extract call arguments
        call_args = mock_resend.Emails.send.call_args[0][0]

        # Verify List-Unsubscribe-Post header
        self.assertIn("List-Unsubscribe-Post", call_args["headers"])
        self.assertEqual(
            call_args["headers"]["List-Unsubscribe-Post"],
            "List-Unsubscribe=One-Click",
        )

    @patch("notifications.email_sender.resend")
    def test_send_daily_digest_includes_unsubscribe_link_in_html_body(
        self, mock_resend
    ):
        """Test that HTML body contains clickable unsubscribe link."""
        mock_resend.Emails.send.return_value = {"id": "email-123"}

        notifications = [
            {
                "id": "notif-1",
                "newsletter": {
                    "id": "news-1",
                    "subject": "Test Newsletter",
                    "received_date": "2026-01-25T10:00:00Z",
                    "source": {"name": "Test Source", "ward_number": "1"},
                },
                "rule": {"name": "Test Rule"},
            }
        ]

        result = send_daily_digest(
            user_id="test-user-html",
            user_email="test@example.com",
            notifications=notifications,
        )

        self.assertTrue(result["success"])

        # Extract HTML body
        call_args = mock_resend.Emails.send.call_args[0][0]
        html_body = call_args["html"]

        # Verify unsubscribe link present
        self.assertIn("href=", html_body)
        self.assertIn("/unsubscribe?token=", html_body)
        self.assertIn("Unsubscribe</a>", html_body)

    @patch("notifications.email_sender.resend")
    def test_send_daily_digest_includes_unsubscribe_link_in_text_body(
        self, mock_resend
    ):
        """Test that plain text body contains unsubscribe URL."""
        mock_resend.Emails.send.return_value = {"id": "email-123"}

        notifications = [
            {
                "id": "notif-1",
                "newsletter": {
                    "id": "news-1",
                    "subject": "Test Newsletter",
                    "received_date": "2026-01-25T10:00:00Z",
                    "source": {"name": "Test Source", "ward_number": "1"},
                },
                "rule": {"name": "Test Rule"},
            }
        ]

        result = send_daily_digest(
            user_id="test-user-text",
            user_email="test@example.com",
            notifications=notifications,
        )

        self.assertTrue(result["success"])

        # Extract text body
        call_args = mock_resend.Emails.send.call_args[0][0]
        text_body = call_args["text"]

        # Verify unsubscribe URL present
        self.assertIn("Unsubscribe: https://", text_body)
        self.assertIn("/unsubscribe?token=", text_body)

    @patch("notifications.email_sender.resend")
    def test_send_daily_digest_unsubscribe_url_uses_frontend_base_url(
        self, mock_resend
    ):
        """Test that URL respects FRONTEND_BASE_URL env var."""
        # Set custom base URL
        os.environ["FRONTEND_BASE_URL"] = "https://custom.domain.com"

        mock_resend.Emails.send.return_value = {"id": "email-123"}

        notifications = [
            {
                "id": "notif-1",
                "newsletter": {
                    "id": "news-1",
                    "subject": "Test Newsletter",
                    "received_date": "2026-01-25T10:00:00Z",
                    "source": {"name": "Test Source", "ward_number": "1"},
                },
                "rule": {"name": "Test Rule"},
            }
        ]

        result = send_daily_digest(
            user_id="test-user-baseurl",
            user_email="test@example.com",
            notifications=notifications,
        )

        self.assertTrue(result["success"])

        # Extract headers
        call_args = mock_resend.Emails.send.call_args[0][0]
        list_unsub = call_args["headers"]["List-Unsubscribe"]

        # Verify custom base URL used
        self.assertIn("https://custom.domain.com", list_unsub)

    def test_send_daily_digest_token_generation_failure_propagates_error(self):
        """Test that token generation failure causes email sending to fail."""
        # Remove secret key to trigger failure
        os.environ.pop("UNSUBSCRIBE_SECRET_KEY", None)

        notifications = [
            {
                "id": "notif-1",
                "newsletter": {
                    "id": "news-1",
                    "subject": "Test Newsletter",
                    "received_date": "2026-01-25T10:00:00Z",
                    "source": {"name": "Test Source", "ward_number": "1"},
                },
                "rule": {"name": "Test Rule"},
            }
        ]

        result = send_daily_digest(
            user_id="test-user-fail",
            user_email="test@example.com",
            notifications=notifications,
        )

        # Email sending should fail
        self.assertFalse(result["success"])
        self.assertIn("error", result)
        # Error message should mention the secret key issue
        self.assertIn("UNSUBSCRIBE_SECRET_KEY", result["error"])

    @patch("notifications.email_sender.resend")
    def test_html_footer_format_matches_existing_style(self, mock_resend):
        """Test that unsubscribe link matches existing email design."""
        mock_resend.Emails.send.return_value = {"id": "email-123"}

        notifications = [
            {
                "id": "notif-1",
                "newsletter": {
                    "id": "news-1",
                    "subject": "Test Newsletter",
                    "received_date": "2026-01-25T10:00:00Z",
                    "source": {"name": "Test Source", "ward_number": "1"},
                },
                "rule": {"name": "Test Rule"},
            }
        ]

        result = send_daily_digest(
            user_id="test-user-style",
            user_email="test@example.com",
            notifications=notifications,
        )

        self.assertTrue(result["success"])

        # Extract HTML
        call_args = mock_resend.Emails.send.call_args[0][0]
        html_body = call_args["html"]

        # Verify footer contains both links
        self.assertIn("Manage your notification preferences</a>", html_body)
        self.assertIn("Unsubscribe</a>", html_body)

        # Verify links separated by bullet
        self.assertIn("•", html_body)

        # Verify footer section exists
        self.assertIn('class="footer"', html_body)


if __name__ == "__main__":
    unittest.main()
