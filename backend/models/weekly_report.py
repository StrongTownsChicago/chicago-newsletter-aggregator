"""Pydantic models for weekly topic reports."""

from datetime import datetime

from pydantic import BaseModel, Field

from models.types import NewsletterID


class KeyDevelopment(BaseModel):
    """Individual development/event extracted from newsletters (domain/storage model)."""

    description: str = Field(..., max_length=2000)
    newsletter_ids: list[NewsletterID] = Field(default_factory=list)
    wards: list[str] = Field(default_factory=list)


class WeeklyTopicReport(BaseModel):
    """Weekly aggregated report for a specific topic."""

    id: str
    topic: str
    week_id: str  # Format: YYYY-WXX
    report_summary: str = Field(..., max_length=3000)
    newsletter_ids: list[NewsletterID]
    key_developments: list[KeyDevelopment] | None = None
    created_at: datetime


# LLM Response Schemas
class FactExtraction(BaseModel):
    """Phase 1: Extract structured facts from newsletters.

    The LLM returns only development descriptions. The owning newsletter's id
    and ward are not LLM concerns — they are known deterministically from the
    source and attached when building the KeyDevelopment domain objects.
    """

    developments: list[str] = Field(
        description="Key developments, decisions, or announcements"
    )


class WeeklySynthesis(BaseModel):
    """Phase 2: Synthesize facts into narrative summary."""

    summary: str = Field(
        max_length=3000,
        description="2-4 paragraph weekly summary of topic activity",
    )
