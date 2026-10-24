"""
Weekly topic report generation orchestration.

CLI script to generate weekly reports for topics with active subscribers.
Designed to run weekly (e.g., Monday morning) via cron or GitHub Actions.

Usage:
    # Generate reports for previous week (default)
    uv run python -m cli.process_weekly_reports

    # Generate for specific week
    uv run python -m cli.process_weekly_reports --week-id 2026-W05

    # Dry run (generate but don't store)
    uv run python -m cli.process_weekly_reports --dry-run

    # Force regenerate even if reports exist
    uv run python -m cli.process_weekly_reports --force
"""

import argparse
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal
from zoneinfo import ZoneInfo

from dotenv import load_dotenv

from cli.logging_setup import configure_cli_logging
from models.weekly_report import WeeklyTopicReport
from notifications.error_logger import log_notification_error
from processing.weekly_report_generator import generate_weekly_topic_report
from shared.db import get_supabase_client

load_dotenv()

ENABLE_LLM = os.getenv("ENABLE_LLM", "false").lower() == "true"


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
            topics_list = rule.get("topics", [])  # type: ignore[union-attr]
            if isinstance(topics_list, list):
                all_topics.update(topics_list)

        return sorted(all_topics)

    except Exception as e:  # noqa: BLE001  database boundary: log and return no topics
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

    except Exception:  # noqa: BLE001  database boundary: treat a failed lookup as absent
        return False


def store_weekly_report(report: WeeklyTopicReport) -> bool:
    """
    Upsert a report into weekly_topic_reports and return whether it was stored.

    Conflicts on (topic, week_id) update the existing row, so reruns are idempotent.
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

    except Exception as e:  # noqa: BLE001  database boundary: log and report failure
        print(f"  ✗ Failed to store report: {e}")
        return False


ReportOutcome = Literal["generated", "skipped", "failed"]


@dataclass(frozen=True)
class ReportRunOptions:
    """What one weekly report run generates and whether it stores."""

    week_id: str
    dry_run: bool
    force: bool
    model: str


def resolve_week_id(week_id: str | None, current_week: bool) -> str:
    """The week to report on: week_id if given, else the current or previous week."""
    if week_id is not None:
        return week_id
    return get_iso_week_id() if current_week else get_previous_week_id()


def print_run_header(options: ReportRunOptions) -> None:
    print(f"\n{'=' * 60}")
    print(f"Weekly Report Generation - Week {options.week_id}")
    print(f"{'=' * 60}")
    print(f"Mode: {'DRY RUN' if options.dry_run else 'PRODUCTION'}")
    print(f"Force: {'Yes' if options.force else 'No'}")
    print(f"Model: {options.model}")
    print(f"LLM Enabled: {'Yes' if ENABLE_LLM else 'No'}")
    print()


def print_run_summary(stats: dict[str, int]) -> None:
    print(f"{'=' * 60}")
    print("Summary:")
    print(f"  Generated: {stats['generated']}")
    print(f"  Skipped:   {stats['skipped']}")
    print(f"  Failed:    {stats['failed']}")
    print(f"{'=' * 60}")


def store_generated_report(report: WeeklyTopicReport, dry_run: bool) -> ReportOutcome:
    """Store a generated report, or only count it on a dry run."""
    if dry_run:
        print("  ✓ Report generated (dry run - not storing)")
        return "generated"

    if store_weekly_report(report):
        print("  ✓ Report stored successfully")
        return "generated"
    print("  ✗ Failed to store report")
    return "failed"


def generate_topic_report(topic: str, options: ReportRunOptions) -> ReportOutcome:
    """
    Generate one topic's report and store it unless this is a dry run.

    An existing report is skipped unless options.force. A generation error is
    logged to an error file and counted as failed.
    """
    if not options.force and report_exists(topic, options.week_id):
        print(f"  ℹ Report already exists for {topic} / {options.week_id}, skipping")
        return "skipped"

    try:
        report = generate_weekly_topic_report(topic, options.week_id, options.model)

        if report is None:
            print("  ℹ No report generated (no newsletters or no content)")
            return "skipped"

        return store_generated_report(report, options.dry_run)

    except Exception as e:  # noqa: BLE001  per-topic boundary: log and continue
        print(f"  ✗ Error generating report: {e}")
        error_file = log_notification_error(
            error_type="weekly_report_generation",
            error_message=str(e),
            context={"week_id": options.week_id, "topic": topic},
        )
        print(f"  ⚠ Error logged to: {error_file}")
        return "failed"


def process_weekly_reports(
    week_id: str | None = None,
    dry_run: bool = False,
    force: bool = False,
    current_week: bool = False,
    model: str = "gpt-oss:20b",
) -> dict[str, int]:
    """
    Generate and store a weekly report for each topic with active weekly subscribers.

    week_id defaults to the previous week, or the current week if current_week.
    Topics that already have a report are skipped unless force; dry_run generates
    without storing. Returns generated, skipped and failed counts.
    """
    options = ReportRunOptions(
        week_id=resolve_week_id(week_id, current_week),
        dry_run=dry_run,
        force=force,
        model=model,
    )
    print_run_header(options)

    if not ENABLE_LLM:
        print("ℹ ENABLE_LLM is false. Skipping report generation.")
        print("  Existing reports will still be processed by the notification queue.")
        return {"generated": 0, "skipped": 0, "failed": 0}

    print("→ Querying active weekly topics...")
    active_topics = get_active_weekly_topics()

    if not active_topics:
        print("ℹ No active weekly topics found (no users have weekly rules)")
        return {"generated": 0, "skipped": 0, "failed": 0}

    print(f"✓ Found {len(active_topics)} active topics:")
    for topic in active_topics:
        print(f"  - {topic}")
    print()

    stats = {"generated": 0, "skipped": 0, "failed": 0}

    for i, topic in enumerate(active_topics, 1):
        print(f"[{i}/{len(active_topics)}] Processing: {topic}")
        stats[generate_topic_report(topic, options)] += 1
        print()

    print_run_summary(stats)

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
        "--current-week",
        action="store_true",
        help="Use current week instead of previous week (useful for manual Sunday runs)",
    )

    parser.add_argument(
        "--model",
        type=str,
        default=os.getenv("LLM_MODEL", os.getenv("OLLAMA_MODEL", "gpt-oss:20b")),
        help="LLM model to use, with optional provider prefix (e.g., openai:gpt-5, ollama:gpt-oss:20b). Default: from LLM_MODEL or OLLAMA_MODEL env var",
    )

    args = parser.parse_args()

    stats = process_weekly_reports(
        week_id=args.week_id,
        dry_run=args.dry_run,
        force=args.force,
        current_week=args.current_week,
        model=args.model,
    )

    # Exit with non-zero if any failures
    if stats["failed"] > 0:
        exit(1)


if __name__ == "__main__":
    configure_cli_logging()
    main()
