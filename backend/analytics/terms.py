"""Term-level metrics: the searchable term index, distinctive ward vocabulary,
and rising terms.

Counts are newsletter counts (how many newsletters mention a term at least
once), not raw occurrences, so one long newsletter repeating a word cannot
dominate a metric. Rising terms go one step further and count wards.
"""

import math
import statistics
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from typing import Any

from analytics.plurals import choose_display_forms, fold_plural
from analytics.records import (
    NewsletterRecord,
    SourceRecord,
    month_key,
    shift_month,
    ward_sort_key,
)
from analytics.text import (
    MIN_TOKEN_LENGTH,
    WORD_PATTERN,
    contains_word_run,
    extract_terms,
)

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
    """True if any word of the term is one of the given name words.

    Words are compared with plurals folded: a term is named by its most common
    written form, which may be a plural or singular variant of a name word.
    """
    folded_names = {fold_plural(name) for name in name_tokens}
    return any(fold_plural(word) in folded_names for word in term.split())


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


@dataclass(frozen=True)
class RisingTerm:
    term: str
    latest_wards: int
    baseline_wards: float
    baseline_month_wards: list[int]
    ward_gain: float
    latest_newsletters: int


def group_wards_by_month(documents: Iterable[NewsletterTerms]) -> dict[str, set[str]]:
    """The wards with at least one newsletter in each month (the ward-reach denominator)."""
    wards_by_month: dict[str, set[str]] = defaultdict(set)
    for document in documents:
        if document.ward is not None:
            wards_by_month[document.month].add(document.ward)
    return wards_by_month


def compute_rising_terms(
    documents: list[NewsletterTerms],
    vocabulary: set[str],
    latest_month: str,
    baseline_months: int,
    min_latest_wards: int,
    min_ward_gain: int,
    top_n: int,
) -> dict[str, Any]:
    """Rank terms by how many more wards mentioned them in latest_month than in a
    typical recent month.

    Counting wards rather than pooling newsletters means one prolific sender
    cannot manufacture a trend. The baseline is the median ward count over the
    baseline_months before latest_month, so one unusual month does not set it;
    baseline months with no active ward (before the archive starts) are left
    out of the median rather than counted as zero.
    A term must reach at least min_latest_wards wards and gain at least
    min_ward_gain wards over the baseline. Pass only newsletters whose text
    could be read: the wards active each month are the denominator readers
    compare against, and a ward whose text was unavailable could not mention
    anything.
    """
    baseline = sorted(
        shift_month(latest_month, -offset) for offset in range(1, baseline_months + 1)
    )
    window = {latest_month, *baseline}
    window_documents = [
        document
        for document in documents
        if document.month in window and document.ward is not None
    ]
    active_wards = group_wards_by_month(window_documents)
    result: dict[str, Any] = {
        "latest_month": latest_month,
        "baseline_months": baseline,
        "latest_active_wards": len(active_wards[latest_month]),
        "baseline_active_wards": [len(active_wards[month]) for month in baseline],
        "terms": [],
    }
    observed_baseline = [month for month in baseline if active_wards[month]]
    if not active_wards[latest_month] or not observed_baseline:
        return result

    wards_by_term: dict[str, dict[str, set[str]]] = defaultdict(
        lambda: defaultdict(set)
    )
    latest_newsletters: Counter[str] = Counter()
    for document in window_documents:
        for term in document.terms & vocabulary:
            wards_by_term[term][document.month].add(str(document.ward))
            if document.month == latest_month:
                latest_newsletters[term] += 1

    candidates: list[RisingTerm] = []
    for term, wards_by_month in wards_by_term.items():
        latest_wards = len(wards_by_month[latest_month])
        month_wards = [len(wards_by_month[month]) for month in baseline]
        baseline_wards = float(
            statistics.median(len(wards_by_month[month]) for month in observed_baseline)
        )
        gain = latest_wards - baseline_wards
        if latest_wards >= min_latest_wards and gain >= min_ward_gain:
            candidates.append(
                RisingTerm(
                    term=term,
                    latest_wards=latest_wards,
                    baseline_wards=baseline_wards,
                    baseline_month_wards=month_wards,
                    ward_gain=gain,
                    latest_newsletters=latest_newsletters[term],
                )
            )
    ranked = sorted(
        candidates, key=lambda item: (-item.ward_gain, -item.latest_wards, item.term)
    )
    result["terms"] = [
        asdict(item) for item in drop_overlapping_terms(ranked, lambda i: i.term)
    ][:top_n]
    return result


def are_parts_of_one_phrase(first: list[str], second: list[str]) -> bool:
    """True if one term contains the other ("labor" in "labor day") or the two
    chain into a longer phrase ("labor day" and "day weekend").

    Terms that merely share a word in the same position ("labor day" and
    "election day") are different phrases, so they are not matched.
    """
    return (
        contains_word_run(first, second)
        or contains_word_run(second, first)
        or first[-1] == second[0]
        or second[-1] == first[0]
    )


def drop_overlapping_terms[T](ranked: list[T], term_of: Callable[[T], str]) -> list[T]:
    """Keep each item unless its term is part of the same phrase as a
    higher-ranked kept term (see `are_parts_of_one_phrase`).

    One story shows up as several overlapping terms ("labor day", "labor",
    "day weekend"); keeping only the highest-ranked leaves room for others.
    """
    kept: list[T] = []
    kept_words: list[list[str]] = []
    for item in ranked:
        words = term_of(item).split(" ")
        if not any(are_parts_of_one_phrase(words, other) for other in kept_words):
            kept.append(item)
            kept_words.append(words)
    return kept
