"""
Weekly topic report generation orchestration.

CLI script to generate weekly reports for topics with active subscribers.
Designed to run weekly (e.g., Monday morning) via cron or GitHub Actions.

Usage:
    # Generate reports for previous week (default)
    uv run python -m utils.process_weekly_reports

    # Generate for specific week
    uv run python -m utils.process_weekly_reports --week-id 2026-W05

    # Dry run (generate but don't store)
    uv run python -m utils.process_weekly_reports --dry-run

    # Force regenerate even if reports exist
    uv run python -m utils.process_weekly_reports --force
"""

import argparse
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from models.weekly_report import WeeklyTopicReport
from notifications.error_logger import log_notification_error
from processing.weekly_report_generator import generate_weekly_topic_report
from shared.db import get_supabase_client


def get_iso_week_id(date: datetime | None = None) -> str:
    """
    Get ISO week ID in format YYYY-WXX.

    Args:
        date: Date to get week for (defaults to current date in Chicago timezone)

    Returns:
        Week ID string (e.g., "2026-W05")
    """
    if date is None:
        date = datetime.now(ZoneInfo("America/Chicago"))
    year, week, _ = date.isocalendar()
    return f"{year}-W{week:02d}"


def get_previous_week_id() -> str:
    """
    Get ISO week ID for the previous week.

    Returns:
        Week ID string for last week (e.g., "2026-W04")
    """
    chicago_tz = ZoneInfo("America/Chicago")
    last_week = datetime.now(chicago_tz) - timedelta(days=7)
    return get_iso_week_id(last_week)


def get_active_weekly_topics() -> list[str]:
    """
    Query notification_rules to find topics with active weekly subscribers.

    Returns:
        List of unique topic strings that have at least one active weekly rule
    """
    supabase = get_supabase_client()

    try:
        # Query notification rules for active weekly rules
        response = (
            supabase.table("notification_rules")
            .select("topics")
            .eq("is_active", True)
            .eq("delivery_frequency", "weekly")
            .execute()
        )

        # Extract and deduplicate topics
        all_topics: set[str] = set()
        for rule in response.data:
            topics_list = rule.get("topics", [])  # type: ignore
            if isinstance(topics_list, list):
                all_topics.update(topics_list)

        return sorted(list(all_topics))

    except Exception as e:
        print(f"⚠ Error querying active topics: {e}")
        return []


def report_exists(topic: str, week_id: str) -> bool:
    """
    Check if a report already exists for topic/week.

    Args:
        topic: Topic identifier
        week_id: Week identifier (YYYY-WXX)

    Returns:
        True if report exists, False otherwise
    """
    supabase = get_supabase_client()

    try:
        response = (
            supabase.table("weekly_topic_reports")
            .select("id")
            .eq("topic", topic)
            .eq("week_id", week_id)
            .limit(1)
            .execute()
        )

        return len(response.data) > 0

    except Exception:
        return False


def store_weekly_report(report: WeeklyTopicReport) -> bool:
    """
    Store generated report in weekly_topic_reports table.

    Uses ON CONFLICT to handle duplicate week/topic (idempotent).

    Args:
        report: WeeklyTopicReport object to store

    Returns:
        True if stored successfully, False otherwise
    """
    supabase = get_supabase_client()

    try:
        # Convert Pydantic model to dict for insertion
        report_data = {
            "topic": report.topic,
            "week_id": report.week_id,
            "report_summary": report.report_summary,
            "newsletter_ids": report.newsletter_ids,
            "key_developments": (
                [dev.model_dump() for dev in report.key_developments]
                if report.key_developments
                else None
            ),
        }

        # Upsert (insert or update on conflict)
        response = (
            supabase.table("weekly_topic_reports")
            .upsert(
                report_data,
                on_conflict="topic,week_id",  # Use unique constraint
            )
            .execute()
        )

        return len(response.data) > 0

    except Exception as e:
        print(f"  ✗ Failed to store report: {e}")
        return False


def process_weekly_reports(
    week_id: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    model: str = "gpt-oss:20b",
) -> dict[str, int]:
    """
    Main orchestration: Generate reports for all active topics.

    Workflow:
    1. Calculate week_id (defaults to previous week)
    2. Query active weekly topics from notification_rules
    3. For each topic:
       a. Check if report already exists (skip if yes, unless force=True)
       b. Generate report via generate_weekly_topic_report()
       c. Store in database via store_weekly_report() (unless dry_run=True)
    4. Return stats (generated, skipped, failed)

    Args:
        week_id: Week identifier (YYYY-WXX), defaults to previous week
        dry_run: If True, generate but don't store
        force: If True, regenerate even if report exists
        model: Ollama model name

    Returns:
        Dictionary with stats: {generated, skipped, failed}
    """
    # Determine week to process
    if week_id is None:
        week_id = get_previous_week_id()

    print(f"\n{'=' * 60}")
    print(f"Weekly Report Generation - Week {week_id}")
    print(f"{'=' * 60}")
    print(f"Mode: {'DRY RUN' if dry_run else 'PRODUCTION'}")
    print(f"Force: {'Yes' if force else 'No'}")
    print(f"Model: {model}")
    print()

    # Get topics with active weekly subscribers
    print("→ Querying active weekly topics...")
    active_topics = get_active_weekly_topics()

    if not active_topics:
        print("ℹ No active weekly topics found (no users have weekly rules)")
        return {"generated": 0, "skipped": 0, "failed": 0}

    print(f"✓ Found {len(active_topics)} active topics:")
    for topic in active_topics:
        print(f"  - {topic}")
    print()

    # Process each topic
    stats = {"generated": 0, "skipped": 0, "failed": 0}

    for i, topic in enumerate(active_topics, 1):
        print(f"[{i}/{len(active_topics)}] Processing: {topic}")

        # Check if report already exists
        if not force and report_exists(topic, week_id):
            print(f"  ℹ Report already exists for {topic} / {week_id}, skipping")
            stats["skipped"] += 1
            print()
            continue

        # Generate report
        try:
            report = generate_weekly_topic_report(topic, week_id, model)

            if report is None:
                print("  ℹ No report generated (no newsletters or no content)")
                stats["skipped"] += 1
                print()
                continue

            # Store report (unless dry run)
            if dry_run:
                print("  ✓ Report generated (dry run - not storing)")
                stats["generated"] += 1
            else:
                success = store_weekly_report(report)
                if success:
                    print("  ✓ Report stored successfully")
                    stats["generated"] += 1
                else:
                    print("  ✗ Failed to store report")
                    stats["failed"] += 1

        except Exception as e:
            print(f"  ✗ Error generating report: {e}")
            error_file = log_notification_error(
                error_type="weekly_report_generation",
                error_message=str(e),
                context={"week_id": week_id, "topic": topic},
            )
            print(f"  ⚠ Error logged to: {error_file}")
            stats["failed"] += 1

        print()

    # Summary
    print(f"{'=' * 60}")
    print("Summary:")
    print(f"  Generated: {stats['generated']}")
    print(f"  Skipped:   {stats['skipped']}")
    print(f"  Failed:    {stats['failed']}")
    print(f"{'=' * 60}")

    return stats


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate weekly topic reports for active subscribers"
    )

    parser.add_argument(
        "--week-id",
        type=str,
        help="Week ID to process (YYYY-WXX format). Defaults to previous week.",
    )

    parser.add_argument(
        "--dry-run", action="store_true", help="Generate but don't store reports"
    )

    parser.add_argument(
        "--force",
        action="store_true",
        help="Regenerate even if reports already exist for week",
    )

    parser.add_argument(
        "--model",
        type=str,
        default="gpt-oss:20b",
        help="Ollama model to use (default: gpt-oss:20b)",
    )

    args = parser.parse_args()

    stats = process_weekly_reports(
        week_id=args.week_id, dry_run=args.dry_run, force=args.force, model=args.model
    )

    # Exit with non-zero if any failures
    if stats["failed"] > 0:
        exit(1)


if __name__ == "__main__":
    main()
