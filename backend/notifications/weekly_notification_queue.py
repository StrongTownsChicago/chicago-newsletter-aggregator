"""
Weekly notification queuing logic.

Queues notifications for weekly topic reports based on user notification rules.
Designed to run after weekly report generation is complete.

Usage:
    from notifications.weekly_notification_queue import queue_weekly_notifications

    stats = queue_weekly_notifications("2026-W05")
    print(f"Queued {stats['queued']} notifications for {stats['users']} users")
"""

from typing import Any

from shared.db import get_supabase_client


def get_users_with_weekly_rules() -> dict[str, list[dict[str, Any]]]:
    """
    Get all users with active weekly notification rules.

    Returns:
        Dictionary mapping user_id to list of their active weekly rules
        Example: {"user-uuid-1": [{"id": "rule-uuid-1", "topics": ["bike_lanes"], ...}], ...}
    """
    supabase = get_supabase_client()

    try:
        # Query active weekly rules
        response = (
            supabase.table("notification_rules")
            .select("id, user_id, topics")
            .eq("is_active", True)
            .eq("delivery_frequency", "weekly")
            .execute()
        )

        # Group rules by user_id
        users_rules: dict[str, list[dict[str, Any]]] = {}
        for rule in response.data:
            rule_dict = dict(rule)  # type: ignore
            user_id = str(rule_dict["user_id"])
            if user_id not in users_rules:
                users_rules[user_id] = []
            users_rules[user_id].append(rule_dict)

        # Filter out users with notifications disabled
        # Query user_profiles to check notification_preferences
        if users_rules:
            profiles_response = (
                supabase.table("user_profiles")
                .select("id, notification_preferences")
                .in_("id", list(users_rules.keys()))
                .execute()
            )

            # Build set of users with notifications enabled
            enabled_users = set()
            for profile in profiles_response.data:
                profile_dict = dict(profile)  # type: ignore
                prefs = profile_dict.get("notification_preferences", {})
                if isinstance(prefs, dict) and prefs.get("enabled", True):
                    enabled_users.add(str(profile_dict["id"]))

            # Filter to only enabled users
            users_rules = {
                uid: rules for uid, rules in users_rules.items() if uid in enabled_users
            }

        return users_rules

    except Exception as e:
        print(f"⚠ Error querying weekly rules: {e}")
        return {}


def queue_weekly_notifications(week_id: str) -> dict[str, int]:
    """
    Queue weekly notifications based on generated reports and user rules.

    Workflow:
    1. Fetch all active weekly notification rules grouped by user
    2. For each user:
       a. Get their subscribed topics (from rules)
       b. Fetch generated reports for those topics + week
       c. For each matching report, queue notification:
          - user_id, report_id (stored in newsletter_id), rule_id
          - status: pending
          - digest_batch_id: week_id
          - notification_type: weekly
    3. Return stats (queued, skipped, users)

    Args:
        week_id: Week identifier (YYYY-WXX)

    Returns:
        Dictionary with stats: {queued, skipped, users}
    """
    supabase = get_supabase_client()

    print(f"\n{'=' * 60}")
    print(f"Weekly Notification Queuing - Week {week_id}")
    print(f"{'=' * 60}\n")

    # Get users with active weekly rules
    print("→ Querying users with weekly rules...")
    users_rules = get_users_with_weekly_rules()

    if not users_rules:
        print("ℹ No users with active weekly rules found")
        return {"queued": 0, "skipped": 0, "users": 0}

    print(f"✓ Found {len(users_rules)} users with weekly rules\n")

    # Fetch all generated reports for this week
    print(f"→ Fetching generated reports for week {week_id}...")
    try:
        reports_response = (
            supabase.table("weekly_topic_reports")
            .select("id, topic, week_id")
            .eq("week_id", week_id)
            .execute()
        )

        # Build topic -> report_id mapping
        topic_to_report: dict[str, str] = {}
        for report in reports_response.data:
            report_dict = dict(report)  # type: ignore
            topic_to_report[str(report_dict["topic"])] = str(report_dict["id"])

        print(
            f"✓ Found {len(topic_to_report)} reports: {', '.join(topic_to_report.keys())}\n"
        )

    except Exception as e:
        print(f"✗ Error fetching reports: {e}")
        return {"queued": 0, "skipped": 0, "users": 0}

    # Queue notifications for each user
    stats = {"queued": 0, "skipped": 0, "users": 0}

    for user_id, rules in users_rules.items():
        user_queued = 0

        for rule in rules:
            rule_id = str(rule["id"])
            topics = rule.get("topics", [])

            if not isinstance(topics, list):
                continue

            # For each topic in the rule, check if report exists
            for topic in topics:
                if topic not in topic_to_report:
                    # No report for this topic this week
                    stats["skipped"] += 1
                    continue

                report_id = topic_to_report[topic]

                # Queue notification
                try:
                    supabase.table("notification_queue").insert(
                        {
                            "user_id": user_id,
                            "report_id": report_id,  # Store in dedicated report_id column
                            "rule_id": rule_id,
                            "status": "pending",
                            "digest_batch_id": week_id,
                            "notification_type": "weekly",
                        }
                    ).execute()

                    stats["queued"] += 1
                    user_queued += 1

                except Exception:
                    # Likely unique constraint violation (already queued)
                    # This is fine - just skip
                    stats["skipped"] += 1
                    continue

        if user_queued > 0:
            stats["users"] += 1
            print(f"  ✓ Queued {user_queued} notifications for user {user_id[:8]}...")

    # Summary
    print(f"\n{'=' * 60}")
    print("Summary:")
    print(f"  Queued:  {stats['queued']} notifications")
    print(f"  Skipped: {stats['skipped']}")
    print(f"  Users:   {stats['users']}")
    print(f"{'=' * 60}\n")

    return stats


def main() -> None:
    """CLI entry point for testing."""
    import argparse
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo

    parser = argparse.ArgumentParser(
        description="Queue weekly notifications for generated reports"
    )

    parser.add_argument(
        "--week-id",
        type=str,
        help="Week ID to process (YYYY-WXX format). Defaults to previous week.",
    )

    args = parser.parse_args()

    # Default to previous week
    if args.week_id:
        week_id = args.week_id
    else:
        chicago_tz = ZoneInfo("America/Chicago")
        last_week = datetime.now(chicago_tz) - timedelta(days=7)
        year, week, _ = last_week.isocalendar()
        week_id = f"{year}-W{week:02d}"

    stats = queue_weekly_notifications(week_id)

    # Exit with non-zero if no notifications queued
    if stats["queued"] == 0:
        exit(1)


if __name__ == "__main__":
    main()
