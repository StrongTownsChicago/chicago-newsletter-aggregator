"""
Unit tests for unsubscribe token generation and validation.
"""

import os
import unittest
import jwt
from datetime import datetime, timedelta, timezone
from notifications.unsubscribe_tokens import (
    generate_unsubscribe_token,
    validate_unsubscribe_token,
    ALGORITHM,
)


class TestUnsubscribeTokens(unittest.TestCase):
    """Test token generation and validation logic."""

    def setUp(self):
        """Set up test environment with secret key."""
        self.original_secret = os.environ.get("UNSUBSCRIBE_SECRET_KEY")
        self.test_secret = "test-secret-key-for-testing-must-be-at-least-32-chars-long"
        os.environ["UNSUBSCRIBE_SECRET_KEY"] = self.test_secret

    def tearDown(self):
        """Restore original environment."""
        if self.original_secret:
            os.environ["UNSUBSCRIBE_SECRET_KEY"] = self.original_secret
        else:
            os.environ.pop("UNSUBSCRIBE_SECRET_KEY", None)

    def test_generate_token_creates_valid_format(self):
        """Test that generated token is a proper JWT string."""
        user_id = "test-user-123"
        token = generate_unsubscribe_token(user_id)

        # Token should be a non-empty string
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 0)

        # JWT format: header.payload.signature
        parts = token.split(".")
        self.assertEqual(len(parts), 3, "Token should be a valid JWT with 3 parts")

    def test_token_contains_correct_claims(self):
        """Test that token contains expected claims."""
        user_id = "test-user-claims"
        token = generate_unsubscribe_token(user_id)

        # Decode without verification to check claims
        payload = jwt.decode(token, options={"verify_signature": False})

        self.assertEqual(payload["sub"], user_id)
        self.assertEqual(payload["type"], "unsubscribe")
        self.assertIn("exp", payload)

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
        user_id = "test-user-789"

        # Manually create an expired token
        expired_payload = {
            "sub": user_id,
            "exp": datetime.now(timezone.utc) - timedelta(days=1),
            "type": "unsubscribe",
        }
        token = jwt.encode(expired_payload, self.test_secret, algorithm=ALGORITHM)

        result = validate_unsubscribe_token(token)

        self.assertIsNone(result)

    def test_validate_token_returns_none_for_tampered_signature(self):
        """Test that token with modified signature is rejected."""
        user_id = "test-user-tampered"
        token = generate_unsubscribe_token(user_id)

        # Tamper with the signature (last part)
        parts = token.split(".")
        parts[2] = "X" * len(parts[2])
        tampered_token = ".".join(parts)

        result = validate_unsubscribe_token(tampered_token)

        self.assertIsNone(result)

    def test_validate_token_returns_none_for_wrong_type(self):
        """Test that token with wrong 'type' claim is rejected."""
        user_id = "test-user-wrong-type"
        payload = {
            "sub": user_id,
            "exp": datetime.now(timezone.utc) + timedelta(days=1),
            "type": "access_token",  # Wrong type
        }
        token = jwt.encode(payload, self.test_secret, algorithm=ALGORITHM)

        result = validate_unsubscribe_token(token)

        self.assertIsNone(result)

    def test_generate_token_handles_special_characters_in_user_id(self):
        """Test that UUIDs and special characters are properly handled."""
        user_ids = [
            "550e8400-e29b-41d4-a716-446655440000",
            "user-test-with-dashes",
            "abc123xyz789",
        ]

        for user_id in user_ids:
            token = generate_unsubscribe_token(user_id)
            result = validate_unsubscribe_token(token)
            self.assertEqual(result, user_id)

    def test_token_requires_secret_key(self):
        """Test that missing secret key raises appropriate error."""
        # Remove secret key from environment
        os.environ.pop("UNSUBSCRIBE_SECRET_KEY", None)

        with self.assertRaises(ValueError) as context:
            generate_unsubscribe_token("test-user")

        self.assertIn("UNSUBSCRIBE_SECRET_KEY", str(context.exception))

    def test_different_users_get_different_tokens(self):
        """Test that different user IDs produce different tokens."""
        user1 = "user-one"
        user2 = "user-two"

        token1 = generate_unsubscribe_token(user1)
        token2 = generate_unsubscribe_token(user2)

        self.assertNotEqual(token1, token2)
        self.assertEqual(validate_unsubscribe_token(token1), user1)
        self.assertEqual(validate_unsubscribe_token(token2), user2)

    def test_validate_token_with_different_secret_key_fails(self):
        """Test that token generated with one secret fails with another secret."""
        user_id = "test-user-secret"
        token = generate_unsubscribe_token(user_id)

        # Change the secret key
        os.environ["UNSUBSCRIBE_SECRET_KEY"] = "different-secret-key-min-32-chars-long"

        result = validate_unsubscribe_token(token)

        # Should fail signature verification
        self.assertIsNone(result)


if __name__ == "__main__":
    unittest.main()
