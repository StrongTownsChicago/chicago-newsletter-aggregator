"""Per-ward "at a glance" summaries for the public ward pages.

Each ward is described against its own recent history: how often its office
sent newsletters and which topics they mentioned. The only city context is
ward reach ("24 of 37 wards"), so no alderman is ranked against another.

Distinctive terms stay on the unlisted dashboard: they surface personal names
and filler words that no stoplist reliably removes.
"""

from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from analytics.records import ward_sort_key
from analytics.topic_reach import (
    TopicNewsletter,
    group_sending_wards_by_month,
    group_topic_wards,
    list_months_ending,
)


@dataclass(frozen=True)
class WardGlanceSettings:
    window_months: int
    top_topics: int


def count_recent_months(
    ward_items: list[TopicNewsletter], window: Sequence[str]
) -> list[int | None]:
    """Newsletters per window month; None for months before the ward's first
    newsletter in the archive, which say nothing about how often it sends.
    """
    first_month = min(item.month for item in ward_items)
    counts = Counter(item.month for item in ward_items)
    return [counts[month] if month >= first_month else None for month in window]


def average_per_month(recent_months: Sequence[int | None]) -> float | None:
    """Mean newsletters per month over the months the ward was in the archive."""
    tracked = [count for count in recent_months if count is not None]
    return round(sum(tracked) / len(tracked), 1) if tracked else None


def summarize_ward_topics(
    window_items: list[TopicNewsletter],
    topic_ids: Sequence[str],
    city_topic_wards: Mapping[str, set[str]],
    top_n: int,
) -> list[dict[str, Any]]:
    """The topics mentioned in the most of the ward's readable newsletters.

    city_wards is how many wards mentioned the topic in the latest month.
    """
    counts = Counter(
        topic_id
        for item in window_items
        if item.readable
        for topic_id in item.topic_mentions
    )
    ranked = sorted(
        (topic_id for topic_id in topic_ids if counts[topic_id]),
        key=lambda topic_id: (-counts[topic_id], topic_ids.index(topic_id)),
    )
    return [
        {
            "id": topic_id,
            "newsletters": counts[topic_id],
            "city_wards": len(city_topic_wards.get(topic_id, set())),
        }
        for topic_id in ranked[:top_n]
    ]


def build_ward_glances(
    items: list[TopicNewsletter],
    topic_ids: Sequence[str],
    latest_month: str,
    settings: WardGlanceSettings,
) -> dict[str, Any]:
    """Summarize every ward with at least one newsletter, over the window of
    complete months ending with latest_month.

    Wards without newsletters are left out, so their pages show nothing extra.
    """
    window = list_months_ending(latest_month, settings.window_months)
    window_set = set(window)
    items_by_ward: dict[str, list[TopicNewsletter]] = defaultdict(list)
    for item in items:
        if item.ward is not None:
            items_by_ward[item.ward].append(item)

    latest_items = [item for item in items if item.month == latest_month]
    city_topic_wards = group_topic_wards(latest_items)
    readable_wards_latest = group_sending_wards_by_month(
        latest_items, readable_only=True
    ).get(latest_month, set())

    def summarize(ward: str) -> dict[str, Any]:
        ward_items = items_by_ward[ward]
        window_items = [item for item in ward_items if item.month in window_set]
        recent_months = count_recent_months(ward_items, window)
        return {
            "first_date": min(item.received_date for item in ward_items).isoformat(),
            "last_date": max(item.received_date for item in ward_items).isoformat(),
            "newsletters": len(ward_items),
            "recent_months": recent_months,
            "per_month": average_per_month(recent_months),
            "topic_newsletters": sum(1 for item in window_items if item.readable),
            "topics": summarize_ward_topics(
                window_items, topic_ids, city_topic_wards, settings.top_topics
            ),
        }

    return {
        "latest_month": latest_month,
        "window_months": window,
        "city_readable_wards": len(readable_wards_latest),
        "wards": {
            ward: summarize(ward) for ward in sorted(items_by_ward, key=ward_sort_key)
        },
    }
