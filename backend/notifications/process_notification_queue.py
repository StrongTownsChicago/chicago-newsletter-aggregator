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
from typing import Any, cast
from shared.db import get_supabase_client
from notifications.rule_matcher import get_pending_notifications_by_user
from notifications.email_sender import send_daily_digest
from notifications.error_logger import log_notification_error


def process_daily_digests(
    batch_id: str | None = None, dry_run: bool = False
) -> dict[str, int]:
    """
    Process daily digest notifications.

    Groups all pending notifications by user and sends ONE email per user
    with all matched newsletters from the specified batch (default: yesterday in Chicago timezone).

    Args:
        batch_id: Digest batch ID (YYYY-MM-DD format). Defaults to yesterday (Chicago time).
        dry_run: If True, don't actually send emails (for testing)

    Returns:
        Dictionary with stats: sent, failed, skipped
    """
    # Default to yesterday (Chicago timezone) if no batch ID specified
    # Workflow runs at 13:35 UTC (~7:35-8:35am Central) sending previous day's batch
    if not batch_id:
        chicago_tz = ZoneInfo("America/Chicago")
        yesterday = datetime.now(chicago_tz).date() - timedelta(days=1)
        batch_id = yesterday.isoformat()

    print(f"Processing daily digest for batch: {batch_id}")

    # Get pending notifications grouped by user
    notifications_by_user = get_pending_notifications_by_user(batch_id)

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

        # Send digest email
        if dry_run:
            print(f"  [DRY RUN] Would send digest to user {user_id}")
            stats["sent"] += 1
        else:
            result = send_daily_digest(user_id, user_email, notifications)

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
                        "delivery_type": "daily_digest",
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
                        "delivery_type": "daily_digest",
                        "success": False,
                        "error_message": error_msg,
                    }
                ).execute()

        # Rate limiting: max 10 emails/second
        time.sleep(0.1)

    # Print summary
    print(f"\n{'=' * 60}")
    print("Daily Digest Processing Complete")
    print(f"{'=' * 60}")
    print(f"Batch ID: {batch_id}")
    print(f"Sent:     {stats['sent']}")
    print(f"Failed:   {stats['failed']}")
    print(f"Skipped:  {stats['skipped']}")
    print(f"Total:    {sum(stats.values())}")

    return stats


def _mark_notifications_skipped(
    supabase: Any, notifications: list[dict[str, Any]]
) -> None:
    """Mark notifications as failed (user has notifications disabled)."""
    notification_ids = [n["id"] for n in notifications]
    supabase.table("notification_queue").update(
        {"status": "failed", "error_message": "User notifications disabled"}
    ).in_("id", notification_ids).execute()


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Process notification queue and send emails"
    )

    parser.add_argument(
        "--daily-digest", action="store_true", help="Send daily digest emails"
    )

    parser.add_argument(
        "--batch-id",
        type=str,
        help="Specific batch ID to process (YYYY-MM-DD format, defaults to yesterday in Chicago timezone)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run mode (don't actually send emails)",
    )

    args = parser.parse_args()

    if not args.daily_digest:
        parser.error("Must specify --daily-digest")

    if args.daily_digest:
        process_daily_digests(batch_id=args.batch_id, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
