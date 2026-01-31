"""Pydantic models for notification system."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.types import (
    BatchID,
    NewsletterID,
    RuleID,
    TopicList,
    UserID,
    WardNumber,
)


class NotificationRule(BaseModel):
    """User-defined notification rule."""

    model_config = ConfigDict(str_strip_whitespace=True)

    id: RuleID
    user_id: UserID
    name: str = Field(..., min_length=1)
    topics: TopicList = Field(default_factory=list)
    search_term: str | None = None
    min_relevance_score: int | None = Field(None, ge=0, le=10)
    source_ids: list[str] = Field(default_factory=list)
    ward_numbers: list[WardNumber] = Field(default_factory=list)
    is_active: bool = True


class RuleMatch(BaseModel):
    """Represents a rule that matched a newsletter."""

    user_id: UserID
    rule_id: RuleID
    rule_name: str


class NotificationQueueEntry(BaseModel):
    """Queued notification waiting to be sent."""

    id: int
    user_id: UserID
    newsletter_id: NewsletterID
    rule_id: RuleID
    status: str = Field(..., pattern="^(pending|sent|failed)$")
    digest_batch_id: BatchID
    created_at: datetime
    sent_at: datetime | None = None
    error_message: str | None = None


class UserProfile(BaseModel):
    """User profile with notification preferences."""

    id: UserID
    email: str = Field(..., pattern=r"^[^@]+@[^@]+\.[^@]+$")
    notification_preferences: dict[str, bool] = Field(
        default_factory=lambda: {"enabled": True}
    )
