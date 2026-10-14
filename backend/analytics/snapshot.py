"""Row format and merge rules for the local analytics snapshot (no I/O).

The snapshot is a local copy of the columns analytics needs, so dashboard
data can be recomputed without re-reading the production database. Refreshes
only fetch newsletters created since `fetched_through` and merge them in.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from analytics.records import NewsletterRecord, SourceRecord


@dataclass(frozen=True)
class Snapshot:
    sources: list[SourceRecord]
    newsletters: list[NewsletterRecord]
    # Newest `newsletters.created_at` covered; the next refresh starts here.
    fetched_through: datetime


def newsletter_to_row(newsletter: NewsletterRecord) -> dict[str, Any]:
    """Serialize a newsletter for the snapshot (dates as ISO strings)."""
    return {
        "id": newsletter.id,
        "received_date": newsletter.received_date.isoformat(),
        "source_id": newsletter.source_id,
        "subject": newsletter.subject,
        "plain_text": newsletter.plain_text,
        "topics": newsletter.topics,
        "relevance_score": newsletter.relevance_score,
    }


def newsletter_from_row(row: dict[str, Any]) -> NewsletterRecord:
    """Rebuild a newsletter from a snapshot row.

    Unlike `parse_newsletter_row`, `received_date` is already a Chicago
    calendar date here, so it is not converted again.
    """
    source_id = row.get("source_id")
    return NewsletterRecord(
        id=str(row["id"]),
        received_date=date.fromisoformat(row["received_date"]),
        source_id=int(source_id) if source_id is not None else None,
        subject=row.get("subject") or "",
        plain_text=row.get("plain_text") or "",
        topics=row.get("topics"),
        relevance_score=row.get("relevance_score"),
    )


def source_to_row(source: SourceRecord) -> dict[str, Any]:
    """Serialize a source for the snapshot."""
    return {
        "id": source.id,
        "name": source.name,
        "ward": source.ward,
        "source_type": source.source_type,
    }


def source_from_row(row: dict[str, Any]) -> SourceRecord:
    """Rebuild a source from a snapshot row."""
    return SourceRecord(
        id=int(row["id"]),
        name=row.get("name") or "",
        ward=row.get("ward"),
        source_type=row.get("source_type") or "",
    )


def merge_newsletters(
    existing: Iterable[NewsletterRecord], updates: Iterable[NewsletterRecord]
) -> list[NewsletterRecord]:
    """Combine snapshot newsletters with freshly fetched ones.

    Rows are keyed by id and fetched rows win, so re-fetching an overlap
    window replaces rather than duplicates. Output is sorted by date then id
    so the snapshot file is stable between runs.
    """
    by_id = {newsletter.id: newsletter for newsletter in existing}
    by_id.update((newsletter.id, newsletter) for newsletter in updates)
    return sorted(by_id.values(), key=lambda item: (item.received_date, item.id))


def newest_created_at(rows: Iterable[dict[str, Any]]) -> datetime | None:
    """Return the newest `created_at` among fetched rows, or None if none have one."""
    timestamps = [
        datetime.fromisoformat(row["created_at"])
        for row in rows
        if row.get("created_at")
    ]
    return max(timestamps, default=None)


def advance_cursor(current: datetime, rows: Iterable[dict[str, Any]]) -> datetime:
    """Move the snapshot cursor to the newest fetched row, never backwards."""
    newest = newest_created_at(rows)
    return max(current, newest) if newest else current
