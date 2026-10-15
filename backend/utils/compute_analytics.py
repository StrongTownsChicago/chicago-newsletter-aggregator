"""
Compute analytics JSON files for the unlisted /analytics dashboard.

Reads newsletters and sources from a local snapshot (see
`utils/analytics_snapshot.py`), computes metrics with the pure functions in
`analytics/`, and writes compact JSON files to `frontend/public/analytics-data/`.
That folder is committed and deployed as public static files, which the page
fetches at runtime. To publish a refresh: run this script, commit the folder,
and push.

The production database has a small disk IO budget, so it is read gently:

- default: fetch all sources and the newsletters created since the
  snapshot's cursor (with a short overlap); merge them into the snapshot,
  then compute. Older rows are never re-read: analytics uses only text and
  dates, not the LLM metadata that processing adds to rows later.
- --offline: never contact the database; compute from the snapshot as-is.
- --full-refresh: rebuild the snapshot by reading every newsletter. Heavy;
  use rarely: on a fresh checkout, or after reprocessing that edits the text
  of rows the default mode does not revisit (privacy re-sanitization of
  plain_text) or after deletions.

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
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from analytics.boilerplate import remove_source_boilerplate
from analytics.facts import (
    build_metadata,
    build_newsletter_facts,
    build_source_coverage,
    is_text_unavailable,
)
from analytics.lenses import (
    LENSES,
    LensMatcher,
    match_newsletters,
    summarize_lens_hits,
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
NEWSLETTER_COLUMNS = "id, created_at, received_date, source_id, subject, plain_text"
SOURCE_COLUMNS = "id, name, ward_number, source_type"

# Text repeated in at least this share of one source's newsletters is template
# (footers, office hours, resource lists) and is left out of every term metric.
BOILERPLATE_MIN_SHARE_PERCENT = 30
# Sources with fewer newsletters keep all their text: a few consecutive issues
# repeating one event announcement would otherwise look like a template.
BOILERPLATE_MIN_SOURCE_NEWSLETTERS = 10
# Terms in fewer newsletters are mostly one-off names and typos; 20 keeps the
# term index around a few MB for the full archive.
DEFAULT_MIN_TERM_NEWSLETTERS = 20
DISTINCTIVE_TOP_N = 20
DISTINCTIVE_MIN_WARD_NEWSLETTERS = 5
DISTINCTIVE_MIN_TERM_NEWSLETTERS_IN_WARD = 3
DISTINCTIVE_MAX_WARD_SHARE = 0.6
# Keyword lenses match on boilerplate-cleaned text. Lenses feed ward reach
# ("did this ward write about X this month"), and a standing block such as a
# resource directory repeated in every issue would answer yes every month
# whether or not the ward said anything new, flattening the monthly calendar
# (on raw text, immigration reaches 14-18 wards every month of 2026; cleaned,
# it falls from 17 in January to 10 in August). The cost: a ward whose only
# coverage of a subject is its standing block is not counted. Set False to
# match raw text instead.
MATCH_LENSES_ON_CLEANED_TEXT = True
# A newsletter mentions a lens when the lens's phrases occur at least this
# many separate times in it (the same phrase twice counts; phrases that
# overlap or touch, like "city council meeting", count once). One passing
# mention, such
# as early voting "at the library" or "call 311 while our office is closed",
# does not make a newsletter about parks or city services, and counting those
# puts nearly every ward on nearly every lens every month.
LENS_MIN_MENTIONS = 2
# Rising terms compare the latest complete month with the median of this
# many months before it, counting wards rather than newsletters.
RISING_BASELINE_MONTHS = 3
# A rising term must be mentioned by at least this many wards in the latest
# month and by at least this many more wards than in a typical baseline month.
RISING_MIN_LATEST_WARDS = 5
RISING_MIN_WARD_GAIN = 3
RISING_TOP_N = 15
SAMPLE_SIZE = 8
LENS_REPORT_TOP_PHRASES = 4


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


def compute_outputs(
    sources: list[SourceRecord],
    newsletters: list[NewsletterRecord],
    min_term_newsletters: int,
    generated_at: datetime,
) -> dict[str, Any]:
    """Compute every analytics output, keyed by output file stem."""
    sources_by_id = {source.id: source for source in sources}
    content_newsletters = remove_source_boilerplate(
        newsletters,
        min_share_percent=BOILERPLATE_MIN_SHARE_PERCENT,
        min_source_newsletters=BOILERPLATE_MIN_SOURCE_NEWSLETTERS,
    )
    # Too little text was extracted from these to tell what they mention.
    unavailable_ids = {
        newsletter.id
        for newsletter in newsletters
        if is_text_unavailable(newsletter.plain_text)
    }
    documents: list[NewsletterTerms] = build_newsletter_terms(
        content_newsletters, sources_by_id
    )
    vocabulary = select_vocabulary(documents, min_term_newsletters)

    lens_newsletters = (
        content_newsletters if MATCH_LENSES_ON_CLEANED_TEXT else newsletters
    )
    matcher = LensMatcher(LENSES)
    lens_matches = match_newsletters(
        (item for item in lens_newsletters if item.id not in unavailable_ids),
        matcher,
    )
    lenses_by_newsletter = {
        newsletter_id: matcher.lenses_mentioned(
            matches.lens_mentions, LENS_MIN_MENTIONS
        )
        for newsletter_id, matches in lens_matches.items()
    }

    latest_month = select_latest_complete_month(
        (document.month for document in documents), month_key(generated_at.date())
    )
    rising = (
        compute_rising_terms(
            [doc for doc in documents if doc.newsletter_id not in unavailable_ids],
            vocabulary,
            latest_month=latest_month,
            baseline_months=RISING_BASELINE_MONTHS,
            min_latest_wards=RISING_MIN_LATEST_WARDS,
            min_ward_gain=RISING_MIN_WARD_GAIN,
            top_n=RISING_TOP_N,
        )
        if latest_month
        else {
            "latest_month": None,
            "baseline_months": [],
            "latest_active_wards": 0,
            "baseline_active_wards": [],
            "terms": [],
        }
    )

    return {
        "metadata": {
            **build_metadata(
                newsletters,
                sources,
                len(vocabulary),
                min_term_newsletters,
                generated_at,
            ),
            # Published so the methodology page states the rule that was applied.
            "boilerplate": {
                "min_share_percent": BOILERPLATE_MIN_SHARE_PERCENT,
                "min_source_newsletters": BOILERPLATE_MIN_SOURCE_NEWSLETTERS,
            },
        },
        "newsletters": {
            "newsletters": build_newsletter_facts(
                newsletters, sources_by_id, lenses_by_newsletter
            )
        },
        "lenses": {
            "text": "cleaned" if MATCH_LENSES_ON_CLEANED_TEXT else "raw",
            "min_mentions": LENS_MIN_MENTIONS,
            "readable_newsletters": len(lens_matches),
            "lenses": summarize_lens_hits(
                matcher,
                {key: matches.phrases for key, matches in lens_matches.items()},
                lenses_by_newsletter,
            ),
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

    lenses = outputs["lenses"]
    readable = lenses["readable_newsletters"]
    print(
        f"\nLens hit rates over {readable} newsletters with readable text "
        f"({lenses['text']} text, mentioned at least "
        f"{lenses['min_mentions']} separate times):"
    )
    for lens in lenses["lenses"]:
        top_phrases = ", ".join(
            f"{item['phrase']} ({item['newsletters']})"
            for item in lens["phrases"][:LENS_REPORT_TOP_PHRASES]
        )
        share = lens["newsletters"] / readable if readable else 0
        print(f"  {lens['label']:<34} {share:6.1%}  {top_phrases}")

    rising = outputs["rising"]
    if rising["latest_month"]:
        print(
            f"\nRising terms in {rising['latest_month']} "
            f"({rising['latest_active_wards']} wards active) vs the median of "
            f"{', '.join(rising['baseline_months'])}:"
        )
    for item in rising["terms"][:SAMPLE_SIZE]:
        print(
            f"  {item['term']:<30} {item['latest_wards']:>3} wards "
            f"(baseline {item['baseline_wards']:g}, +{item['ward_gain']:g})"
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
    snapshot, fetched = refresh_snapshot(get_supabase_client(), snapshot)
    save_snapshot(args.snapshot_dir, snapshot, now)
    print(
        f"Fetched {fetched} recent newsletter rows; the snapshot now has "
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
