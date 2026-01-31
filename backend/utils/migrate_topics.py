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
    uv run python -m processing.migrate_topics --dry-run

    # Actually migrate
    uv run python -m processing.migrate_topics
"""

import argparse
from typing import Any, cast
from collections import defaultdict
from shared.db import get_supabase_client
from processing.llm_processor import TOPICS as VALID_TOPICS


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

    return sorted(list(new_topics))


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

    # Fetch all newsletters with topics
    print("Fetching newsletters with topics...")
    response = (
        supabase.table("newsletters")
        .select("id, subject, topics")
        .not_.is_("topics", None)
        .order("created_at", desc=True)
        .execute()
    )

    if not response.data:
        print("No newsletters with topics found.")
        return

    newsletters = cast(list[dict[str, Any]], response.data)
    print(f"Found {len(newsletters)} newsletters with topics\n")

    # Statistics tracking
    stats: dict[str, Any] = {
        "total": len(newsletters),
        "unchanged": 0,
        "modified": 0,
        "topics_removed": defaultdict(int),
        "topics_mapped": defaultdict(lambda: defaultdict(int)),
    }

    # Process each newsletter
    modified_newsletters: list[dict[str, Any]] = []

    for newsletter in newsletters:
        old_topics = cast(list[str], newsletter["topics"] or [])
        new_topics = remap_topics(old_topics)

        # Track changes
        if set(old_topics) == set(new_topics):
            stats["unchanged"] += 1
        else:
            stats["modified"] += 1
            modified_newsletters.append(
                {
                    "id": newsletter["id"],
                    "subject": newsletter["subject"][:50],
                    "old": old_topics,
                    "new": new_topics,
                }
            )

            # Track detailed stats on what happened to each old topic
            for topic in old_topics:
                # Case 1: Topic was mapped to something else
                if topic in TOPIC_MAPPING:
                    target_topic = TOPIC_MAPPING[topic]
                    # did the mapping succeed? (i.e. is the target valid?)
                    if target_topic in new_topics:
                        stats["topics_mapped"][topic][target_topic] += 1
                    else:
                        # Mapped to a topic that isn't valid, so effectively removed
                        stats["topics_removed"][topic] += 1

                # Case 2: Topic was NOT mapped
                else:
                    # If it's not in the new list, it was removed (filtered out)
                    if topic not in new_topics:
                        stats["topics_removed"][topic] += 1

    # Show statistics
    print("-" * 60)
    print("STATISTICS")
    print("-" * 60)
    print(f"Total newsletters:     {stats['total']}")
    print(f"Unchanged:             {stats['unchanged']}")
    print(f"To be modified:        {stats['modified']}")
    print()

    if stats["topics_removed"]:
        print("Topics to be REMOVED:")
        for topic, count in sorted(
            stats["topics_removed"].items(), key=lambda x: -x[1]
        ):
            print(f"  - {topic}: {count} newsletters")
        print()

    if stats["topics_mapped"]:
        print("Topics to be MAPPED:")
        for old_topic, new_topics_dict in sorted(stats["topics_mapped"].items()):
            for new_topic, count in sorted(new_topics_dict.items()):
                if old_topic != new_topic:  # Only show if changed
                    print(f"  - {old_topic} → {new_topic}: {count} newsletters")
        print()

    # Show sample of changes
    if modified_newsletters:
        print("-" * 60)
        print("SAMPLE CHANGES (first 50):")
        print("-" * 60)
        for item in modified_newsletters[:50]:
            print(f"\nNewsletter: {item['subject']}...")
            print(f"  Old: {item['old']}")
            print(f"  New: {item['new']}")

        if len(modified_newsletters) > 50:
            print(f"\n... and {len(modified_newsletters) - 50} more")
        print()

    # Update database if not dry run
    if not dry_run and stats["modified"] > 0:
        print("-" * 60)
        print("UPDATING DATABASE")
        print("-" * 60)

        updated_count = 0
        failed_count = 0

        for newsletter in newsletters:
            old_topics = cast(list[str], newsletter["topics"] or [])
            new_topics = remap_topics(old_topics)

            if set(old_topics) != set(new_topics):
                try:
                    supabase.table("newsletters").update({"topics": new_topics}).eq(
                        "id", newsletter["id"]
                    ).execute()
                    updated_count += 1
                    if updated_count % 10 == 0:
                        print(
                            f"  Updated {updated_count}/{stats['modified']} newsletters..."
                        )
                except Exception as e:
                    print(f"  ✗ Failed to update newsletter {newsletter['id']}: {e}")
                    failed_count += 1

        print(f"\n✓ Successfully updated {updated_count} newsletters")
        if failed_count > 0:
            print(f"✗ Failed to update {failed_count} newsletters")

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
    main()
