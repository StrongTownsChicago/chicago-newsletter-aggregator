"""
Integration tests for complete unsubscribe workflow.
"""

import os
import unittest
import jwt
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from notifications.unsubscribe_tokens import (
    generate_unsubscribe_token,
    validate_unsubscribe_token,
    ALGORITHM,
)
from notifications.email_sender import send_daily_digest


class TestUnsubscribeFlow(unittest.TestCase):
    """Test end-to-end unsubscribe workflow."""

    def setUp(self):
        """Set up test environment."""
        self.original_secret = os.environ.get("UNSUBSCRIBE_SECRET_KEY")
        self.test_secret = "test-secret-key-for-testing-must-be-at-least-32-chars-long"
        os.environ["UNSUBSCRIBE_SECRET_KEY"] = self.test_secret
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

    def test_token_generation_and_validation_roundtrip(self):
        """Test that generated token can be validated to get original user_id."""
        user_id = "test-user-integration-123"

        # Generate token
        token = generate_unsubscribe_token(user_id)
        self.assertIsNotNone(token)
        self.assertGreater(len(token), 0)

        # Validate token
        validated_user_id = validate_unsubscribe_token(token)
        self.assertEqual(validated_user_id, user_id)

    @patch("notifications.email_sender.resend")
    def test_email_contains_valid_unsubscribe_token(self, mock_resend):
        """Test that email digest includes valid unsubscribe token in headers and body."""
        mock_resend.Emails.send.return_value = {"id": "email-123"}

        user_id = "test-user-email-flow"
        user_email = "test@example.com"
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

        # Send email
        result = send_daily_digest(user_id, user_email, notifications)
        self.assertTrue(result["success"])

        # Extract sent email data
        call_args = mock_resend.Emails.send.call_args[0][0]

        # Verify List-Unsubscribe header
        self.assertIn("headers", call_args)
        self.assertIn("List-Unsubscribe", call_args["headers"])
        list_unsub_header = call_args["headers"]["List-Unsubscribe"]

        # Extract token from header
        # Format: <https://test.example.com/unsubscribe?token=TOKENHERE>
        self.assertTrue(list_unsub_header.startswith("<https://"))
        self.assertTrue(list_unsub_header.endswith(">"))
        url = list_unsub_header[1:-1]  # Remove angle brackets
        self.assertIn("/unsubscribe?token=", url)

        token = url.split("?token=")[1]

        # Validate extracted token
        validated_user_id = validate_unsubscribe_token(token)
        self.assertEqual(validated_user_id, user_id)

        # Verify token also in HTML body
        html_body = call_args["html"]
        self.assertIn("/unsubscribe?token=", html_body)
        self.assertIn(token, html_body)

        # Verify token also in text body
        text_body = call_args["text"]
        self.assertIn("/unsubscribe?token=", text_body)
        self.assertIn(token, text_body)

    def test_expired_token_cannot_be_validated(self):
        """Test that tokens respect expiration."""
        user_id = "test-user-expiry-check"

        # Manually create an expired token
        expired_payload = {
            "sub": user_id,
            "exp": datetime.now(timezone.utc) - timedelta(days=1),
            "type": "unsubscribe",
        }
        token = jwt.encode(expired_payload, self.test_secret, algorithm=ALGORITHM)

        # Validate should fail
        result = validate_unsubscribe_token(token)
        self.assertIsNone(result)

    def test_tampered_token_fails_validation(self):
        """Test that modifying token makes it invalid."""
        user_id = "test-user-tamper-check"

        # Generate valid token
        token = generate_unsubscribe_token(user_id)

        # Tamper with token (signature part)
        parts = token.split(".")
        tampered_parts = parts.copy()
        # Change the FIRST character of the signature to ensure it changes
        first_char = tampered_parts[2][0]
        new_char = "Z" if first_char != "Z" else "A"
        tampered_parts[2] = new_char + tampered_parts[2][1:]
        tampered_token = ".".join(tampered_parts)

        # Validation should fail
        result = validate_unsubscribe_token(tampered_token)
        self.assertIsNone(result)

    def test_different_secret_key_fails_validation(self):
        """Test that tokens generated with different secret keys don't validate."""
        user_id = "test-user-secret-mismatch"

        # Generate token with first secret
        os.environ["UNSUBSCRIBE_SECRET_KEY"] = (
            "first-secret-key-must-be-at-least-32-chars-long-test"
        )
        token = generate_unsubscribe_token(user_id)

        # Try to validate with different secret
        os.environ["UNSUBSCRIBE_SECRET_KEY"] = (
            "second-secret-key-must-be-at-least-32-chars-long-diff"
        )

        result = validate_unsubscribe_token(token)
        self.assertIsNone(result)

    @patch("notifications.email_sender.resend")
    def test_multiple_users_get_unique_tokens(self, mock_resend):
        """Test that different users get different unsubscribe tokens."""
        mock_resend.Emails.send.return_value = {"id": "email-123"}

        user1_id = "user-one"
        user2_id = "user-two"

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

        # Send to first user
        result1 = send_daily_digest(user1_id, "user1@example.com", notifications)
        self.assertTrue(result1["success"])
        call1_args = mock_resend.Emails.send.call_args_list[0][0][0]
        token1_url = call1_args["headers"]["List-Unsubscribe"]

        # Send to second user
        result2 = send_daily_digest(user2_id, "user2@example.com", notifications)
        self.assertTrue(result2["success"])
        call2_args = mock_resend.Emails.send.call_args_list[1][0][0]
        token2_url = call2_args["headers"]["List-Unsubscribe"]

        # Tokens should be different
        self.assertNotEqual(token1_url, token2_url)

        # Extract and validate both tokens
        token1 = token1_url.split("?token=")[1].rstrip(">")
        token2 = token2_url.split("?token=")[1].rstrip(">")

        validated1 = validate_unsubscribe_token(token1)
        validated2 = validate_unsubscribe_token(token2)

        self.assertEqual(validated1, user1_id)
        self.assertEqual(validated2, user2_id)

    def test_token_with_special_characters_in_user_id(self):
        """Test that UUIDs and special characters work correctly."""
        # Test with typical UUID format
        uuid_user_id = "550e8400-e29b-41d4-a716-446655440000"
        token1 = generate_unsubscribe_token(uuid_user_id)
        result1 = validate_unsubscribe_token(token1)
        self.assertEqual(result1, uuid_user_id)

        # Test with alphanumeric
        alphanum_id = "abc123XYZ789"
        token2 = generate_unsubscribe_token(alphanum_id)
        result2 = validate_unsubscribe_token(token2)
        self.assertEqual(result2, alphanum_id)


if __name__ == "__main__":
    unittest.main()
