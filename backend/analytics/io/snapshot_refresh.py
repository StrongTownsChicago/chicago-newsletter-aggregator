"""Bring the local analytics snapshot up to date from Supabase, gently.

The production database has a small disk IO budget, so rows are read in small
pages with a pause between them, and the default refresh fetches only
newsletters created since the snapshot's cursor. `load_or_refresh_snapshot`
picks the mode `cli.compute_analytics` was run with.
"""

import argparse
import time
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any

from analytics.io.snapshot_store import load_snapshot, save_snapshot
from analytics.records import SourceRecord, parse_newsletter_row, parse_source_row
from analytics.snapshot import (
    Snapshot,
    advance_cursor,
    merge_newsletters,
    newest_created_at,
)
from shared.db import get_supabase_client

# Small pages with a pause between them keep reads well under the database's
# disk IO budget; repeated full reads of every plain_text exhausted it once.
FETCH_PAGE_SIZE = 100
FETCH_PAUSE_SECONDS = 1.0
# Re-fetch this far behind the cursor so rows committed late are not missed.
INCREMENTAL_OVERLAP = timedelta(days=1)
NEWSLETTER_COLUMNS = "id, created_at, received_date, source_id, subject, plain_text"
SOURCE_COLUMNS = "id, name, ward_number, source_type"


def fetch_rows(
    supabase: Any,
    table: str,
    columns: str,
    created_since: datetime | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Fetch rows one small page at a time, pausing between pages.

    Pages are ordered by the unique `id`, so offsets stay stable. Errors are
    not retried: a struggling database should be left alone, not hammered.
    """
    rows: list[dict[str, Any]] = []
    while True:
        query = supabase.table(table).select(columns)
        if created_since is not None:
            query = query.gte("created_at", created_since.isoformat())
        page = (
            query.order("id")
            .range(len(rows), len(rows) + FETCH_PAGE_SIZE - 1)
            .execute()
            .data
        )
        rows.extend(page)
        if len(page) < FETCH_PAGE_SIZE:
            return rows
        sleep(FETCH_PAUSE_SECONDS)


def fetch_sources(
    supabase: Any, sleep: Callable[[float], None] = time.sleep
) -> list[SourceRecord]:
    """Fetch every source (a small table, so always read in full)."""
    return [
        parse_source_row(row)
        for row in fetch_rows(supabase, "sources", SOURCE_COLUMNS, sleep=sleep)
    ]


def refresh_snapshot(
    supabase: Any, snapshot: Snapshot, sleep: Callable[[float], None] = time.sleep
) -> tuple[Snapshot, int]:
    """Bring the snapshot up to date without re-reading old newsletters.

    Fetches newsletters created since the snapshot's cursor (minus an
    overlap) and returns the updated snapshot with the number of rows fetched.
    """
    created_since = snapshot.fetched_through - INCREMENTAL_OVERLAP
    sources = fetch_sources(supabase, sleep)
    rows = fetch_rows(supabase, "newsletters", NEWSLETTER_COLUMNS, created_since, sleep)
    newsletters = merge_newsletters(
        snapshot.newsletters, (parse_newsletter_row(row) for row in rows)
    )
    updated = Snapshot(
        sources=sources,
        newsletters=newsletters,
        fetched_through=advance_cursor(snapshot.fetched_through, rows),
    )
    return updated, len(rows)


def build_full_snapshot(
    supabase: Any, now: datetime, sleep: Callable[[float], None] = time.sleep
) -> Snapshot:
    """Read every newsletter to build a snapshot from scratch."""
    sources = fetch_sources(supabase, sleep)
    rows = fetch_rows(supabase, "newsletters", NEWSLETTER_COLUMNS, sleep=sleep)
    newsletters = merge_newsletters([], (parse_newsletter_row(row) for row in rows))
    # An empty table has nothing to resume from, so the cursor starts now.
    return Snapshot(sources, newsletters, newest_created_at(rows) or now)


def load_or_refresh_snapshot(args: argparse.Namespace, now: datetime) -> Snapshot:
    """Produce the snapshot to compute from, according to the chosen mode."""
    if args.full_refresh:
        print(
            "Full refresh: reading every newsletter from Supabase in pages of "
            f"{FETCH_PAGE_SIZE}, pausing {FETCH_PAUSE_SECONDS}s between pages..."
        )
        snapshot = build_full_snapshot(get_supabase_client(), now)
        save_snapshot(args.snapshot_dir, snapshot, now)
        print(f"Saved a snapshot of {len(snapshot.newsletters)} newsletters.")
        return snapshot

    snapshot = load_snapshot(args.snapshot_dir)
    print(
        f"Loaded a snapshot of {len(snapshot.newsletters)} newsletters "
        f"(fetched through {snapshot.fetched_through.isoformat()})."
    )
    if args.offline:
        return snapshot

    print("Fetching sources and newsletters created since the snapshot...")
    snapshot, fetched = refresh_snapshot(get_supabase_client(), snapshot)
    save_snapshot(args.snapshot_dir, snapshot, now)
    print(
        f"Fetched {fetched} recent newsletter rows; the snapshot now has "
        f"{len(snapshot.newsletters)} newsletters."
    )
    return snapshot
