"""Decode unsubscribe tokens the way the frontend does, for round-trip tests.

Production validation lives in the frontend (`jose`); this mirror lets the
backend tests check that the tokens it signs carry the right user, type and
expiry.
"""

import os

import jwt

from notifications.unsubscribe_tokens import ALGORITHM


def validate_unsubscribe_token(token: str) -> str | None:
    """
    Validate an unsubscribe JWT and extract the user_id.

    Verifies the token's signature, expiration, and type.
    Never raises exceptions - returns None for any invalid or expired token.
    """
    secret_key = os.getenv("UNSUBSCRIBE_SECRET_KEY")
    if not secret_key:
        return None
    try:
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
    except jwt.InvalidTokenError:
        # Invalid signature, expired or malformed
        return None
    if payload.get("type") != "unsubscribe":
        return None
    user_id = payload.get("sub")
    return str(user_id) if user_id is not None else None
