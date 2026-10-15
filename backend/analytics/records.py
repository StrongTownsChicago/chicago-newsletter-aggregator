"""Typed records parsed from Supabase rows, plus date bucketing helpers."""

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any
from zoneinfo import ZoneInfo

CHICAGO_TIMEZONE = ZoneInfo("America/Chicago")


@dataclass(frozen=True)
class SourceRecord:
    id: int
    name: str
    ward: str | None
    source_type: str


@dataclass(frozen=True)
class NewsletterRecord:
    id: str
    received_date: date
    source_id: int | None
    subject: str
    plain_text: str
    topics: list[str] | None


def to_chicago_date(timestamp: str) -> date:
    """Convert an ISO timestamp to its calendar date in Chicago.

    Naive timestamps are treated as already local.
    """
    parsed = datetime.fromisoformat(timestamp)
    if parsed.tzinfo is None:
        return parsed.date()
    return parsed.astimezone(CHICAGO_TIMEZONE).date()


def month_key(day: date) -> str:
    """Return the YYYY-MM bucket for a date."""
    return f"{day.year:04d}-{day.month:02d}"


def shift_month(month: str, offset: int) -> str:
    """Move a YYYY-MM key by offset months (negative goes back in time)."""
    year, month_number = (int(part) for part in month.split("-"))
    month_index = year * 12 + (month_number - 1) + offset
    return f"{month_index // 12:04d}-{month_index % 12 + 1:02d}"


def parse_source_row(row: dict[str, Any]) -> SourceRecord:
    """Build a SourceRecord from a `sources` row; blank wards become None."""
    ward = (row.get("ward_number") or "").strip()
    return SourceRecord(
        id=int(row["id"]),
        name=row.get("name") or "",
        ward=ward or None,
        source_type=row.get("source_type") or "",
    )


def parse_newsletter_row(row: dict[str, Any]) -> NewsletterRecord:
    """Build a NewsletterRecord from a `newsletters` row."""
    source_id = row.get("source_id")
    return NewsletterRecord(
        id=str(row["id"]),
        received_date=to_chicago_date(row["received_date"]),
        source_id=int(source_id) if source_id is not None else None,
        subject=row.get("subject") or "",
        plain_text=row.get("plain_text") or "",
        topics=row.get("topics"),
    )


def ward_sort_key(ward: str) -> tuple[bool, int, str]:
    """Sort numeric wards numerically, followed by any non-numeric labels alphabetically."""
    is_numeric = ward.isdigit()
    return (not is_numeric, int(ward) if is_numeric else 0, ward)
