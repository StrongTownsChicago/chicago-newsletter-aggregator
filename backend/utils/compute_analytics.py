"""
Compute analytics JSON files for the local /analytics dashboard.

Fetches newsletters and sources from Supabase (read-only), computes metrics
with the pure functions in `analytics/`, and writes compact JSON files that
the frontend loads at build/dev time.

Usage:
    uv run python -m utils.compute_analytics
    uv run python -m utils.compute_analytics --output-dir /tmp/analytics
    uv run python -m utils.compute_analytics --min-term-newsletters 30
"""

import argparse
import json
from datetime import datetime
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

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "frontend" / "src" / "data" / "analytics"

# PostgREST caps rows per request; smaller pages also keep plain_text payloads manageable.
FETCH_PAGE_SIZE = 500
NEWSLETTER_COLUMNS = (
    "id, received_date, source_id, subject, plain_text, topics, relevance_score"
)
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


def fetch_all_rows(
    supabase: Any, table: str, columns: str, order_column: str
) -> list[dict[str, Any]]:
    """Fetch every row of a table, one page at a time."""
    rows: list[dict[str, Any]] = []
    while True:
        page = (
            supabase.table(table)
            .select(columns)
            .order(order_column)
            .range(len(rows), len(rows) + FETCH_PAGE_SIZE - 1)
            .execute()
            .data
        )
        rows.extend(page)
        if len(page) < FETCH_PAGE_SIZE:
            return rows


def fetch_records() -> tuple[list[SourceRecord], list[NewsletterRecord]]:
    """Load all sources and newsletters as typed records."""
    supabase = get_supabase_client()
    sources = [
        parse_source_row(row)
        for row in fetch_all_rows(supabase, "sources", SOURCE_COLUMNS, "id")
    ]
    newsletters = [
        parse_newsletter_row(row)
        for row in fetch_all_rows(supabase, "newsletters", NEWSLETTER_COLUMNS, "id")
    ]
    return sources, newsletters


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
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    print("Fetching sources and newsletters from Supabase...")
    sources, newsletters = fetch_records()
    print(
        f"Fetched {len(sources)} sources and {len(newsletters)} newsletters. Computing..."
    )
    outputs = compute_outputs(
        sources, newsletters, args.min_term_newsletters, datetime.now(CHICAGO_TIMEZONE)
    )
    sizes = write_outputs(outputs, args.output_dir)
    print_report(outputs, sizes, args.output_dir)


if __name__ == "__main__":
    main()
