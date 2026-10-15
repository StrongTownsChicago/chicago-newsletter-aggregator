"""Per-newsletter facts, per-source coverage, and dataset metadata."""

from collections import defaultdict
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from analytics.records import NewsletterRecord, SourceRecord
from analytics.text import count_words

# Bodies shorter than this are mostly image-only issues or "view in browser"
# stubs whose content was not extracted, so a term missing from them says
# little about what the alderman wrote.
MIN_EXTRACTED_WORDS = 80


def is_text_unavailable(plain_text: str) -> bool:
    """True when too little text was extracted to analyze the newsletter's content."""
    return count_words(plain_text) < MIN_EXTRACTED_WORDS


def build_newsletter_fact(
    newsletter: NewsletterRecord, source: SourceRecord | None, lens_ids: list[str]
) -> dict[str, Any]:
    """Shape one newsletter into a compact, body-free fact row.

    The `lenses` field holds lens_ids, the keyword lenses the newsletter
    mentions (see `analytics.lenses`).
    The LLM topics and relevance score are deliberately left out: the topic
    list changed over time without relabeling and misses most of what
    aldermen write about, and the score mostly tracks newsletter length.
    """
    return {
        "id": newsletter.id,
        "date": newsletter.received_date.isoformat(),
        "source_id": newsletter.source_id,
        "ward": source.ward if source else None,
        "alder": source.name if source else None,
        "lenses": lens_ids,
        "words": count_words(newsletter.plain_text),
        "text_unavailable": is_text_unavailable(newsletter.plain_text),
    }


def build_newsletter_facts(
    newsletters: list[NewsletterRecord],
    sources_by_id: dict[int, SourceRecord],
    lenses_by_newsletter: Mapping[str, list[str]],
) -> list[dict[str, Any]]:
    """Shape every newsletter into a fact row, ordered by date then id.

    Newsletters missing from lenses_by_newsletter mention no lens.
    """
    ordered = sorted(newsletters, key=lambda item: (item.received_date, item.id))
    return [
        build_newsletter_fact(
            newsletter,
            sources_by_id.get(newsletter.source_id)
            if newsletter.source_id is not None
            else None,
            lenses_by_newsletter.get(newsletter.id, []),
        )
        for newsletter in ordered
    ]


def build_source_coverage(
    sources: list[SourceRecord], newsletters: list[NewsletterRecord]
) -> list[dict[str, Any]]:
    """Summarize each source's newsletter count and first/last newsletter dates.

    Sources without newsletters are included with a count of zero so gaps in
    coverage are visible.
    """
    dates_by_source: dict[int, list[date]] = defaultdict(list)
    for newsletter in newsletters:
        if newsletter.source_id is not None:
            dates_by_source[newsletter.source_id].append(newsletter.received_date)

    def summarize(source: SourceRecord) -> dict[str, Any]:
        source_dates = dates_by_source.get(source.id, [])
        return {
            "id": source.id,
            "name": source.name,
            "ward": source.ward,
            "source_type": source.source_type,
            "first_date": min(source_dates).isoformat() if source_dates else None,
            "last_date": max(source_dates).isoformat() if source_dates else None,
            "newsletters": len(source_dates),
        }

    return [summarize(source) for source in sorted(sources, key=lambda s: s.id)]


def build_metadata(
    newsletters: list[NewsletterRecord],
    sources: list[SourceRecord],
    term_count: int,
    min_term_newsletters: int,
    generated_at: datetime,
) -> dict[str, Any]:
    """Describe the generated dataset: when, how much, and which dates it spans."""
    dates = [newsletter.received_date for newsletter in newsletters]
    return {
        "generated_at": generated_at.isoformat(),
        "newsletter_count": len(newsletters),
        "source_count": len(sources),
        "first_date": min(dates).isoformat() if dates else None,
        "last_date": max(dates).isoformat() if dates else None,
        "term_count": term_count,
        "min_term_newsletters": min_term_newsletters,
    }
