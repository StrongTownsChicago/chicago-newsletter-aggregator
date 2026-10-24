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
    received_date: str | None = None,
    email_uid: str | None = None,
    summary: str | None = None,
    from_email: str | None = None,
    to_email: str | None = None,
    **overrides: Any,
) -> dict[str, Any]:
    """
    Build a newsletter dict matching the database schema.

    Omitted fields get defaults: raw_html wraps plain_text, received_date is
    now, email_uid is random. `overrides` replace any field.
    """
    newsletter_id = str(uuid.uuid4())

    newsletter = {
        "id": newsletter_id,
        "subject": subject,
        "plain_text": plain_text,
        "raw_html": raw_html or f"<html><body><p>{plain_text}</p></body></html>",
        "source_id": source_id,
        "topics": topics or [],
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
    **overrides: Any,
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
    **overrides: Any,
) -> dict[str, Any]:
    """Factory for creating test email source mapping."""
    mapping = {
        "email_pattern": email_pattern,
        "source_id": source_id,
        "sources": create_test_source(source_id=source_id),
    }
    mapping.update(overrides)
    return mapping


def insert_row(client: Any, table: str, row: dict[str, Any]) -> dict[str, Any]:
    """Insert one row with ``client`` and return it as stored."""
    stored: dict[str, Any] = client.table(table).insert(row).execute().data[0]
    return stored


def insert_source(client: Any, **fields: Any) -> dict[str, Any]:
    """Insert a source; its id comes from the sequence unless `source_id` is given."""
    row = create_test_source(**fields)
    if "source_id" not in fields:
        del row["id"]
    if row["ward_number"] is not None:
        row["ward_number"] = str(row["ward_number"])  # a text column
    return insert_row(client, "sources", row)


def insert_newsletter(client: Any, source_id: int, **fields: Any) -> dict[str, Any]:
    """Insert a newsletter for `source_id`; `fields` as for create_test_newsletter.

    A field given as None stays None (create_test_newsletter fills some in).
    """
    row = create_test_newsletter(source_id=source_id, **fields)
    row.update({name: value for name, value in fields.items() if value is None})
    del row["created_at"]  # the column default
    return insert_row(client, "newsletters", row)


def insert_email_mapping(
    client: Any, email_pattern: str, source_id: int
) -> dict[str, Any]:
    """Insert an email_source_mappings row."""
    return insert_row(
        client,
        "email_source_mappings",
        {"email_pattern": email_pattern, "source_id": source_id},
    )
