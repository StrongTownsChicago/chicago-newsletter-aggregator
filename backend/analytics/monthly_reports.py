"""Monthly citywide reports: what Chicago aldermen's newsletters mentioned each month.

Each report describes one complete month with broad coverage (see
`topic_reach.select_broad_complete_months`): which topics the most wards
mentioned, terms more wards used than usual, which wards sent newsletters,
and a few example newsletters per topic. Everything is counted in wards with
explicit denominators, and nothing ranks named aldermen.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from analytics.records import shift_month, ward_sort_key
from analytics.terms import NewsletterTerms, compute_rising_terms
from analytics.topic_reach import (
    TopicNewsletter,
    group_sending_wards_by_month,
    group_topic_wards,
)


@dataclass(frozen=True)
class MonthlyReportSettings:
    examples_per_topic: int
    rising_baseline_months: int
    rising_min_latest_wards: int
    rising_min_ward_gain: int
    rising_top_n: int


def pick_topic_examples(
    items: Iterable[TopicNewsletter], topic_id: str, limit: int
) -> list[TopicNewsletter]:
    """Choose up to limit readable newsletters that mention a topic, one per ward.

    Newsletters that mention the topic most often come first (then the
    earliest), so the examples are ones where the topic is prominent, and each
    comes from a different ward so no single office stands for the city.
    """
    candidates = sorted(
        (
            item
            for item in items
            if item.readable
            and item.ward is not None
            and topic_id in item.topic_mentions
        ),
        key=lambda item: (-item.topic_mentions[topic_id], item.received_date, item.id),
    )
    examples: list[TopicNewsletter] = []
    used_wards: set[str] = set()
    for item in candidates:
        if len(examples) == limit:
            break
        if item.ward not in used_wards:
            examples.append(item)
            used_wards.add(str(item.ward))
    return examples


def describe_example(item: TopicNewsletter) -> dict[str, Any]:
    return {
        "id": item.id,
        "subject": item.subject,
        "ward": item.ward,
        "date": item.received_date.isoformat(),
    }


def summarize_month_topics(
    month_items: list[TopicNewsletter],
    topic_ids: Sequence[str],
    examples_per_topic: int,
) -> list[dict[str, Any]]:
    """Each topic at least one ward mentioned, the most wards first.

    Ties keep topic display order.
    """
    wards_by_topic = group_topic_wards(month_items)
    newsletters_by_topic = {
        topic_id: sum(
            1
            for item in month_items
            if item.readable and topic_id in item.topic_mentions
        )
        for topic_id in topic_ids
    }
    mentioned = [topic_id for topic_id in topic_ids if wards_by_topic.get(topic_id)]
    ranked = sorted(
        mentioned,
        key=lambda topic_id: (
            -len(wards_by_topic[topic_id]),
            -newsletters_by_topic[topic_id],
            topic_ids.index(topic_id),
        ),
    )
    return [
        {
            "id": topic_id,
            "wards": len(wards_by_topic[topic_id]),
            "newsletters": newsletters_by_topic[topic_id],
            "examples": [
                describe_example(item)
                for item in pick_topic_examples(
                    month_items, topic_id, examples_per_topic
                )
            ],
        }
        for topic_id in ranked
    ]


def summarize_rising_terms(
    month: str,
    documents: list[NewsletterTerms],
    vocabulary: set[str],
    broad_months: set[str],
    settings: MonthlyReportSettings,
) -> dict[str, Any] | None:
    """Terms more wards used this month than in a typical recent month, or None
    when any baseline month lacks broad coverage.

    A baseline with few wards would make nearly every common term look new,
    because the wards added since then mention it for the first time.
    """
    baseline = [
        shift_month(month, -offset)
        for offset in range(settings.rising_baseline_months, 0, -1)
    ]
    if not all(baseline_month in broad_months for baseline_month in baseline):
        return None
    rising = compute_rising_terms(
        documents,
        vocabulary,
        latest_month=month,
        baseline_months=settings.rising_baseline_months,
        min_latest_wards=settings.rising_min_latest_wards,
        min_ward_gain=settings.rising_min_ward_gain,
        top_n=settings.rising_top_n,
    )
    return {
        "baseline_months": rising["baseline_months"],
        "terms": [
            {
                "term": item["term"],
                "wards": item["latest_wards"],
                "baseline_wards": item["baseline_wards"],
            }
            for item in rising["terms"]
        ],
    }


def build_monthly_report(
    month: str,
    items: list[TopicNewsletter],
    readable_documents: list[NewsletterTerms],
    vocabulary: set[str],
    topic_ids: Sequence[str],
    all_wards: Iterable[str],
    broad_months: set[str],
    settings: MonthlyReportSettings,
) -> dict[str, Any]:
    """Describe one month across the city.

    readable_documents are the term sets of newsletters whose text could be
    read; all_wards lists every ward, so wards without a newsletter in the
    archive that month are named rather than silently left out.
    """
    month_items = [item for item in items if item.month == month]
    sending_wards = group_sending_wards_by_month(month_items).get(month, set())
    readable_wards = group_sending_wards_by_month(month_items, readable_only=True).get(
        month, set()
    )
    return {
        "month": month,
        "newsletters": len(month_items),
        "sending_wards": sorted(sending_wards, key=ward_sort_key),
        "absent_wards": sorted(set(all_wards) - sending_wards, key=ward_sort_key),
        "readable_wards": len(readable_wards),
        "topics": summarize_month_topics(
            month_items, topic_ids, settings.examples_per_topic
        ),
        "rising": summarize_rising_terms(
            month, readable_documents, vocabulary, broad_months, settings
        ),
    }


def build_monthly_reports(
    report_months: Sequence[str],
    items: list[TopicNewsletter],
    readable_documents: list[NewsletterTerms],
    vocabulary: set[str],
    topic_ids: Sequence[str],
    all_wards: Iterable[str],
    settings: MonthlyReportSettings,
) -> list[dict[str, Any]]:
    """Build a report for each of report_months, newest first."""
    wards = sorted(set(all_wards), key=ward_sort_key)
    broad_months = set(report_months)
    return [
        build_monthly_report(
            month,
            items,
            readable_documents,
            vocabulary,
            topic_ids,
            wards,
            broad_months,
            settings,
        )
        for month in sorted(report_months, reverse=True)
    ]
