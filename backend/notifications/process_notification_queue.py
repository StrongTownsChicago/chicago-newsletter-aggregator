"""
CLI script for processing notification queue and sending emails.

Usage:
    # Send daily digest emails (defaults to yesterday's batch in Chicago timezone)
    uv run python -m notifications.process_notification_queue --daily-digest

    # Process specific batch ID
    uv run python -m notifications.process_notification_queue --daily-digest --batch-id 2026-01-21

    # Dry run (don't actually send emails)
    uv run python -m notifications.process_notification_queue --daily-digest --dry-run
"""

import argparse
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any, cast, Callable
from dataclasses import dataclass
from shared.db import get_supabase_client
from notifications.rule_matcher import get_pending_notifications_by_user
from notifications.email_sender import send_digest, DigestType
from notifications.error_logger import log_notification_error


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
                "id, user_id, newsletter_id, rule_id, "
                "weekly_topic_reports:newsletter_id(id, topic, week_id, report_summary, newsletter_ids), "
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
            notif_dict = dict(notif)  # type: ignore
            user_id = str(notif_dict["user_id"])
            if user_id not in notifications_by_user:
                notifications_by_user[user_id] = []
            notifications_by_user[user_id].append(notif_dict)

        return notifications_by_user

    except Exception as e:
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
    Process digest notifications (daily or weekly).

    Generic digest processor that handles both daily newsletter digests and
    weekly topic report digests using type-specific configuration.

    Args:
        digest_type: Type of digest to process (DigestType.DAILY or DigestType.WEEKLY)
        batch_id: Digest batch ID. Format depends on type:
                  - Daily: YYYY-MM-DD (defaults to yesterday in Chicago time)
                  - Weekly: YYYY-WXX (defaults to previous week)
        dry_run: If True, don't actually send emails (for testing)

    Returns:
        Dictionary with stats: sent, failed, skipped
    """
    # Get configuration for this digest type
    config = DIGEST_CONFIGS[digest_type]

    # Calculate default batch_id if not provided
    if not batch_id:
        batch_id = config.batch_id_calculator()

    digest_name = "daily" if digest_type == DigestType.DAILY else "weekly"
    print(f"Processing {digest_name} digest for batch: {batch_id}")

    # Fetch pending notifications grouped by user (type-specific)
    notifications_by_user = config.fetch_notifications(batch_id)

    if not notifications_by_user:
        print("No pending notifications to process.")
        return {"sent": 0, "failed": 0, "skipped": 0}

    print(f"Found notifications for {len(notifications_by_user)} users")

    supabase = get_supabase_client()
    stats = {"sent": 0, "failed": 0, "skipped": 0}

    # Process each user
    for user_id, notifications in notifications_by_user.items():
        print(f"\nProcessing user {user_id} ({len(notifications)} notifications)...")

        # Get user email
        user_response = (
            supabase.table("user_profiles")
            .select("email, notification_preferences")
            .eq("id", user_id)
            .single()
            .execute()
        )

        if not user_response.data:
            print("  ⚠️  User profile not found, skipping")
            stats["skipped"] += 1
            continue

        user_data = cast(dict[str, Any], user_response.data)
        user_email = cast(str, user_data["email"])
        preferences = cast(
            dict[str, Any], user_data.get("notification_preferences", {})
        )

        # Double-check notifications are enabled (should be filtered already, but be safe)
        if not preferences.get("enabled", True):
            print("  ⚠️  Notifications disabled for user, skipping")
            stats["skipped"] += 1
            _mark_notifications_skipped(supabase, notifications)
            continue

        # Send digest email (type-specific sender)
        if dry_run:
            print(f"  [DRY RUN] Would send {digest_name} digest to {user_email}")
            stats["sent"] += 1
        else:
            result = send_digest(user_id, user_email, notifications, config.digest_type)

            if result["success"]:
                print(f"  ✓ Sent digest to user {user_id}")
                stats["sent"] += 1

                # Update notification queue status
                notification_ids = [n["id"] for n in notifications]
                supabase.table("notification_queue").update(
                    {"status": "sent", "sent_at": "now()"}
                ).in_("id", notification_ids).execute()

                # Record in history
                newsletter_ids = list(set([n["newsletter_id"] for n in notifications]))
                rule_ids = list(set([n["rule_id"] for n in notifications]))

                supabase.table("notification_history").insert(
                    {
                        "user_id": user_id,
                        "newsletter_ids": newsletter_ids,
                        "rule_ids": rule_ids,
                        "digest_batch_id": batch_id,
                        "delivery_type": config.delivery_type,
                        "success": True,
                        "resend_email_id": result.get("email_id"),
                    }
                ).execute()

            else:
                error_msg = cast(str, result.get("error", "Unknown error"))
                print(f"  ✗ Failed to send to user {user_id}: {error_msg}")
                stats["failed"] += 1

                # Log error to file
                error_file = log_notification_error(
                    error_type="sending",
                    error_message=error_msg,
                    context={
                        "user_id": user_id,
                        "batch_id": batch_id,
                        "notification_count": len(notifications),
                        "newsletter_ids": [n["newsletter_id"] for n in notifications],
                    },
                )
                print(f"    Error details logged to: {error_file}")

                # Update notification queue with error
                notification_ids = [n["id"] for n in notifications]
                supabase.table("notification_queue").update(
                    {"status": "failed", "error_message": error_msg}
                ).in_("id", notification_ids).execute()

                # Record failure in history
                newsletter_ids = list(set([n["newsletter_id"] for n in notifications]))
                rule_ids = list(set([n["rule_id"] for n in notifications]))

                supabase.table("notification_history").insert(
                    {
                        "user_id": user_id,
                        "newsletter_ids": newsletter_ids,
                        "rule_ids": rule_ids,
                        "digest_batch_id": batch_id,
                        "delivery_type": config.delivery_type,
                        "success": False,
                        "error_message": error_msg,
                    }
                ).execute()

        # Rate limiting: max 10 emails/second
        time.sleep(0.1)

    # Print summary
    print(f"\n{'=' * 60}")
    print(f"{digest_name.title()} Digest Processing Complete")
    print(f"{'=' * 60}")
    print(f"Batch ID: {batch_id}")
    print(f"Sent:     {stats['sent']}")
    print(f"Failed:   {stats['failed']}")
    print(f"Skipped:  {stats['skipped']}")
    print(f"Total:    {sum(stats.values())}")

    return stats


def process_daily_digests(
    batch_id: str | None = None, dry_run: bool = False
) -> dict[str, int]:
    """
    Process daily digest notifications.

    Wrapper around process_digests() for backward compatibility and CLI convenience.

    Args:
        batch_id: Digest batch ID (YYYY-MM-DD format). Defaults to yesterday (Chicago time).
        dry_run: If True, don't actually send emails (for testing)

    Returns:
        Dictionary with stats: sent, failed, skipped
    """
    return process_digests(DigestType.DAILY, batch_id, dry_run)


def _mark_notifications_skipped(
    supabase: Any, notifications: list[dict[str, Any]]
) -> None:
    """Mark notifications as failed (user has notifications disabled)."""
    notification_ids = [n["id"] for n in notifications]
    supabase.table("notification_queue").update(
        {"status": "failed", "error_message": "User notifications disabled"}
    ).in_("id", notification_ids).execute()


def process_weekly_digests(
    batch_id: str | None = None, dry_run: bool = False
) -> dict[str, int]:
    """
    Process weekly digest notifications.

    Wrapper around process_digests() for backward compatibility and CLI convenience.

    Args:
        batch_id: Week identifier (YYYY-WXX format). Defaults to previous week.
        dry_run: If True, don't actually send emails (for testing)

    Returns:
        Dictionary with stats: sent, failed, skipped
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
    main()
