"""Term-level metrics: the searchable term index, distinctive ward vocabulary,
and rising terms.

All counts are newsletter counts (how many newsletters mention a term at least
once), not raw occurrences, so one long newsletter repeating a word cannot
dominate a metric.
"""

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from typing import Any

from analytics.plurals import choose_display_forms
from analytics.records import (
    NewsletterRecord,
    SourceRecord,
    month_key,
    shift_month,
    ward_sort_key,
)
from analytics.text import MIN_TOKEN_LENGTH, WORD_PATTERN, extract_terms

# Additive smoothing for share estimates so unseen terms never divide by zero.
SHARE_SMOOTHING = 0.5


@dataclass(frozen=True)
class NewsletterTerms:
    """The distinct terms of one newsletter plus the keys used to bucket it."""

    newsletter_id: str
    source_id: int | None
    ward: str | None
    month: str
    terms: frozenset[str]


def build_newsletter_terms(
    newsletters: list[NewsletterRecord], sources_by_id: dict[int, SourceRecord]
) -> list[NewsletterTerms]:
    """Tokenize every newsletter's subject and body once.

    Singular and plural forms of a term are merged and named by their most
    common written form across these newsletters (see `analytics.plurals`).
    """

    def ward_for(source_id: int | None) -> str | None:
        source = sources_by_id.get(source_id) if source_id is not None else None
        return source.ward if source else None

    written_terms = [
        extract_terms(f"{newsletter.subject}\n{newsletter.plain_text}")
        for newsletter in newsletters
    ]
    display_forms = choose_display_forms(
        Counter(term for terms in written_terms for term in terms)
    )

    return [
        NewsletterTerms(
            newsletter_id=newsletter.id,
            source_id=newsletter.source_id,
            ward=ward_for(newsletter.source_id),
            month=month_key(newsletter.received_date),
            terms=frozenset(display_forms[term] for term in terms),
        )
        for newsletter, terms in zip(newsletters, written_terms, strict=True)
    ]


def count_newsletters_per_term(documents: Iterable[NewsletterTerms]) -> Counter[str]:
    """Count how many newsletters contain each term."""
    counts: Counter[str] = Counter()
    for document in documents:
        counts.update(document.terms)
    return counts


def select_vocabulary(
    documents: list[NewsletterTerms], min_newsletters: int
) -> set[str]:
    """Keep terms that appear in at least min_newsletters distinct newsletters."""
    return {
        term
        for term, count in count_newsletters_per_term(documents).items()
        if count >= min_newsletters
    }


def build_term_index(
    documents: list[NewsletterTerms], vocabulary: set[str]
) -> dict[str, Any]:
    """Count newsletters mentioning each vocabulary term per (source, month) bucket.

    Output is compact: `buckets` lists [source_id, month_index] pairs, and each
    term maps to a flat [bucket_index, newsletter_count, ...] array. Newsletters
    without a source cannot be placed in a bucket and are skipped.
    """
    attributed = [
        (document.source_id, document)
        for document in documents
        if document.source_id is not None
    ]
    months = sorted({document.month for _, document in attributed})
    month_index = {month: index for index, month in enumerate(months)}
    bucket_keys = sorted(
        {(source_id, document.month) for source_id, document in attributed}
    )
    bucket_index = {key: index for index, key in enumerate(bucket_keys)}

    counts_by_term: dict[str, Counter[int]] = defaultdict(Counter)
    for source_id, document in attributed:
        bucket = bucket_index[(source_id, document.month)]
        for term in document.terms & vocabulary:
            counts_by_term[term][bucket] += 1

    return {
        "months": months,
        "buckets": [
            [source_id, month_index[month]] for source_id, month in bucket_keys
        ],
        "terms": {
            term: [
                value
                for bucket, count in sorted(counts_by_term[term].items())
                for value in (bucket, count)
            ]
            for term in sorted(counts_by_term)
        },
    }


def smoothed_share(term_newsletters: int, total_newsletters: int) -> float:
    """Estimate the share of newsletters mentioning a term, with additive smoothing."""
    return (term_newsletters + SHARE_SMOOTHING) / (
        total_newsletters + 2 * SHARE_SMOOTHING
    )


@dataclass(frozen=True)
class DistinctiveTerm:
    term: str
    score: float
    lift: float
    ward_newsletters: int
    ward_share: float
    rest_share: float


@dataclass(frozen=True)
class RisingTerm:
    term: str
    ratio: float
    latest_newsletters: int
    latest_sources: int
    latest_share: float
    baseline_newsletters: int
    baseline_share: float


def build_name_tokens_by_ward(sources: Iterable[SourceRecord]) -> dict[str, set[str]]:
    """Collect the lowercase name words of each ward's sources (e.g. alderman names)."""
    tokens_by_ward: dict[str, set[str]] = defaultdict(set)
    for source in sources:
        if source.ward is not None:
            tokens_by_ward[source.ward].update(
                word
                for word in WORD_PATTERN.findall(source.name.lower())
                if len(word) >= MIN_TOKEN_LENGTH
            )
    return dict(tokens_by_ward)


def term_mentions_name(term: str, name_tokens: set[str]) -> bool:
    """True if any word of the term is one of the given name words."""
    return any(word in name_tokens for word in term.split())


def score_distinctive_term(
    term: str, ward_count: int, ward_total: int, rest_count: int, rest_total: int
) -> DistinctiveTerm:
    """Score how much more often a ward mentions a term than the rest of the city.

    Score is the ward share times the log of the smoothed lift over the rest of
    the city (a per-term KL-divergence contribution), balancing "how much more"
    against "how often" so a term used a handful of times in a small ward does
    not outrank one the ward discusses constantly.
    """
    ward_share = ward_count / ward_total
    lift = smoothed_share(ward_count, ward_total) / smoothed_share(
        rest_count, rest_total
    )
    return DistinctiveTerm(
        term=term,
        score=round(ward_share * math.log(lift), 4),
        lift=round(lift, 2),
        ward_newsletters=ward_count,
        ward_share=round(ward_share, 4),
        rest_share=round(rest_count / rest_total, 4) if rest_total else 0.0,
    )


def compute_distinctive_terms(
    documents: list[NewsletterTerms],
    vocabulary: set[str],
    name_tokens_by_ward: dict[str, set[str]],
    top_n: int,
    min_ward_newsletters: int,
    min_term_newsletters_in_ward: int,
    max_ward_share: float,
) -> dict[str, list[dict[str, Any]]]:
    """Find the top terms each ward uses far more often than the rest of the city.

    Skipped as uninformative: terms below min_term_newsletters_in_ward, terms in
    more than max_ward_share of a ward's newsletters (signatures and footers),
    and terms containing the ward's own source names (alderman self-references).
    Wards with fewer than min_ward_newsletters newsletters are omitted.
    """
    documents_by_ward: dict[str, list[NewsletterTerms]] = defaultdict(list)
    for document in documents:
        if document.ward is not None:
            documents_by_ward[document.ward].append(document)

    city_counts = count_newsletters_per_term(documents)
    city_total = len(documents)
    distinctive: dict[str, list[dict[str, Any]]] = {}

    for ward in sorted(documents_by_ward, key=ward_sort_key):
        ward_documents = documents_by_ward[ward]
        ward_total = len(ward_documents)
        if ward_total < min_ward_newsletters:
            continue
        name_tokens = name_tokens_by_ward.get(ward, set())
        scored = [
            score_distinctive_term(
                term,
                ward_count,
                ward_total,
                city_counts[term] - ward_count,
                city_total - ward_total,
            )
            for term, ward_count in count_newsletters_per_term(ward_documents).items()
            if term in vocabulary
            and ward_count >= min_term_newsletters_in_ward
            and ward_count / ward_total <= max_ward_share
            and not term_mentions_name(term, name_tokens)
        ]
        ranked = sorted(
            (item for item in scored if item.lift > 1),
            key=lambda item: (-item.score, item.term),
        )
        distinctive[ward] = [asdict(item) for item in ranked[:top_n]]

    return distinctive


def select_latest_complete_month(months: Iterable[str], as_of_month: str) -> str | None:
    """Return the latest month with data that is strictly before as_of_month."""
    complete = [month for month in months if month < as_of_month]
    return max(complete) if complete else None


def compute_rising_terms(
    documents: list[NewsletterTerms],
    vocabulary: set[str],
    latest_month: str,
    baseline_months: int,
    min_latest_newsletters: int,
    min_latest_sources: int,
    top_n: int,
) -> dict[str, Any]:
    """Rank terms by how much their share of newsletters rose in latest_month
    versus the preceding baseline_months.

    A term must appear in at least min_latest_newsletters newsletters from at
    least min_latest_sources different sources in the latest month, so a
    single prolific sender cannot manufacture a trend.
    """
    baseline = [
        shift_month(latest_month, -offset) for offset in range(1, baseline_months + 1)
    ]
    baseline_set = set(baseline)
    latest_documents = [d for d in documents if d.month == latest_month]
    baseline_documents = [d for d in documents if d.month in baseline_set]
    latest_total = len(latest_documents)
    baseline_total = len(baseline_documents)

    result: dict[str, Any] = {
        "latest_month": latest_month,
        "baseline_months": sorted(baseline),
        "latest_newsletters": latest_total,
        "baseline_newsletters": baseline_total,
        "terms": [],
    }
    if not latest_total or not baseline_total:
        return result

    sources_by_term: dict[str, set[int | None]] = defaultdict(set)
    for document in latest_documents:
        for term in document.terms & vocabulary:
            sources_by_term[term].add(document.source_id)

    latest_counts = count_newsletters_per_term(latest_documents)
    baseline_counts = count_newsletters_per_term(baseline_documents)

    candidates = [
        RisingTerm(
            term=term,
            ratio=round(
                smoothed_share(latest_counts[term], latest_total)
                / smoothed_share(baseline_counts[term], baseline_total),
                2,
            ),
            latest_newsletters=latest_counts[term],
            latest_sources=len(term_sources),
            latest_share=round(latest_counts[term] / latest_total, 4),
            baseline_newsletters=baseline_counts[term],
            baseline_share=round(baseline_counts[term] / baseline_total, 4),
        )
        for term, term_sources in sources_by_term.items()
        if latest_counts[term] >= min_latest_newsletters
        and len(term_sources) >= min_latest_sources
    ]
    ranked = sorted(
        (item for item in candidates if item.ratio > 1),
        key=lambda item: (-item.ratio, -item.latest_newsletters, item.term),
    )
    result["terms"] = [asdict(item) for item in ranked[:top_n]]
    return result
