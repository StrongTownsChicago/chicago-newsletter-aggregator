"""Shared building blocks for the public ward summaries and monthly reports.

Both count wards, not newsletters, when they describe the city: "24 of 37
wards mentioned it" cannot be inflated by one prolific sender. Topics here are
the keyword lenses of `analytics.lenses`; the public pages call them topics.
"""

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date

from analytics.lenses import Lens
from analytics.records import NewsletterRecord, SourceRecord, month_key, shift_month


@dataclass(frozen=True)
class TopicNewsletter:
    """One newsletter reduced to what the public summaries need."""

    id: str
    ward: str | None
    received_date: date
    subject: str
    # False when too little text was extracted to tell what it mentions.
    readable: bool
    # Separate mentions of each topic the newsletter mentions, by topic id.
    topic_mentions: Mapping[str, int] = field(default_factory=dict)

    @property
    def month(self) -> str:
        return month_key(self.received_date)


def build_topic_newsletters(
    newsletters: Iterable[NewsletterRecord],
    sources_by_id: Mapping[int, SourceRecord],
    unavailable_ids: set[str],
    lens_mentions_by_newsletter: Mapping[str, Mapping[str, int]],
    lenses_by_newsletter: Mapping[str, list[str]],
) -> list[TopicNewsletter]:
    """Combine newsletters with their ward and the topics they mention.

    lens_mentions_by_newsletter holds each newsletter's `TextMatches.lens_mentions`;
    lenses_by_newsletter says which of those reach the mention minimum.
    """

    def ward_for(source_id: int | None) -> str | None:
        source = sources_by_id.get(source_id) if source_id is not None else None
        return source.ward if source else None

    return [
        TopicNewsletter(
            id=newsletter.id,
            ward=ward_for(newsletter.source_id),
            received_date=newsletter.received_date,
            subject=newsletter.subject.strip(),
            readable=newsletter.id not in unavailable_ids,
            topic_mentions={
                lens_id: lens_mentions_by_newsletter[newsletter.id][lens_id]
                for lens_id in lenses_by_newsletter.get(newsletter.id, [])
            },
        )
        for newsletter in newsletters
    ]


def build_topic_labels(topics: Iterable[Lens]) -> dict[str, str]:
    """Map each topic id to its display label, in display order."""
    return {topic.id: topic.label for topic in topics}


def group_sending_wards_by_month(
    items: Iterable[TopicNewsletter], readable_only: bool = False
) -> dict[str, set[str]]:
    """The wards with at least one newsletter (optionally a readable one) each month.

    Readable wards are the denominator for ward reach: a ward whose text could
    not be read could not be counted as mentioning anything.
    """
    wards_by_month: dict[str, set[str]] = defaultdict(set)
    for item in items:
        if item.ward is not None and (item.readable or not readable_only):
            wards_by_month[item.month].add(item.ward)
    return dict(wards_by_month)


def group_topic_wards(items: Iterable[TopicNewsletter]) -> dict[str, set[str]]:
    """The wards with a readable newsletter mentioning each topic, by topic id."""
    wards_by_topic: dict[str, set[str]] = defaultdict(set)
    for item in items:
        if item.ward is not None and item.readable:
            for topic_id in item.topic_mentions:
                wards_by_topic[topic_id].add(item.ward)
    return dict(wards_by_topic)


def select_broad_complete_months(
    items: Iterable[TopicNewsletter], as_of_month: str, min_sending_wards: int
) -> list[str]:
    """Months before as_of_month in which at least min_sending_wards wards sent a
    newsletter, oldest first.

    The month of as_of_month itself is still in progress, so it is never
    included; months with few wards describe the archive's gaps more than the
    city.
    """
    return sorted(
        month
        for month, wards in group_sending_wards_by_month(items).items()
        if month < as_of_month and len(wards) >= min_sending_wards
    )


def list_months_ending(latest_month: str, count: int) -> list[str]:
    """The count months ending with latest_month, oldest first."""
    return [shift_month(latest_month, -offset) for offset in range(count - 1, -1, -1)]
