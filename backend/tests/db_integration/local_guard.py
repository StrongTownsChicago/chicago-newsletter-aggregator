"""Refuse any database connection that isn't the local Supabase stack.

``backend/.env`` points at production, so every test helper that connects,
writes, truncates or seeds checks its URL and key here first. The checks are
pure; ``abort_unless_local`` ends the whole process when one fails, since
unittest would otherwise record the error and carry on with the next test.
"""

import base64
import binascii
import json
import os
import sys
from urllib.parse import urlsplit

LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})

#: Issuer of the demo JWTs that ``supabase start`` prints. Hosted projects'
#: keys are issued by ``supabase`` and name the project in a ``ref`` claim.
LOCAL_KEY_ISSUER = "supabase-demo"

#: Exit status when a check fails: distinct from a test failure (1).
NOT_LOCAL_EXIT_STATUS = 3


class NotLocalDatabaseError(RuntimeError):
    """A URL or key that may belong to a hosted (production) project."""


def ensure_local_url(url: str) -> None:
    """Raise unless ``url`` (HTTP API or Postgres) points at a loopback host."""
    try:
        host = urlsplit(url).hostname
    except ValueError as error:
        raise NotLocalDatabaseError(f"unparseable database URL: {error}") from error
    if host not in LOOPBACK_HOSTS:
        raise NotLocalDatabaseError(f"database host {host!r} is not local")


def _jwt_claims(key: str) -> dict[str, object]:
    parts = key.split(".")
    if len(parts) != 3:  # header, payload, signature
        raise NotLocalDatabaseError(
            "key is not a JWT; use the stack's ANON_KEY or SERVICE_ROLE_KEY"
        )
    payload = parts[1] + "=" * (-len(parts[1]) % 4)
    try:
        claims = json.loads(base64.urlsafe_b64decode(payload))
    except (binascii.Error, UnicodeDecodeError, ValueError) as error:
        raise NotLocalDatabaseError("key's JWT payload is unreadable") from error
    if not isinstance(claims, dict):
        raise NotLocalDatabaseError("key's JWT payload is not an object")
    return claims


def ensure_local_key(key: str) -> None:
    """Raise unless ``key`` is one of the local stack's demo JWTs."""
    claims = _jwt_claims(key)
    if "ref" in claims:
        raise NotLocalDatabaseError(f"key belongs to hosted project {claims['ref']!r}")
    if claims.get("iss") != LOCAL_KEY_ISSUER:
        raise NotLocalDatabaseError(
            f"key issuer {claims.get('iss')!r} is not the local stack's"
        )


def ensure_local_supabase(url: str, key: str) -> None:
    """Raise unless both the API URL and its key are the local stack's."""
    ensure_local_url(url)
    ensure_local_key(key)


def abort_unless_local(url: str, key: str | None = None) -> None:
    """End the process unless ``url`` (and ``key``, if given) are local."""
    try:
        ensure_local_url(url)
        if key is not None:
            ensure_local_key(key)
    except NotLocalDatabaseError as error:
        sys.stderr.write(f"\nRefusing to touch a non-local database: {error}\n")
        sys.stderr.flush()
        os._exit(NOT_LOCAL_EXIT_STATUS)
