"""
Migration script to remap newsletter topics from old to new consolidated list.

This script:
1. Fetches all newsletters with topics
2. Remaps topics according to the mapping (some old topics are removed)
3. Deduplicates topics (e.g., budget_transparency + fiscal_sustainability → city_budget)
4. Updates the database
5. Shows detailed statistics

Usage:
    # Dry run (show what would change, don't update)
    uv run python -m cli.migrate_topics --dry-run

    # Actually migrate
    uv run python -m cli.migrate_topics
"""

import argparse
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from typing import Any, cast

from supabase import Client

from cli.logging_setup import configure_cli_logging
from processing.llm_processor import TOPICS as VALID_TOPICS
from shared.db import get_supabase_client

SAMPLE_LIMIT = 50  # changed newsletters listed in the preview
SUBJECT_PREVIEW_CHARS = 50
PROGRESS_INTERVAL = 10  # updates between progress lines

# Mapping from old topics to new topics
# Topics not in this mapping will be REMOVED
TOPIC_MAPPING = {
    # Housing
    "4_flats_legalization": "4_flats_legalization",
    "missing_middle_housing": "missing_middle_housing",
    "adu_coach_house": "accessory_dwelling_units",
    "single_stair_reform": "single_stair_reform",
    # Streets
    "bike_infrastructure": "bike_lanes",
    "street_redesign": "street_redesign",
    # Transit
    "cta_metra_funding": "transit_funding",
    # Budget
    "budget_transparency": "city_budget",
    "fiscal_sustainability": "city_budget",
    "tax_policy": "tax_policy",
    # Governance
    "development_approval": "zoning_or_development_meeting_or_approval",
    "public_hearing": "zoning_or_development_meeting_or_approval",
    "city_charter": "city_charter",
}


def remap_topics(old_topics: list[str]) -> list[str]:
    """
    Remap old topics to new topics and deduplicate.

    Args:
        old_topics: List of old topic strings

    Returns:
        List of new topic strings (deduplicated, sorted)
    """
    new_topics = set()

    for old_topic in old_topics:
        candidate_topic = old_topic

        # apply mapping if exists
        if old_topic in TOPIC_MAPPING:
            candidate_topic = TOPIC_MAPPING[old_topic]

        # only keep if it's a valid system topic
        if candidate_topic in VALID_TOPICS:
            new_topics.add(candidate_topic)

    return sorted(new_topics)


@dataclass(frozen=True)
class TopicChange:
    """One newsletter whose topics the migration changes."""

    newsletter_id: str
    subject_preview: str
    old: list[str]
    new: list[str]


@dataclass
class MigrationPlan:
    """The changes a migration makes and what happened to each old topic."""

    total: int
    changes: list[TopicChange] = field(default_factory=list)
    topics_removed: Counter[str] = field(default_factory=Counter)
    topics_mapped: defaultdict[str, Counter[str]] = field(
        default_factory=lambda: defaultdict(Counter)
    )

    @property
    def unchanged(self) -> int:
        return self.total - len(self.changes)


def record_topic_fates(
    old_topics: list[str], new_topics: list[str], plan: MigrationPlan
) -> None:
    """Count each old topic of a changed newsletter as mapped or removed."""
    for topic in old_topics:
        if topic in TOPIC_MAPPING:
            target_topic = TOPIC_MAPPING[topic]
            # A mapping whose target is not a valid topic removes it.
            if target_topic in new_topics:
                plan.topics_mapped[topic][target_topic] += 1
            else:
                plan.topics_removed[topic] += 1
        elif topic not in new_topics:
            plan.topics_removed[topic] += 1


def plan_migration(newsletters: list[dict[str, Any]]) -> MigrationPlan:
    """Work out each newsletter's new topics without touching the database."""
    plan = MigrationPlan(total=len(newsletters))

    for newsletter in newsletters:
        old_topics = cast(list[str], newsletter["topics"] or [])
        new_topics = remap_topics(old_topics)

        if set(old_topics) == set(new_topics):
            continue

        plan.changes.append(
            TopicChange(
                newsletter_id=newsletter["id"],
                subject_preview=newsletter["subject"][:SUBJECT_PREVIEW_CHARS],
                old=old_topics,
                new=new_topics,
            )
        )
        record_topic_fates(old_topics, new_topics, plan)

    return plan


def fetch_newsletters_with_topics(supabase: Client) -> list[dict[str, Any]]:
    response = (
        supabase.table("newsletters")
        .select("id, subject, topics")
        .not_.is_("topics", None)
        .order("created_at", desc=True)
        .execute()
    )
    return cast(list[dict[str, Any]], response.data)


def print_statistics(plan: MigrationPlan) -> None:
    print("-" * 60)
    print("STATISTICS")
    print("-" * 60)
    print(f"Total newsletters:     {plan.total}")
    print(f"Unchanged:             {plan.unchanged}")
    print(f"To be modified:        {len(plan.changes)}")
    print()

    if plan.topics_removed:
        print("Topics to be REMOVED:")
        for topic, count in sorted(plan.topics_removed.items(), key=lambda x: -x[1]):
            print(f"  - {topic}: {count} newsletters")
        print()

    if plan.topics_mapped:
        print("Topics to be MAPPED:")
        for old_topic, new_topic_counts in sorted(plan.topics_mapped.items()):
            for new_topic, count in sorted(new_topic_counts.items()):
                if old_topic != new_topic:  # Only show if changed
                    print(f"  - {old_topic} → {new_topic}: {count} newsletters")
        print()


def print_sample_changes(changes: list[TopicChange]) -> None:
    if not changes:
        return

    print("-" * 60)
    print(f"SAMPLE CHANGES (first {SAMPLE_LIMIT}):")
    print("-" * 60)
    for change in changes[:SAMPLE_LIMIT]:
        print(f"\nNewsletter: {change.subject_preview}...")
        print(f"  Old: {change.old}")
        print(f"  New: {change.new}")

    if len(changes) > SAMPLE_LIMIT:
        print(f"\n... and {len(changes) - SAMPLE_LIMIT} more")
    print()


def apply_topic_changes(supabase: Client, changes: list[TopicChange]) -> None:
    """Write each change, reporting progress; a failed update does not stop the rest."""
    print("-" * 60)
    print("UPDATING DATABASE")
    print("-" * 60)

    updated_count = 0
    failed_count = 0

    for change in changes:
        try:
            supabase.table("newsletters").update({"topics": change.new}).eq(
                "id", change.newsletter_id
            ).execute()
            updated_count += 1
            if updated_count % PROGRESS_INTERVAL == 0:
                print(f"  Updated {updated_count}/{len(changes)} newsletters...")
        except Exception as e:  # noqa: BLE001  per-newsletter boundary: log and continue
            print(f"  ✗ Failed to update newsletter {change.newsletter_id}: {e}")
            failed_count += 1

    print(f"\n✓ Successfully updated {updated_count} newsletters")
    if failed_count > 0:
        print(f"✗ Failed to update {failed_count} newsletters")


def migrate_topics(dry_run: bool = False) -> None:
    """
    Migrate all newsletter topics from old to new schema.

    Args:
        dry_run: If True, show what would change but don't update database
    """
    supabase = get_supabase_client()

    print("=" * 60)
    print("Topic Migration Script")
    print("=" * 60)

    if dry_run:
        print("DRY RUN MODE - No changes will be made to the database")
        print()

    print("Fetching newsletters with topics...")
    newsletters = fetch_newsletters_with_topics(supabase)

    if not newsletters:
        print("No newsletters with topics found.")
        return

    print(f"Found {len(newsletters)} newsletters with topics\n")

    plan = plan_migration(newsletters)
    print_statistics(plan)
    print_sample_changes(plan.changes)

    if not dry_run and plan.changes:
        apply_topic_changes(supabase, plan.changes)
    elif dry_run:
        print("-" * 60)
        print("DRY RUN COMPLETE")
        print("-" * 60)
        print("Run without --dry-run to actually update the database")

    print("\n" + "=" * 60)
    print("Migration Complete")
    print("=" * 60)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Migrate newsletter topics from old to new schema"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would change without updating database",
    )

    args = parser.parse_args()
    migrate_topics(dry_run=args.dry_run)


if __name__ == "__main__":
    configure_cli_logging()
    main()
