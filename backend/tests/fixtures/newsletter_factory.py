"""Factory functions for creating test newsletter data."""

import uuid
from datetime import datetime
from typing import Any


def create_test_newsletter(
    subject: str = "Test Newsletter",
    plain_text: str = "Test newsletter content about zoning and development.",
    raw_html: str | None = None,
    source_id: int = 1,
    topics: list[str] | None = None,
    relevance_score: int = 5,
    received_date: str | None = None,
    email_uid: str | None = None,
    summary: str | None = None,
    from_email: str | None = None,
    to_email: str | None = None,
    **overrides,
) -> dict[str, Any]:
    """
    Factory for creating test newsletter data.

    Args:
        subject: Newsletter subject line
        plain_text: Plain text content
        raw_html: HTML content (defaults to wrapping plain_text)
        source_id: Source database ID
        topics: List of topics (defaults to empty list)
        relevance_score: Relevance score 0-10
        received_date: ISO format date (defaults to now)
        email_uid: Email UID (defaults to random)
        summary: Newsletter summary (defaults to None)
        from_email: Sender email address
        to_email: Recipient email address
        **overrides: Override any field

    Returns:
        Dictionary with newsletter data matching database schema
    """
    newsletter_id = str(uuid.uuid4())

    newsletter = {
        "id": newsletter_id,
        "subject": subject,
        "plain_text": plain_text,
        "raw_html": raw_html or f"<html><body><p>{plain_text}</p></body></html>",
        "source_id": source_id,
        "topics": topics or [],
        "relevance_score": relevance_score,
        "received_date": received_date or datetime.now().isoformat(),
        "email_uid": email_uid or f"test_{uuid.uuid4().hex[:8]}",
        "summary": summary,
        "from_email": from_email or "test@example.com",
        "to_email": to_email or "recipient@example.com",
        "created_at": datetime.now().isoformat(),
    }

    newsletter.update(overrides)
    return newsletter


def create_test_source(
    source_id: int = 1,
    name: str = "Test Alderman",
    ward_number: int | None = 1,
    source_type: str = "alderman",
    newsletter_archive_url: str | None = None,
    **overrides,
) -> dict[str, Any]:
    """Factory for creating test source data."""
    source = {
        "id": source_id,
        "name": name,
        "ward_number": ward_number,
        "source_type": source_type,
        "newsletter_archive_url": newsletter_archive_url,
    }
    source.update(overrides)
    return source


def create_test_email_mapping(
    email_pattern: str = "%@testward.org",
    source_id: int = 1,
    **overrides,
) -> dict[str, Any]:
    """Factory for creating test email source mapping."""
    mapping = {
        "email_pattern": email_pattern,
        "source_id": source_id,
        "sources": create_test_source(source_id=source_id),
    }
    mapping.update(overrides)
    return mapping
