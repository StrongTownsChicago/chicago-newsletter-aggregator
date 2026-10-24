"""
Rule matching logic for notification system.

Matches newsletters against user-defined notification rules and queues
notifications for delivery.
"""

import logging
from datetime import datetime
from typing import Any, cast
from zoneinfo import ZoneInfo

from notifications.error_logger import log_notification_error
from shared.db import get_supabase_client

logger = logging.getLogger(__name__)


def match_newsletter_to_rules(
    newsletter_id: str, newsletter_data: dict[str, Any]
) -> list[dict[str, Any]]:
    """
    Find all notification rules that match a given newsletter.

    `newsletter_data` needs topics, plain_text, source_id and ward_number.
    Each returned rule dict includes user_id, rule_id and rule_name.
    """
    try:
        supabase = get_supabase_client()

        # Fetch all active notification rules with user preferences
        response = (
            supabase.table("notification_rules")
            .select(
                "id, user_id, name, topics, search_term, source_ids, ward_numbers, delivery_frequency"
            )
            .eq("is_active", True)
            .eq("delivery_frequency", "daily")
            .execute()
        )

        if not response.data:
            return []

        active_rules = cast(list[dict[str, Any]], response.data)

        # Also fetch user preferences to check if notifications are enabled
        user_ids = [str(rule["user_id"]) for rule in active_rules]
        users_response = (
            supabase.table("user_profiles")
            .select("id, notification_preferences")
            .in_("id", user_ids)
            .execute()
        )

        # Create lookup for enabled users
        enabled_users: set[str] = set()
        if users_response.data:
            users_data = cast(list[dict[str, Any]], users_response.data)
            for user in users_data:
                prefs = cast(dict[str, Any], user.get("notification_preferences", {}))
                if prefs.get("enabled", True):  # Default to enabled if not set
                    enabled_users.add(str(user["id"]))

        # Filter and match rules
        matched_rules: list[dict[str, Any]] = []
        for rule in active_rules:
            # Skip if user has notifications disabled
            if str(rule["user_id"]) not in enabled_users:
                continue

            # Check if rule matches newsletter
            if _rule_matches_newsletter(rule, newsletter_data):
                matched_rules.append(
                    {
                        "user_id": str(rule["user_id"]),
                        "rule_id": str(rule["id"]),
                        "rule_name": str(rule["name"]),
                    }
                )

        return matched_rules

    except Exception as e:  # noqa: BLE001  matching must not fail ingestion: log to file
        error_file = log_notification_error(
            error_type="matching",
            error_message=str(e),
            context={
                "newsletter_id": newsletter_id,
                "newsletter_topics": newsletter_data.get("topics", []),
                "newsletter_source_id": newsletter_data.get("source_id"),
            },
        )
        logger.warning(
            f"  ⚠️  Error matching newsletter to rules. Details logged to: {error_file}"
        )
        # Return empty list to avoid breaking ingestion
        return []


def _rule_matches_newsletter(
    rule: dict[str, Any], newsletter_data: dict[str, Any]
) -> bool:
    """
    Check if a single rule matches a newsletter.

    All filter conditions are AND-ed together.
    Within each condition type (topics, keywords), matches are OR-ed.
    """
    # Extract newsletter data; both columns are nullable (no LLM topics yet, no text)
    newsletter_topics = set(newsletter_data.get("topics") or [])
    newsletter_text = (newsletter_data.get("plain_text") or "").lower()
    newsletter_ward = newsletter_data.get("ward_number")

    # Topics filter (at least one topic must match)
    rule_topics = rule.get("topics", [])
    if rule_topics and not any(topic in newsletter_topics for topic in rule_topics):
        return False

    # Search Term filter (phrase match)
    search_term = rule.get("search_term")
    # Search term must appear in newsletter text (case-insensitive)
    if search_term and search_term.lower() not in newsletter_text:
        return False

    # Ward filter (newsletter must be from alderman in one of specified wards)
    rule_wards = rule.get("ward_numbers", [])
    if rule_wards and newsletter_ward not in rule_wards:  # noqa: SIM103  one guard per filter
        return False

    # All conditions passed
    return True


def queue_notifications(newsletter_id: str, matched_rules: list[dict[str, Any]]) -> int:
    """
    Queue notifications for matched rules.

    Args:
        newsletter_id: UUID of the newsletter
        matched_rules: List of dicts with user_id, rule_id, rule_name

    Returns:
        Number of notifications successfully queued
    """
    if not matched_rules:
        return 0

    try:
        supabase = get_supabase_client()

        # Generate digest batch ID for daily grouping (YYYY-MM-DD)
        # Use Chicago timezone to ensure evening emails (7pm-10pm) are batched
        # with the same day's newsletters, not the next day in UTC
        chicago_tz = ZoneInfo("America/Chicago")
        today = datetime.now(chicago_tz).date().isoformat()

        # Prepare notifications for batch insert
        notifications = [
            {
                "user_id": match["user_id"],
                "newsletter_id": newsletter_id,
                "rule_id": match["rule_id"],
                "status": "pending",
                "digest_batch_id": today,
            }
            for match in matched_rules
        ]

        # Insert notifications individually to handle duplicates gracefully
        # Unique constraint on (user_id, newsletter_id, rule_id) will prevent duplicates
        queued_count = 0
        failed_notifications = []

        for notification in notifications:
            try:
                supabase.table("notification_queue").insert(notification).execute()
                queued_count += 1
            except Exception as e:  # noqa: BLE001  per-notification boundary: duplicates are expected
                # Track failures that aren't just duplicates
                error_str = str(e)
                if (
                    "duplicate" not in error_str.lower()
                    and "unique" not in error_str.lower()
                ):
                    failed_notifications.append(
                        {"notification": notification, "error": error_str}
                    )
                logger.warning(
                    f"  ⚠ Could not queue notification for user {notification['user_id']}: {e}"
                )

        # Log non-duplicate failures
        if failed_notifications:
            log_notification_error(
                error_type="queuing",
                error_message=f"Failed to queue {len(failed_notifications)} notification(s)",
                context={
                    "newsletter_id": newsletter_id,
                    "failures": failed_notifications,
                },
            )

        return queued_count

    except Exception as e:  # noqa: BLE001  queuing must not fail ingestion: log to file
        error_file = log_notification_error(
            error_type="queuing",
            error_message=str(e),
            context={
                "newsletter_id": newsletter_id,
                "matched_rules_count": len(matched_rules),
            },
        )
        logger.warning(
            f"  ⚠️  Error queuing notifications. Details logged to: {error_file}"
        )
        return 0


def get_pending_notifications_by_user(
    digest_batch_id: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Get all pending notifications grouped by user.

    Args:
        digest_batch_id: Optional batch ID to filter by (YYYY-MM-DD format)
                         If None, gets all pending notifications

    Returns:
        Dictionary mapping user_id to list of notification records
    """
    supabase = get_supabase_client()

    query = (
        supabase.table("notification_queue")
        .select(
            "*, newsletter:newsletters(id, subject, received_date, plain_text, summary, topics, source:sources(name, ward_number)), rule:notification_rules(name)"
        )
        .eq("status", "pending")
        .order("created_at", desc=False)
    )

    if digest_batch_id:
        query = query.eq("digest_batch_id", digest_batch_id)

    response = query.execute()

    if not response.data:
        return {}

    # Group by user_id
    notifications_by_user: dict[str, list[dict[str, Any]]] = {}
    notifications_data = cast(list[dict[str, Any]], response.data)
    for notification in notifications_data:
        user_id = str(notification["user_id"])
        if user_id not in notifications_by_user:
            notifications_by_user[user_id] = []
        notifications_by_user[user_id].append(notification)

    return notifications_by_user
