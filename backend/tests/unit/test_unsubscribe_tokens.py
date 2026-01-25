"""
Unit tests for unsubscribe token generation and validation.
"""

import os
import unittest
from unittest.mock import patch
import time
from notifications.unsubscribe_tokens import (
    generate_unsubscribe_token,
    validate_unsubscribe_token,
    UNSUBSCRIBE_SALT,
)


class TestUnsubscribeTokens(unittest.TestCase):
    """Test token generation and validation logic."""

    def setUp(self):
        """Set up test environment with secret key."""
        self.original_secret = os.environ.get("UNSUBSCRIBE_SECRET_KEY")
        os.environ["UNSUBSCRIBE_SECRET_KEY"] = (
            "test-secret-key-for-testing-must-be-at-least-32-chars-long"
        )

    def tearDown(self):
        """Restore original environment."""
        if self.original_secret:
            os.environ["UNSUBSCRIBE_SECRET_KEY"] = self.original_secret
        else:
            os.environ.pop("UNSUBSCRIBE_SECRET_KEY", None)

    def test_generate_token_creates_valid_format(self):
        """Test that generated token is a proper string with expected format."""
        user_id = "test-user-123"
        token = generate_unsubscribe_token(user_id)

        # Token should be a non-empty string
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 0)

        # Token should contain only URL-safe characters (base64url + separators)
        # Valid chars: A-Z, a-z, 0-9, -, _, .
        allowed_chars = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_."
        )
        self.assertTrue(
            all(c in allowed_chars for c in token), "Token contains invalid characters"
        )

        # Token should have payload.timestamp.signature format (2 dots)
        self.assertEqual(
            token.count("."), 2, "Token should have format: payload.timestamp.signature"
        )

    def test_validate_token_returns_user_id_for_valid_token(self):
        """Test that valid token returns correct user_id."""
        user_id = "test-user-456"
        token = generate_unsubscribe_token(user_id)

        result = validate_unsubscribe_token(token)

        self.assertEqual(result, user_id)
        self.assertIsNotNone(result)

    def test_validate_token_returns_none_for_invalid_token(self):
        """Test that invalid token returns None without raising exception."""
        invalid_token = "this-is-not-a-valid-token-at-all"

        result = validate_unsubscribe_token(invalid_token)

        self.assertIsNone(result)

    def test_validate_token_returns_none_for_expired_token(self):
        """Test that expired token returns None."""
        import hashlib
        from itsdangerous import URLSafeTimedSerializer

        user_id = "test-user-789"
        secret_key = os.environ["UNSUBSCRIBE_SECRET_KEY"]
        serializer = URLSafeTimedSerializer(
            secret_key,
            salt=UNSUBSCRIBE_SALT,
            signer_kwargs={"digest_method": hashlib.sha256},
        )

        # Create a token with timestamp in the past (91 days ago)
        # We need to use itsdangerous directly to create an old token
        old_timestamp = time.time() - (91 * 24 * 60 * 60)
        with patch("time.time", return_value=old_timestamp):
            token = serializer.dumps(user_id)

        # Try to validate with 90 day max age (should fail)
        result = validate_unsubscribe_token(token, max_age_days=90)

        self.assertIsNone(result)

    def test_validate_token_returns_none_for_tampered_signature(self):
        """Test that token with modified signature is rejected."""
        user_id = "test-user-tampered"
        token = generate_unsubscribe_token(user_id)

        # Tamper with the signature (last part after second dot)
        parts = token.split(".")
        # Replace signature with same length of 'X's to ensure it's invalid
        parts[2] = "X" * len(parts[2])
        tampered_token = ".".join(parts)

        result = validate_unsubscribe_token(tampered_token)

        self.assertIsNone(result)

    def test_validate_token_returns_none_for_tampered_payload(self):
        """Test that token with modified payload is rejected."""
        user_id = "test-user-payload-tamper"
        token = generate_unsubscribe_token(user_id)

        # Tamper with the payload (first part)
        parts = token.split(".")
        parts[0] = parts[0][:-1] + ("Z" if parts[0][-1] != "Z" else "A")
        tampered_token = ".".join(parts)

        result = validate_unsubscribe_token(tampered_token)

        # Signature won't match tampered payload
        self.assertIsNone(result)

    def test_token_expiry_respects_max_age_parameter(self):
        """Test that custom max_age is honored during validation."""
        import hashlib
        from itsdangerous import URLSafeTimedSerializer

        user_id = "test-user-expiry"
        secret_key = os.environ["UNSUBSCRIBE_SECRET_KEY"]
        serializer = URLSafeTimedSerializer(
            secret_key,
            salt=UNSUBSCRIBE_SALT,
            signer_kwargs={"digest_method": hashlib.sha256},
        )

        # Create a token with timestamp 45 days ago
        old_timestamp = time.time() - (45 * 24 * 60 * 60)
        with patch("time.time", return_value=old_timestamp):
            token = serializer.dumps(user_id)

        # Should be valid with 90 day max_age (45 < 90)
        result_90_days = validate_unsubscribe_token(token, max_age_days=90)
        self.assertEqual(result_90_days, user_id)

        # Should be valid with 365 day max_age (45 < 365)
        result_365_days = validate_unsubscribe_token(token, max_age_days=365)
        self.assertEqual(result_365_days, user_id)

        # Should be invalid with 30 day max_age (45 > 30)
        result_30_days = validate_unsubscribe_token(token, max_age_days=30)
        self.assertIsNone(result_30_days)

    def test_generate_token_handles_special_characters_in_user_id(self):
        """Test that UUIDs and special characters are properly encoded."""
        # Test with UUID format (most common)
        uuid_user_id = "550e8400-e29b-41d4-a716-446655440000"
        token1 = generate_unsubscribe_token(uuid_user_id)
        result1 = validate_unsubscribe_token(token1)
        self.assertEqual(result1, uuid_user_id)

        # Test with user ID containing dashes
        dashed_id = "user-test-with-dashes"
        token2 = generate_unsubscribe_token(dashed_id)
        result2 = validate_unsubscribe_token(token2)
        self.assertEqual(result2, dashed_id)

        # Test with alphanumeric ID
        alpha_id = "abc123xyz789"
        token3 = generate_unsubscribe_token(alpha_id)
        result3 = validate_unsubscribe_token(token3)
        self.assertEqual(result3, alpha_id)

    def test_token_requires_secret_key(self):
        """Test that missing secret key raises appropriate error."""
        # Remove secret key from environment
        os.environ.pop("UNSUBSCRIBE_SECRET_KEY", None)

        with self.assertRaises(ValueError) as context:
            generate_unsubscribe_token("test-user")

        self.assertIn("UNSUBSCRIBE_SECRET_KEY", str(context.exception))
        self.assertIn("must be set", str(context.exception))

    def test_validate_token_returns_none_for_empty_token(self):
        """Test that empty string token returns None."""
        result = validate_unsubscribe_token("")
        self.assertIsNone(result)

    def test_validate_token_returns_none_for_none_token(self):
        """Test that None token returns None without error."""
        result = validate_unsubscribe_token(None)
        self.assertIsNone(result)

    def test_different_users_get_different_tokens(self):
        """Test that different user IDs produce different tokens."""
        user1 = "user-one"
        user2 = "user-two"

        token1 = generate_unsubscribe_token(user1)
        token2 = generate_unsubscribe_token(user2)

        self.assertNotEqual(token1, token2)

        # Validate each returns correct user
        self.assertEqual(validate_unsubscribe_token(token1), user1)
        self.assertEqual(validate_unsubscribe_token(token2), user2)

    def test_validate_token_with_different_secret_key_fails(self):
        """Test that token generated with one secret fails with another secret."""
        user_id = "test-user-secret"
        token = generate_unsubscribe_token(user_id)

        # Change the secret key
        os.environ["UNSUBSCRIBE_SECRET_KEY"] = (
            "different-secret-key-wont-match-original-signature-min32"
        )

        result = validate_unsubscribe_token(token)

        # Should fail signature verification
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
