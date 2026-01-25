"""
Token generation and validation for one-click unsubscribe functionality.

Uses cryptographically signed tokens with expiry for secure unsubscribe links.
Tokens are stateless (no database storage needed) and expire after 90 days.
"""

import os
import hashlib
from typing import Optional
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

UNSUBSCRIBE_SALT = "unsubscribe"


def _get_serializer() -> URLSafeTimedSerializer:
    """
    Get configured serializer for token generation and validation.

    Returns:
        URLSafeTimedSerializer instance

    Raises:
        ValueError: If UNSUBSCRIBE_SECRET_KEY environment variable not set
    """
    secret_key = os.getenv("UNSUBSCRIBE_SECRET_KEY")
    if not secret_key:
        raise ValueError("UNSUBSCRIBE_SECRET_KEY environment variable must be set.")

    return URLSafeTimedSerializer(
        secret_key,
        salt=UNSUBSCRIBE_SALT,
        signer_kwargs={"digest_method": hashlib.sha256},
    )


def generate_unsubscribe_token(user_id: str, max_age_days: int = 90) -> str:
    """
    Generate a signed unsubscribe token for a user.

    The token is cryptographically signed using HMAC and contains only the user_id.
    It's URL-safe and can be embedded in email links.

    Args:
        user_id: User's unique identifier (UUID)
        max_age_days: Token expiry in days (default: 90)

    Returns:
        URL-safe token string (format: payload.timestamp.signature)

    Raises:
        ValueError: If UNSUBSCRIBE_SECRET_KEY not configured
    """
    serializer = _get_serializer()
    return serializer.dumps(user_id)


def validate_unsubscribe_token(token: str, max_age_days: int = 90) -> Optional[str]:
    """
    Validate an unsubscribe token and extract the user_id.

    Verifies the token's signature and checks it hasn't expired.
    Never raises exceptions - returns None for any invalid token.

    Args:
        token: Token string from URL parameter
        max_age_days: Maximum token age in days (default: 90)

    Returns:
        user_id if token is valid, None if invalid or expired

    Examples:
        >>> token = generate_unsubscribe_token("user-123")
        >>> user_id = validate_unsubscribe_token(token)
        >>> print(user_id)
        'user-123'

        >>> user_id = validate_unsubscribe_token("invalid-token")
        >>> print(user_id)
        None
    """
    try:
        serializer = _get_serializer()
        max_age_seconds = max_age_days * 24 * 60 * 60
        user_id = serializer.loads(
            token, max_age=max_age_seconds, salt=UNSUBSCRIBE_SALT
        )
        return user_id
    except (BadSignature, SignatureExpired, ValueError, TypeError):
        # Invalid signature, expired, or malformed token
        return None
