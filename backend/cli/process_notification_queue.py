"""
CLI script for processing notification queue and sending emails.

Usage:
    # Send daily digest emails (defaults to yesterday's batch in Chicago timezone)
    uv run python -m cli.process_notification_queue --daily-digest

    # Process specific batch ID
    uv run python -m cli.process_notification_queue --daily-digest --batch-id 2026-01-21

    # Dry run (don't actually send emails)
    uv run python -m cli.process_notification_queue --daily-digest --dry-run
"""

import argparse
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from cli.logging_setup import configure_cli_logging
from notifications.digest_config import DigestType
from notifications.email_sender import send_digest
from notifications.error_logger import log_notification_error
from notifications.rule_matcher import get_pending_notifications_by_user
from shared.db import get_supabase_client


@dataclass
class DigestConfig:
    """Configuration for digest processing by type."""

    digest_type: DigestType
    notification_type: str  # DB filter value
    delivery_type: str  # History record value
    batch_id_calculator: Callable[[], str]  # Function to calculate default batch_id
    fetch_notifications: Callable[
        [str], dict[str, list[dict[str, Any]]]
    ]  # Fetch function


def _calculate_daily_batch_id() -> str:
    """Calculate default batch ID for daily digests (yesterday in Chicago time)."""
    chicago_tz = ZoneInfo("America/Chicago")
    yesterday = datetime.now(chicago_tz).date() - timedelta(days=1)
    return yesterday.isoformat()


def _calculate_weekly_batch_id() -> str:
    """Calculate default batch ID for weekly digests (previous week)."""
    chicago_tz = ZoneInfo("America/Chicago")
    last_week = datetime.now(chicago_tz) - timedelta(days=7)
    year, week, _ = last_week.isocalendar()
    return f"{year}-W{week:02d}"


def _fetch_daily_notifications(batch_id: str) -> dict[str, list[dict[str, Any]]]:
    """Fetch pending daily notifications grouped by user."""
    return get_pending_notifications_by_user(batch_id)


def _fetch_weekly_notifications(batch_id: str) -> dict[str, list[dict[str, Any]]]:
    """Fetch pending weekly notifications grouped by user."""
    supabase = get_supabase_client()

    try:
        response = (
            supabase.table("notification_queue")
            .select(
                "id, user_id, report_id, rule_id, "
                "report:weekly_topic_reports(id, topic, week_id, report_summary, newsletter_ids), "
                "rule:notification_rules(name)"
            )
            .eq("status", "pending")
            .eq("notification_type", "weekly")
            .eq("digest_batch_id", batch_id)
            .execute()
        )

        # Group by user
        notifications_by_user: dict[str, list[dict[str, Any]]] = {}
        for notif in response.data:
            notif_dict = dict(notif)  # type: ignore[arg-type]
            user_id = str(notif_dict["user_id"])
            if user_id not in notifications_by_user:
                notifications_by_user[user_id] = []
            notifications_by_user[user_id].append(notif_dict)

        return notifications_by_user

    except Exception as e:  # noqa: BLE001  database boundary: log and return no notifications
        print(f"Error fetching weekly notifications: {e}")
        return {}


# Digest type configurations
DIGEST_CONFIGS = {
    DigestType.DAILY: DigestConfig(
        digest_type=DigestType.DAILY,
        notification_type="daily",
        delivery_type="daily_digest",
        batch_id_calculator=_calculate_daily_batch_id,
        fetch_notifications=_fetch_daily_notifications,
    ),
    DigestType.WEEKLY: DigestConfig(
        digest_type=DigestType.WEEKLY,
        notification_type="weekly",
        delivery_type="weekly_digest",
        batch_id_calculator=_calculate_weekly_batch_id,
        fetch_notifications=_fetch_weekly_notifications,
    ),
}


def process_digests(
    digest_type: DigestType, batch_id: str | None = None, dry_run: bool = False
) -> dict[str, int]:
    """
    Send the queued daily or weekly digests for one batch.

    batch_id is YYYY-MM-DD for daily (default: yesterday, Chicago time) and
    YYYY-WXX for weekly (default: previous week). dry_run sends no email.
    Returns sent, failed and skipped counts.
    """
    # Get configuration for this digest type
    config = DIGEST_CONFIGS[digest_type]

    # Calculate default batch_id if not provided
    if not batch_id:
        batch_id = config.batch_id_calculator()

    print(f"Processing {_digest_name(digest_type)} digest for batch: {batch_id}")

    # Fetch pending notifications grouped by user (type-specific)
    notifications_by_user = config.fetch_notifications(batch_id)

    if not notifications_by_user:
        print("No pending notifications to process.")
        return {"sent": 0, "failed": 0, "skipped": 0}

    print(f"Found notifications for {len(notifications_by_user)} users")

    run = _DigestRun(get_supabase_client(), config, batch_id, dry_run)

    for user_id, notifications in notifications_by_user.items():
        print(f"\nProcessing user {user_id} ({len(notifications)} notifications)...")
        if _process_user_digest(run, user_id, notifications):
            # Rate limiting: max 10 emails/second
            time.sleep(0.1)

    _print_summary(run)
    return run.stats


@dataclass
class _DigestRun:
    """One batch being sent: what each user's step needs, and the running stats."""

    supabase: Any
    config: DigestConfig
    batch_id: str
    dry_run: bool
    stats: dict[str, int] = field(
        default_factory=lambda: {"sent": 0, "failed": 0, "skipped": 0}
    )

    @property
    def digest_name(self) -> str:
        return _digest_name(self.config.digest_type)


def _digest_name(digest_type: DigestType) -> str:
    return "daily" if digest_type == DigestType.DAILY else "weekly"


def _process_user_digest(
    run: _DigestRun, user_id: str, notifications: list[dict[str, Any]]
) -> bool:
    """Send one user's digest and record the outcome. False when the user is skipped unsent."""
    user_response = (
        run.supabase.table("user_profiles")
        .select("email, notification_preferences")
        .eq("id", user_id)
        .single()
        .execute()
    )

    if not user_response.data:
        print("  ⚠️  User profile not found, skipping")
        run.stats["skipped"] += 1
        return False

    user_data = cast(dict[str, Any], user_response.data)
    user_email = cast(str, user_data["email"])
    preferences = cast(dict[str, Any], user_data.get("notification_preferences", {}))

    # Double-check notifications are enabled (should be filtered already, but be safe)
    if not preferences.get("enabled", True):
        print("  ⚠️  Notifications disabled for user, skipping")
        run.stats["skipped"] += 1
        if not run.dry_run:
            _mark_notifications_failed(
                run.supabase, notifications, "User notifications disabled"
            )
        return False

    if run.dry_run:
        print(f"  [DRY RUN] Would send {run.digest_name} digest to {user_email}")
        run.stats["sent"] += 1
    else:
        result = send_digest(user_id, user_email, notifications, run.config.digest_type)
        _record_send_result(run, user_id, notifications, result)
    return True


def _record_send_result(
    run: _DigestRun,
    user_id: str,
    notifications: list[dict[str, Any]],
    result: dict[str, Any],
) -> None:
    """Update the queue and history for a sent, empty or failed digest."""
    if result["success"]:
        print(f"  ✓ Sent digest to user {user_id}")
        run.stats["sent"] += 1

        # Update notification queue status
        notification_ids = [n["id"] for n in notifications]
        run.supabase.table("notification_queue").update(
            {"status": "sent", "sent_at": "now()"}
        ).in_("id", notification_ids).execute()

        _record_history(
            run,
            user_id,
            notifications,
            {"success": True, "resend_email_id": result.get("email_id")},
        )

    elif result.get("error") == "Empty digest content":
        print(f"  ⚠ Skipped user {user_id}: Empty digest content")
        run.stats["skipped"] += 1

        # Update notification queue with skip reason
        _mark_notifications_failed(run.supabase, notifications, result["error"])

        # Record skip in history (as failure, but with specific reason)
        _record_history(
            run,
            user_id,
            notifications,
            {"success": False, "error_message": result["error"]},
        )

    else:
        error_msg = cast(str, result.get("error", "Unknown error"))
        print(f"  ✗ Failed to send to user {user_id}: {error_msg}")
        run.stats["failed"] += 1

        error_file = log_notification_error(
            error_type="sending",
            error_message=error_msg,
            context={
                "user_id": user_id,
                "batch_id": run.batch_id,
                "notification_count": len(notifications),
                "content_ids": _extract_content_ids(notifications),
            },
        )
        print(f"    Error details logged to: {error_file}")

        _mark_notifications_failed(run.supabase, notifications, error_msg)
        _record_history(
            run, user_id, notifications, {"success": False, "error_message": error_msg}
        )


def _record_history(
    run: _DigestRun,
    user_id: str,
    notifications: list[dict[str, Any]],
    outcome: dict[str, Any],
) -> None:
    """Insert a notification_history row; `outcome` holds success and its detail."""
    run.supabase.table("notification_history").insert(
        {
            "user_id": user_id,
            # Stores both newsletter and report IDs
            "newsletter_ids": _extract_content_ids(notifications),
            "rule_ids": list({n["rule_id"] for n in notifications}),
            "digest_batch_id": run.batch_id,
            "delivery_type": run.config.delivery_type,
            **outcome,
        }
    ).execute()


def _print_summary(run: _DigestRun) -> None:
    print(f"\n{'=' * 60}")
    print(f"{run.digest_name.title()} Digest Processing Complete")
    print(f"{'=' * 60}")
    print(f"Batch ID: {run.batch_id}")
    print(f"Sent:     {run.stats['sent']}")
    print(f"Failed:   {run.stats['failed']}")
    print(f"Skipped:  {run.stats['skipped']}")
    print(f"Total:    {sum(run.stats.values())}")


def process_daily_digests(
    batch_id: str | None = None, dry_run: bool = False
) -> dict[str, int]:
    """
    Send daily digests via process_digests().

    batch_id is YYYY-MM-DD, defaulting to yesterday (Chicago time).
    """
    return process_digests(DigestType.DAILY, batch_id, dry_run)


def _extract_content_ids(notifications: list[dict[str, Any]]) -> list[str]:
    """
    Return the unique content IDs of notifications, in no particular order.

    Weekly notifications contribute their report_id, daily ones their newsletter_id.
    """
    content_ids = []
    for n in notifications:
        # Weekly notifications have report_id, daily have newsletter_id
        if "report_id" in n and n["report_id"] is not None:
            content_ids.append(n["report_id"])
        elif "newsletter_id" in n and n["newsletter_id"] is not None:
            content_ids.append(n["newsletter_id"])
    return list(set(content_ids))


def _mark_notifications_failed(
    supabase: Any, notifications: list[dict[str, Any]], error_message: str
) -> None:
    """Mark notifications as failed with a specific reason."""
    notification_ids = [n["id"] for n in notifications]
    supabase.table("notification_queue").update(
        {"status": "failed", "error_message": error_message}
    ).in_("id", notification_ids).execute()


def process_weekly_digests(
    batch_id: str | None = None, dry_run: bool = False
) -> dict[str, int]:
    """
    Send weekly digests via process_digests().

    batch_id is YYYY-WXX, defaulting to the previous week.
    """
    return process_digests(DigestType.WEEKLY, batch_id, dry_run)


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Process notification queue and send emails"
    )

    parser.add_argument(
        "--daily-digest", action="store_true", help="Send daily digest emails"
    )

    parser.add_argument(
        "--weekly-digest", action="store_true", help="Send weekly digest emails"
    )

    parser.add_argument(
        "--batch-id",
        type=str,
        help="Specific batch ID to process (YYYY-MM-DD for daily, YYYY-WXX for weekly)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (don't actually send emails)",
    )

    args = parser.parse_args()

    if not args.daily_digest and not args.weekly_digest:
        parser.error("Must specify --daily-digest or --weekly-digest")

    if args.daily_digest:
        process_daily_digests(batch_id=args.batch_id, dry_run=args.dry_run)
    elif args.weekly_digest:
        process_weekly_digests(batch_id=args.batch_id, dry_run=args.dry_run)


if __name__ == "__main__":
    configure_cli_logging()
    main()
