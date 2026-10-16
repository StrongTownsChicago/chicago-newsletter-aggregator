"""Compute analytics JSON files for the unlisted /analytics dashboard.

Reads newsletters and sources from a local snapshot (see
`analytics/io/snapshot_store.py`), computes metrics with the pure functions in
`analytics/`, and writes compact JSON files to `frontend/public/analytics-data/`.
That folder is committed and deployed as public static files, which the page
fetches at runtime. It also writes two small summaries to
`frontend/src/data/` for the public pages: per-ward "at a glance" figures,
imported by the server-rendered ward pages, and monthly citywide reports,
prerendered at build time. To publish a refresh: run this script, commit both
folders, and push.

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
    uv run python -m cli.compute_analytics
    uv run python -m cli.compute_analytics --offline
    uv run python -m cli.compute_analytics --full-refresh
"""

import argparse
import io
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from analytics.boilerplate import remove_source_boilerplate
from analytics.facts import (
    build_metadata,
    build_newsletter_facts,
    build_source_coverage,
    is_text_unavailable,
)
from analytics.io.output import print_report, print_sizes, write_outputs
from analytics.io.snapshot_refresh import load_or_refresh_snapshot
from analytics.io.snapshot_store import DEFAULT_SNAPSHOT_DIR, SnapshotError
from analytics.lens_matching import (
    LensMatcher,
    TextMatches,
    match_newsletters,
    summarize_lens_hits,
)
from analytics.lenses import LENSES
from analytics.monthly_reports import MonthlyReportSettings, build_monthly_reports
from analytics.records import (
    CHICAGO_TIMEZONE,
    NewsletterRecord,
    SourceRecord,
    select_as_of_month,
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
from analytics.topic_reach import (
    build_topic_labels,
    build_topic_newsletters,
    select_broad_complete_months,
)
from analytics.ward_glance import WardGlanceSettings, build_ward_glances

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUTPUT_DIR = REPO_ROOT / "frontend" / "public" / "analytics-data"
# Imported by page code rather than fetched, so keep these files small: the
# ward summary is bundled into the server worker.
DEFAULT_SITE_DATA_DIR = REPO_ROOT / "frontend" / "src" / "data"

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
# Distinctive terms in exactly the same newsletters of a ward are fragments of
# one standing block and are listed as one entry (ward 46: 30 terms in the same
# 24 of 81 issues). A word and a phrase containing it ("truman" and "truman
# college") are merged when the Jaccard similarity of their newsletter sets is
# at least this. Looser matching of unrelated terms merged whole digests: ward
# 46 runs several standing sections in nearly the same issues.
DISTINCTIVE_MIN_NESTED_TERM_SIMILARITY = 0.8
# Lenses match boilerplate-cleaned text. They feed ward reach ("did this ward write
# about X this month"), and a standing block repeated in every issue, such as a
# resource directory, would answer yes every month whether or not the ward said
# anything new, flattening the monthly calendar (raw text: immigration reaches 14-18
# wards every month of 2026; cleaned, 17 in January to 10 in August). Cost: a ward
# covering a subject only in its standing block is uncounted. Set False for raw text.
MATCH_LENSES_ON_CLEANED_TEXT = True
# A newsletter mentions a lens when the lens's phrases occur at least this many
# separate times in it (the same phrase twice counts; phrases that overlap or touch,
# like "city council meeting", count once). One passing mention, such as early
# voting "at the library" or "call 311 while our office is closed", does not make a
# newsletter about parks or city services, and counting those puts nearly every
# ward on nearly every lens every month.
LENS_MIN_MENTIONS = 2
# Rising terms compare the latest complete month with the median of this
# many months before it, counting wards rather than newsletters.
RISING_BASELINE_MONTHS = 3
# A rising term must be mentioned by at least this many wards in the latest
# month and by at least this many more wards than in a typical baseline month.
RISING_MIN_LATEST_WARDS = 5
RISING_MIN_WARD_GAIN = 3
RISING_TOP_N = 15
# Rising terms are phrases: single words rise every month for unrelated
# reasons (September 2026: "fall", "pro", "moving"), while the phrases that
# carried those stories ("residential landlord", "tenant ordinance") rise too.
RISING_MIN_PHRASE_WORDS = 2
# Monthly reports cover complete months in which at least this many wards
# sent a newsletter; thinner months describe the archive's gaps, not the city.
REPORT_MIN_SENDING_WARDS = 30
MONTHLY_REPORT_SETTINGS = MonthlyReportSettings(examples_per_topic=3)
# Ward pages describe the last six complete months: recent enough to reflect
# the current office, long enough for a typical ward to send 20+ newsletters.
WARD_GLANCE_SETTINGS = WardGlanceSettings(window_months=6, top_topics=5)
# Ward pages show a topic's share of a ward's newsletters as a percentage only
# when at least this many of them could be read; below it, counts only.
MIN_WARD_TOPIC_SHARE_NEWSLETTERS = 20
# The ward summary when the archive has no complete month yet.
EMPTY_WARD_GLANCES: dict[str, Any] = {
    "latest_month": None,
    "window_months": [],
    "city_readable_wards": 0,
    "wards": {},
}


@dataclass(frozen=True)
class ArchiveAnalysis:
    """Intermediate results shared by the dashboard files and the site summaries."""

    sources: list[SourceRecord]
    newsletters: list[NewsletterRecord]
    sources_by_id: dict[int, SourceRecord]
    min_term_newsletters: int
    generated_at: datetime
    # Months from this one on may be incomplete in the snapshot.
    as_of_month: str
    # Ids of newsletters with too little extracted text to analyze.
    unavailable_ids: set[str]
    documents: list[NewsletterTerms]
    vocabulary: set[str]
    matcher: LensMatcher
    lens_matches: dict[str, TextMatches]
    lenses_by_newsletter: dict[str, list[str]]
    latest_month: str | None

    @property
    def readable_documents(self) -> list[NewsletterTerms]:
        return [
            document
            for document in self.documents
            if document.newsletter_id not in self.unavailable_ids
        ]


def analyze_archive(
    sources: list[SourceRecord],
    newsletters: list[NewsletterRecord],
    min_term_newsletters: int,
    generated_at: datetime,
) -> ArchiveAnalysis:
    """Clean, tokenize, and match topics once for every output."""
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
    lens_newsletters = (
        content_newsletters if MATCH_LENSES_ON_CLEANED_TEXT else newsletters
    )
    matcher = LensMatcher(LENSES)
    lens_matches = match_newsletters(
        (item for item in lens_newsletters if item.id not in unavailable_ids),
        matcher,
    )
    as_of_month = select_as_of_month(
        (newsletter.received_date for newsletter in newsletters), generated_at.date()
    )
    return ArchiveAnalysis(
        sources=sources,
        newsletters=newsletters,
        sources_by_id=sources_by_id,
        min_term_newsletters=min_term_newsletters,
        generated_at=generated_at,
        as_of_month=as_of_month,
        unavailable_ids=unavailable_ids,
        documents=documents,
        vocabulary=select_vocabulary(documents, min_term_newsletters),
        matcher=matcher,
        lens_matches=lens_matches,
        lenses_by_newsletter={
            newsletter_id: matcher.lenses_mentioned(
                matches.lens_mentions, LENS_MIN_MENTIONS
            )
            for newsletter_id, matches in lens_matches.items()
        },
        latest_month=select_latest_complete_month(
            (document.month for document in documents), as_of_month
        ),
    )


def compute_outputs(analysis: ArchiveAnalysis) -> dict[str, Any]:
    """Compute every dashboard output, keyed by output file stem."""
    sources = analysis.sources
    newsletters = analysis.newsletters
    documents = analysis.documents
    vocabulary = analysis.vocabulary
    matcher = analysis.matcher
    lens_matches = analysis.lens_matches
    lenses_by_newsletter = analysis.lenses_by_newsletter
    latest_month = analysis.latest_month
    min_term_newsletters = analysis.min_term_newsletters

    rising = (
        compute_rising_terms(
            analysis.readable_documents,
            vocabulary,
            latest_month=latest_month,
            baseline_months=RISING_BASELINE_MONTHS,
            min_latest_wards=RISING_MIN_LATEST_WARDS,
            min_ward_gain=RISING_MIN_WARD_GAIN,
            top_n=RISING_TOP_N,
            min_phrase_words=RISING_MIN_PHRASE_WORDS,
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
        "metadata": build_metadata(
            newsletters,
            sources,
            len(vocabulary),
            min_term_newsletters,
            analysis.generated_at,
        ),
        "newsletters": {
            "newsletters": build_newsletter_facts(
                newsletters, analysis.sources_by_id, lenses_by_newsletter
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
                min_nested_term_similarity=DISTINCTIVE_MIN_NESTED_TERM_SIMILARITY,
            )
        },
        "rising": rising,
    }


def compute_site_outputs(analysis: ArchiveAnalysis) -> dict[str, Any]:
    """Compute the small summaries the public ward and report pages import,
    keyed by output file stem.

    Without a complete month there is nothing to summarize, so both are empty.
    """
    items = build_topic_newsletters(
        analysis.newsletters,
        analysis.sources_by_id,
        analysis.unavailable_ids,
        {key: matches.lens_mentions for key, matches in analysis.lens_matches.items()},
        analysis.lenses_by_newsletter,
    )
    topic_labels = build_topic_labels(LENSES)
    topic_ids = list(topic_labels)
    dates = [newsletter.received_date for newsletter in analysis.newsletters]
    data_through = max(dates).isoformat() if dates else None
    latest_month = analysis.latest_month

    ward_glance: dict[str, Any] = {
        "data_through": data_through,
        "topics": topic_labels,
        "min_share_newsletters": MIN_WARD_TOPIC_SHARE_NEWSLETTERS,
        **(
            build_ward_glances(items, topic_ids, latest_month, WARD_GLANCE_SETTINGS)
            if latest_month
            else EMPTY_WARD_GLANCES
        ),
    }
    report_months = select_broad_complete_months(
        items, analysis.as_of_month, REPORT_MIN_SENDING_WARDS
    )
    monthly_reports = {
        "data_through": data_through,
        "topics": topic_labels,
        "reports": build_monthly_reports(
            report_months, items, topic_ids, MONTHLY_REPORT_SETTINGS
        ),
    }
    return {"ward-glance": ward_glance, "monthly-reports": monthly_reports}


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
        "--site-data-dir",
        type=Path,
        default=DEFAULT_SITE_DATA_DIR,
        help="Directory for the ward and monthly report summaries "
        f"(default: {DEFAULT_SITE_DATA_DIR})",
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
    analysis = analyze_archive(
        snapshot.sources, snapshot.newsletters, args.min_term_newsletters, now
    )
    outputs = compute_outputs(analysis)
    print_sizes(write_outputs(outputs, args.output_dir), args.output_dir)
    print_sizes(
        write_outputs(compute_site_outputs(analysis), args.site_data_dir),
        args.site_data_dir,
    )
    print_report(outputs)


if __name__ == "__main__":
    main()
