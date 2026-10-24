"""Factory functions for creating test user and notification data."""

import uuid
from typing import Any


def create_test_user(
    user_id: str | None = None,
    email: str = "test@example.com",
    notifications_enabled: bool = True,
    **overrides: Any,
) -> dict[str, Any]:
    """Factory for creating test user profile data."""
    user = {
        "id": user_id or str(uuid.uuid4()),
        "email": email,
        "notification_preferences": {
            "enabled": notifications_enabled,
        },
    }
    user.update(overrides)
    return user


def create_test_rule(
    rule_id: str | None = None,
    user_id: str | None = None,
    name: str = "Test Rule",
    topics: list[str] | None = None,
    search_term: str | None = None,
    ward_numbers: list[int] | None = None,
    is_active: bool = True,
    **overrides: Any,
) -> dict[str, Any]:
    """Factory for creating test notification rule data."""
    rule = {
        "id": rule_id or str(uuid.uuid4()),
        "user_id": user_id or str(uuid.uuid4()),
        "name": name,
        "topics": topics or [],
        "search_term": search_term,
        "ward_numbers": ward_numbers or [],
        "is_active": is_active,
    }
    rule.update(overrides)
    return rule


def create_test_notification(
    notification_id: str | None = None,
    user_id: str | None = None,
    newsletter_id: str | None = None,
    rule_id: str | None = None,
    status: str = "pending",
    digest_batch_id: str = "2026-01-24",
    **overrides: Any,
) -> dict[str, Any]:
    """Factory for creating test notification queue entry."""
    notification = {
        "id": notification_id or str(uuid.uuid4()),
        "user_id": user_id or str(uuid.uuid4()),
        "newsletter_id": newsletter_id or str(uuid.uuid4()),
        "rule_id": rule_id or str(uuid.uuid4()),
        "status": status,
        "digest_batch_id": digest_batch_id,
    }
    notification.update(overrides)
    return notification


def create_auth_user(client: Any, email: str, password: str) -> str:
    """Create a confirmed user through the GoTrue admin API; returns its id.

    `client` needs the service key. The on_auth_user_created trigger adds the
    user_profiles row, as in production.
    """
    response = client.auth.admin.create_user(
        {"email": email, "password": password, "email_confirm": True}
    )
    return str(response.user.id)


def insert_rule(client: Any, user_id: str, **fields: Any) -> dict[str, Any]:
    """Insert a notification rule for `user_id`; `fields` as for create_test_rule."""
    row = create_test_rule(user_id=user_id, **fields)
    stored: dict[str, Any] = (
        client.table("notification_rules").insert(row).execute().data[0]
    )
    return stored


def insert_notification(client: Any, **fields: Any) -> dict[str, Any]:
    """Insert a notification_queue row; `fields` as for create_test_notification.

    An id given as None stays None (create_test_notification would invent one).
    """
    row = create_test_notification(**fields)
    row.update({name: value for name, value in fields.items() if value is None})
    stored: dict[str, Any] = (
        client.table("notification_queue").insert(row).execute().data[0]
    )
    return stored
