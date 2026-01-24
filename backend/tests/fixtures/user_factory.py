"""Factory functions for creating test user and notification data."""

import uuid
from typing import Any, Dict, List, Optional


def create_test_user(
    user_id: Optional[str] = None,
    email: str = "test@example.com",
    notifications_enabled: bool = True,
    **overrides,
) -> Dict[str, Any]:
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
    rule_id: Optional[str] = None,
    user_id: Optional[str] = None,
    name: str = "Test Rule",
    topics: Optional[List[str]] = None,
    search_term: Optional[str] = None,
    ward_numbers: Optional[List[int]] = None,
    min_relevance_score: Optional[int] = None,
    is_active: bool = True,
    **overrides,
) -> Dict[str, Any]:
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
    notification_id: Optional[str] = None,
    user_id: Optional[str] = None,
    newsletter_id: Optional[str] = None,
    rule_id: Optional[str] = None,
    status: str = "pending",
    digest_batch_id: str = "2026-01-24",
    **overrides,
) -> Dict[str, Any]:
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
