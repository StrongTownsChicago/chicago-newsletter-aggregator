"""Pydantic models for newsletter data."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from models.types import NewsletterID, SourceID, TopicList, WardNumber


class NewsletterBase(BaseModel):
    """Base newsletter fields shared across contexts."""

    model_config = ConfigDict(
        str_strip_whitespace=True,
        validate_assignment=True,
    )

    subject: str = Field(..., min_length=1)
    plain_text: str
    raw_html: str | None = None


class NewsletterCreate(NewsletterBase):
    """Newsletter data for database insertion (before ID assignment)."""

    email_uid: str | None = None
    received_date: datetime | None = None
    from_email: str | None = None
    to_email: str | None = None
    source_id: SourceID | None = None
    topics: TopicList = Field(default_factory=list)
    summary: str | None = None
    relevance_score: int | None = Field(None, ge=0, le=10)


class Newsletter(NewsletterCreate):
    """Complete newsletter record from database."""

    id: NewsletterID
    created_at: datetime | None = None
    updated_at: datetime | None = None


class NewsletterProcessing(BaseModel):
    """Newsletter data for LLM processing (minimal fields)."""

    model_config = ConfigDict(str_strip_whitespace=True)

    subject: str
    plain_text: str


class NewsletterMatching(BaseModel):
    """Newsletter data for notification rule matching."""

    topics: TopicList = Field(default_factory=list)
    plain_text: str = ""
    source_id: SourceID | None = None
    ward_number: WardNumber | None = None
    relevance_score: int | None = Field(None, ge=0, le=10)
