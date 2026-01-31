"""Factory functions for creating test user and notification data."""

import uuid
from typing import Any


def create_test_user(
    user_id: str | None = None,
    email: str = "test@example.com",
    notifications_enabled: bool = True,
    **overrides,
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
    min_relevance_score: int | None = None,
    is_active: bool = True,
    **overrides,
) -> dict[str, Any]:
    """Factory for creating test notification rule data."""
    rule = {
        "id": rule_id or str(uuid.uuid4()),
        "user_id": user_id or str(uuid.uuid4()),
        "name": name,
        "topics": topics or [],
        "search_term": search_term,
        "ward_numbers": ward_numbers or [],
        "min_relevance_score": min_relevance_score,
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
    **overrides,
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
