"""
Compute analytics JSON files for the unlisted /analytics dashboard.

Reads newsletters and sources from a local snapshot (see
`utils/analytics_snapshot.py`), computes metrics with the pure functions in
`analytics/`, and writes compact JSON files to `frontend/public/analytics-data/`.
That folder is committed and deployed as public static files, which the page
fetches at runtime. To publish a refresh: run this script, commit the folder,
and push.

The production database has a small disk IO budget, so it is read gently:

- default: fetch all sources, the newsletters created since the snapshot's
  cursor (with a short overlap), and the topics of older rows that had no
  LLM topics yet; merge them into the snapshot, then compute.
- --offline: never contact the database; compute from the snapshot as-is.
- --full-refresh: rebuild the snapshot by reading every newsletter. Heavy;
  use rarely: on a fresh checkout, or after reprocessing that edits rows the
  default mode does not revisit (privacy re-sanitization of plain_text, LLM
  re-runs over already-processed rows) or after deletions.

Usage:
    uv run python -m utils.compute_analytics
    uv run python -m utils.compute_analytics --offline
    uv run python -m utils.compute_analytics --full-refresh
    uv run python -m utils.compute_analytics --output-dir /tmp/analytics
    uv run python -m utils.compute_analytics --min-term-newsletters 30
"""

import argparse
import io
import json
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from analytics.facts import (
    build_metadata,
    build_newsletter_facts,
    build_source_coverage,
)
from analytics.records import (
    CHICAGO_TIMEZONE,
    NewsletterRecord,
    SourceRecord,
    month_key,
    parse_newsletter_row,
    parse_source_row,
)
from analytics.snapshot import (
    Snapshot,
    advance_cursor,
    apply_llm_metadata,
    ids_missing_llm_metadata,
    merge_newsletters,
    newest_created_at,
)
from analytics.terms import (
    NewsletterTerms,
    build_name_tokens_by_ward,
    build_newsletter_terms,
    build_term_index,
    compute_distinctive_terms,
    compute_rising_terms,
    select_latest_complete_month,
    select_vocabulary,
)
from shared.db import get_supabase_client
from utils.analytics_snapshot import (
    DEFAULT_SNAPSHOT_DIR,
    SnapshotError,
    load_snapshot,
    save_snapshot,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "frontend" / "public" / "analytics-data"

# Small pages with a pause between them keep reads well under the database's
# disk IO budget; repeated full reads of every plain_text exhausted it once.
FETCH_PAGE_SIZE = 100
FETCH_PAUSE_SECONDS = 1.0
# Re-fetch this far behind the cursor so rows committed late are not missed.
INCREMENTAL_OVERLAP = timedelta(days=1)
NEWSLETTER_COLUMNS = (
    "id, created_at, received_date, source_id, subject, plain_text, topics"
)
# Only these columns change when LLM processing runs after ingestion.
LLM_METADATA_COLUMNS = "id, topics"
SOURCE_COLUMNS = "id, name, ward_number, source_type"

# Terms in fewer newsletters are mostly one-off names and typos; 20 keeps the
# term index around a few MB for the full archive.
DEFAULT_MIN_TERM_NEWSLETTERS = 20
DISTINCTIVE_TOP_N = 20
DISTINCTIVE_MIN_WARD_NEWSLETTERS = 5
DISTINCTIVE_MIN_TERM_NEWSLETTERS_IN_WARD = 3
DISTINCTIVE_MAX_WARD_SHARE = 0.6
RISING_BASELINE_MONTHS = 6
RISING_MIN_LATEST_NEWSLETTERS = 5
RISING_MIN_LATEST_SOURCES = 2
RISING_TOP_N = 30
SAMPLE_SIZE = 8


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


def fetch_rows_by_id(
    supabase: Any,
    table: str,
    columns: str,
    ids: list[str],
    sleep: Callable[[float], None] = time.sleep,
) -> list[dict[str, Any]]:
    """Fetch specific rows in batches of FETCH_PAGE_SIZE ids, pausing between batches."""
    rows: list[dict[str, Any]] = []
    for start in range(0, len(ids), FETCH_PAGE_SIZE):
        if start:
            sleep(FETCH_PAUSE_SECONDS)
        batch = ids[start : start + FETCH_PAGE_SIZE]
        rows.extend(
            supabase.table(table).select(columns).in_("id", batch).execute().data
        )
    return rows


def fetch_sources(
    supabase: Any, sleep: Callable[[float], None] = time.sleep
) -> list[SourceRecord]:
    """Fetch every source (a small table, so always read in full)."""
    return [
        parse_source_row(row)
        for row in fetch_rows(supabase, "sources", SOURCE_COLUMNS, sleep=sleep)
    ]


@dataclass(frozen=True)
class RefreshCounts:
    new_rows: int
    metadata_rows: int


def refresh_snapshot(
    supabase: Any, snapshot: Snapshot, sleep: Callable[[float], None] = time.sleep
) -> tuple[Snapshot, RefreshCounts]:
    """Bring the snapshot up to date without re-reading old newsletter text.

    Fetches newsletters created since the snapshot's cursor (minus an
    overlap), then re-checks only the LLM metadata columns of older rows that
    were still unprocessed, since LLM processing often runs days later.
    """
    created_since = snapshot.fetched_through - INCREMENTAL_OVERLAP
    sources = fetch_sources(supabase, sleep)
    rows = fetch_rows(supabase, "newsletters", NEWSLETTER_COLUMNS, created_since, sleep)
    newsletters = merge_newsletters(
        snapshot.newsletters, (parse_newsletter_row(row) for row in rows)
    )

    fetched_ids = {str(row["id"]) for row in rows}
    pending_ids = [
        newsletter_id
        for newsletter_id in ids_missing_llm_metadata(newsletters)
        if newsletter_id not in fetched_ids
    ]
    metadata_rows = fetch_rows_by_id(
        supabase, "newsletters", LLM_METADATA_COLUMNS, pending_ids, sleep
    )

    updated = Snapshot(
        sources=sources,
        newsletters=apply_llm_metadata(newsletters, metadata_rows),
        fetched_through=advance_cursor(snapshot.fetched_through, rows),
    )
    return updated, RefreshCounts(len(rows), len(metadata_rows))


def build_full_snapshot(
    supabase: Any, now: datetime, sleep: Callable[[float], None] = time.sleep
) -> Snapshot:
    """Read every newsletter to build a snapshot from scratch."""
    sources = fetch_sources(supabase, sleep)
    rows = fetch_rows(supabase, "newsletters", NEWSLETTER_COLUMNS, sleep=sleep)
    newsletters = merge_newsletters([], (parse_newsletter_row(row) for row in rows))
    # An empty table has nothing to resume from, so the cursor starts now.
    return Snapshot(sources, newsletters, newest_created_at(rows) or now)


def compute_outputs(
    sources: list[SourceRecord],
    newsletters: list[NewsletterRecord],
    min_term_newsletters: int,
    generated_at: datetime,
) -> dict[str, Any]:
    """Compute every analytics output, keyed by output file stem."""
    sources_by_id = {source.id: source for source in sources}
    documents: list[NewsletterTerms] = build_newsletter_terms(
        newsletters, sources_by_id
    )
    vocabulary = select_vocabulary(documents, min_term_newsletters)

    latest_month = select_latest_complete_month(
        (document.month for document in documents), month_key(generated_at.date())
    )
    rising = (
        compute_rising_terms(
            documents,
            vocabulary,
            latest_month=latest_month,
            baseline_months=RISING_BASELINE_MONTHS,
            min_latest_newsletters=RISING_MIN_LATEST_NEWSLETTERS,
            min_latest_sources=RISING_MIN_LATEST_SOURCES,
            top_n=RISING_TOP_N,
        )
        if latest_month
        else {
            "latest_month": None,
            "baseline_months": [],
            "terms": [],
            "latest_newsletters": 0,
            "baseline_newsletters": 0,
        }
    )

    return {
        "metadata": build_metadata(
            newsletters, sources, len(vocabulary), min_term_newsletters, generated_at
        ),
        "newsletters": {
            "newsletters": build_newsletter_facts(newsletters, sources_by_id)
        },
        "sources": {"sources": build_source_coverage(sources, newsletters)},
        "terms": {
            "min_newsletters": min_term_newsletters,
            **build_term_index(documents, vocabulary),
        },
        "distinctive": {
            "wards": compute_distinctive_terms(
                documents,
                vocabulary,
                name_tokens_by_ward=build_name_tokens_by_ward(sources),
                top_n=DISTINCTIVE_TOP_N,
                min_ward_newsletters=DISTINCTIVE_MIN_WARD_NEWSLETTERS,
                min_term_newsletters_in_ward=DISTINCTIVE_MIN_TERM_NEWSLETTERS_IN_WARD,
                max_ward_share=DISTINCTIVE_MAX_WARD_SHARE,
            )
        },
        "rising": rising,
    }


def write_outputs(outputs: dict[str, Any], output_dir: Path) -> dict[str, int]:
    """Write each output as compact JSON; return file sizes in bytes."""
    output_dir.mkdir(parents=True, exist_ok=True)
    sizes: dict[str, int] = {}
    for stem, payload in outputs.items():
        path = output_dir / f"{stem}.json"
        path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
        sizes[path.name] = path.stat().st_size
    return sizes


def print_report(
    outputs: dict[str, Any], sizes: dict[str, int], output_dir: Path
) -> None:
    """Print file sizes and a few sample results for a quick sanity check."""
    print(f"\nWrote analytics to {output_dir}")
    for name, size in sizes.items():
        print(f"  {name:<20} {size / 1024:>9.1f} KB")

    metadata = outputs["metadata"]
    print(
        f"\n{metadata['newsletter_count']} newsletters from {metadata['source_count']} sources, "
        f"{metadata['first_date']} to {metadata['last_date']}; "
        f"{metadata['term_count']} indexed terms (>= {metadata['min_term_newsletters']} newsletters)"
    )

    rising = outputs["rising"]
    print(
        f"\nRising terms in {rising['latest_month']} vs {', '.join(rising['baseline_months'])}:"
    )
    for item in rising["terms"][:SAMPLE_SIZE]:
        print(
            f"  {item['term']:<30} x{item['ratio']:<6} "
            f"({item['latest_newsletters']} newsletters, {item['latest_sources']} sources)"
        )

    print("\nDistinctive vocabulary (sample wards):")
    for ward, terms in list(outputs["distinctive"]["wards"].items())[:SAMPLE_SIZE]:
        print(
            f"  Ward {ward}: {', '.join(item['term'] for item in terms[:SAMPLE_SIZE])}"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compute analytics JSON for the local dashboard."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help=f"Directory for JSON output (default: {DEFAULT_OUTPUT_DIR})",
    )
    parser.add_argument(
        "--min-term-newsletters",
        type=int,
        default=DEFAULT_MIN_TERM_NEWSLETTERS,
        help="Only index terms found in at least this many newsletters "
        f"(default: {DEFAULT_MIN_TERM_NEWSLETTERS})",
    )
    parser.add_argument(
        "--snapshot-dir",
        type=Path,
        default=DEFAULT_SNAPSHOT_DIR,
        help=f"Local snapshot directory (default: {DEFAULT_SNAPSHOT_DIR})",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--offline",
        action="store_true",
        help="Compute from the snapshot only; never contact the database",
    )
    mode.add_argument(
        "--full-refresh",
        action="store_true",
        help="Rebuild the snapshot by reading every newsletter (heavy; use rarely)",
    )
    return parser.parse_args()


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
    snapshot, counts = refresh_snapshot(get_supabase_client(), snapshot)
    save_snapshot(args.snapshot_dir, snapshot, now)
    print(
        f"Fetched {counts.new_rows} recent newsletter rows and LLM metadata for "
        f"{counts.metadata_rows} older ones; the snapshot now has "
        f"{len(snapshot.newsletters)} newsletters."
    )
    return snapshot


def main() -> None:
    # Newsletter terms include accented words (e.g. Spanish), which the default
    # Windows console encoding cannot print when output is redirected.
    if isinstance(sys.stdout, io.TextIOWrapper):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = parse_args()
    now = datetime.now(CHICAGO_TIMEZONE)
    try:
        snapshot = load_or_refresh_snapshot(args, now)
    except SnapshotError as error:
        sys.exit(
            f"{error}\nRebuild it with --full-refresh (reads every newsletter, "
            "so run it when the site is quiet), or restore a saved snapshot there."
        )

    print("Computing...")
    outputs = compute_outputs(
        snapshot.sources, snapshot.newsletters, args.min_term_newsletters, now
    )
    sizes = write_outputs(outputs, args.output_dir)
    print_report(outputs, sizes, args.output_dir)


if __name__ == "__main__":
    main()
