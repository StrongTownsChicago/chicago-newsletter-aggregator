"""Monthly citywide reports: what Chicago aldermen's newsletters mentioned each month.

Each report describes one complete month with broad coverage (see
`topic_reach.select_broad_complete_months`): which topics the most wards
mentioned, with example newsletters, and which wards sent newsletters.
Everything is counted in wards with explicit denominators; nothing ranks
aldermen. Rising terms stay on the unlisted dashboard: too many are filler
words or personal names for a public page.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Any

from analytics.records import ward_sort_key
from analytics.topic_reach import (
    TopicNewsletter,
    group_sending_wards_by_month,
    group_topic_wards,
)


@dataclass(frozen=True)
class MonthlyReportSettings:
    examples_per_topic: int


def pick_topic_examples(
    items: Iterable[TopicNewsletter],
    topic_id: str,
    limit: int,
    shown_ids: frozenset[str] = frozenset(),
) -> list[TopicNewsletter]:
    """Choose up to limit readable newsletters that mention a topic, one per ward.

    Newsletters not already shown for another topic come first, so one long
    roundup does not stand in for every topic; then the most mentions of the
    topic, then the earliest.
    """
    candidates = sorted(
        (
            item
            for item in items
            if item.readable
            and item.ward is not None
            and topic_id in item.topic_mentions
        ),
        key=lambda item: (
            item.id in shown_ids,
            -item.topic_mentions[topic_id],
            item.received_date,
            item.id,
        ),
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
    summaries: list[dict[str, Any]] = []
    shown_ids: set[str] = set()
    for topic_id in ranked:
        examples = pick_topic_examples(
            month_items, topic_id, examples_per_topic, frozenset(shown_ids)
        )
        shown_ids.update(example.id for example in examples)
        summaries.append(
            {
                "id": topic_id,
                "wards": len(wards_by_topic[topic_id]),
                "newsletters": newsletters_by_topic[topic_id],
                "examples": [describe_example(example) for example in examples],
            }
        )
    return summaries


def build_monthly_report(
    month: str,
    items: list[TopicNewsletter],
    topic_ids: Sequence[str],
    settings: MonthlyReportSettings,
) -> dict[str, Any]:
    """Describe one month across the city."""
    month_items = [item for item in items if item.month == month]
    sending_wards = group_sending_wards_by_month(month_items).get(month, set())
    readable_wards = group_sending_wards_by_month(month_items, readable_only=True).get(
        month, set()
    )
    return {
        "month": month,
        "newsletters": len(month_items),
        "sending_wards": sorted(sending_wards, key=ward_sort_key),
        "readable_wards": len(readable_wards),
        "topics": summarize_month_topics(
            month_items, topic_ids, settings.examples_per_topic
        ),
    }


def build_monthly_reports(
    report_months: Sequence[str],
    items: list[TopicNewsletter],
    topic_ids: Sequence[str],
    settings: MonthlyReportSettings,
) -> list[dict[str, Any]]:
    """Build a report for each of report_months, newest first."""
    return [
        build_monthly_report(month, items, topic_ids, settings)
        for month in sorted(report_months, reverse=True)
    ]
