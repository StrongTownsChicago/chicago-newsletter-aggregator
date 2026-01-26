"""
Token generation and validation for one-click unsubscribe functionality.

Uses JSON Web Tokens (JWT) for secure, cross-platform unsubscribe links.
Tokens are stateless (no database storage needed).
"""

import os
import jwt
from datetime import datetime, timedelta, timezone
from typing import Optional

ALGORITHM = "HS256"


def _get_secret_key() -> str:
    """
    Get the secret key for signing tokens.

    Returns:
        Secret key string

    Raises:
        ValueError: If UNSUBSCRIBE_SECRET_KEY environment variable not set
    """
    secret_key = os.getenv("UNSUBSCRIBE_SECRET_KEY")
    if not secret_key:
        raise ValueError("UNSUBSCRIBE_SECRET_KEY environment variable must be set.")
    return secret_key


def generate_unsubscribe_token(user_id: str, max_age_days: int = 90) -> str:
    """
    Generate a JWT unsubscribe token for a user.

    Args:
        user_id: User's unique identifier (UUID)
        max_age_days: Token expiry in days (default: 90)

    Returns:
        JWT token string

    Raises:
        ValueError: If UNSUBSCRIBE_SECRET_KEY not configured
    """
    secret_key = _get_secret_key()
    expiration = datetime.now(timezone.utc) + timedelta(days=max_age_days)

    payload = {"sub": user_id, "exp": expiration, "type": "unsubscribe"}

    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)


def validate_unsubscribe_token(token: str) -> Optional[str]:
    """
    Validate an unsubscribe JWT and extract the user_id.

    Verifies the token's signature, expiration, and type.
    Never raises exceptions - returns None for any invalid token.

    Args:
        token: JWT token string

    Returns:
        user_id if token is valid, None if invalid or expired
    """
    try:
        secret_key = _get_secret_key()
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])

        if payload.get("type") != "unsubscribe":
            return None

        return payload.get("sub")
    except (jwt.InvalidTokenError, ValueError):
        # Invalid signature, expired, malformed, or missing secret key
        return None
