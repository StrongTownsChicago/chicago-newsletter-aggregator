"""
Token generation for one-click unsubscribe functionality.

Uses JSON Web Tokens (JWT) for secure, cross-platform unsubscribe links.
Tokens are stateless (no database storage needed); the frontend validates them.
"""

import os
from datetime import UTC, datetime, timedelta

import jwt

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
    Generate a JWT unsubscribe token for a user, expiring after `max_age_days`.

    Raises ValueError if UNSUBSCRIBE_SECRET_KEY is not configured.
    """
    secret_key = _get_secret_key()
    expiration = datetime.now(UTC) + timedelta(days=max_age_days)

    payload = {"sub": user_id, "exp": expiration, "type": "unsubscribe"}

    return jwt.encode(payload, secret_key, algorithm=ALGORITHM)
