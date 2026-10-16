"""Pydantic models for data validation and type checking."""

from models.newsletter import (
    Newsletter,
    NewsletterCreate,
    NewsletterMatching,
    NewsletterProcessing,
)
from models.notification import (
    NotificationQueueEntry,
    NotificationRule,
    RuleMatch,
    UserProfile,
)
from models.source import EmailSourceMapping, Source

__all__ = [
    "EmailSourceMapping",
    "Newsletter",
    "NewsletterCreate",
    "NewsletterMatching",
    "NewsletterProcessing",
    "NotificationQueueEntry",
    "NotificationRule",
    "RuleMatch",
    "Source",
    "UserProfile",
]
