"""
Rule matching logic for notification system.

Matches newsletters against user-defined notification rules and queues
notifications for delivery.
"""

from datetime import date
from typing import Dict, List, Any, Optional
from shared.db import get_supabase_client


def match_newsletter_to_rules(
    newsletter_id: str,
    newsletter_data: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Find all notification rules that match a given newsletter.

    Args:
        newsletter_id: UUID of the newsletter
        newsletter_data: Dictionary containing:
            - topics: List of extracted topics
            - plain_text: Full text content (for keyword matching in Phase 2)
            - source_id: UUID of the source (for source filtering in Phase 2)
            - ward_number: Ward number (for ward filtering in Phase 2)

    Returns:
        List of matching rules (each rule dict includes user_id, rule_id, rule_name)
    """
    supabase = get_supabase_client()

    # Fetch all active notification rules with user preferences
    response = supabase.table('notification_rules') \
        .select('id, user_id, name, topics, keywords, min_relevance_score, source_ids, ward_numbers') \
        .eq('is_active', True) \
        .execute()

    if not response.data:
        return []

    active_rules = response.data

    # Also fetch user preferences to check if notifications are enabled
    user_ids = [rule['user_id'] for rule in active_rules]
    users_response = supabase.table('user_profiles') \
        .select('id, notification_preferences') \
        .in_('id', user_ids) \
        .execute()

    # Create lookup for enabled users
    enabled_users = set()
    if users_response.data:
        for user in users_response.data:
            prefs = user.get('notification_preferences', {})
            if prefs.get('enabled', True):  # Default to enabled if not set
                enabled_users.add(user['id'])

    # Filter and match rules
    matched_rules = []
    for rule in active_rules:
        # Skip if user has notifications disabled
        if rule['user_id'] not in enabled_users:
            continue

        # Check if rule matches newsletter
        if _rule_matches_newsletter(rule, newsletter_data):
            matched_rules.append({
                'user_id': rule['user_id'],
                'rule_id': rule['id'],
                'rule_name': rule['name']
            })

    return matched_rules


def _rule_matches_newsletter(
    rule: Dict[str, Any],
    newsletter_data: Dict[str, Any]
) -> bool:
    """
    Check if a single rule matches a newsletter.

    All filter conditions are AND-ed together.
    Within each condition type (topics, keywords), matches are OR-ed.

    Args:
        rule: Notification rule from database
        newsletter_data: Newsletter data to match against

    Returns:
        True if the rule matches the newsletter
    """
    # Extract newsletter data
    newsletter_topics = set(newsletter_data.get('topics', []))
    newsletter_text = newsletter_data.get('plain_text', '').lower()
    newsletter_source_id = newsletter_data.get('source_id')
    newsletter_ward = newsletter_data.get('ward_number')
    newsletter_relevance = newsletter_data.get('relevance_score')

    # MVP: Topics filter (at least one topic must match)
    rule_topics = rule.get('topics', [])
    if rule_topics:
        # At least one rule topic must be in newsletter topics
        if not any(topic in newsletter_topics for topic in rule_topics):
            return False

    # Phase 2: Keywords filter (at least one keyword must be found)
    rule_keywords = rule.get('keywords', [])
    if rule_keywords:
        # At least one keyword must appear in newsletter text (case-insensitive)
        if not any(keyword.lower() in newsletter_text for keyword in rule_keywords):
            return False

    # Phase 2: Minimum relevance score
    min_score = rule.get('min_relevance_score')
    if min_score is not None:
        if newsletter_relevance is None or newsletter_relevance < min_score:
            return False

    # Phase 2: Source filter (newsletter must be from one of specified sources)
    rule_source_ids = rule.get('source_ids', [])
    if rule_source_ids:
        if newsletter_source_id not in rule_source_ids:
            return False

    # Phase 2: Ward filter (newsletter must be from alderman in one of specified wards)
    rule_wards = rule.get('ward_numbers', [])
    if rule_wards:
        if newsletter_ward not in rule_wards:
            return False

    # All conditions passed
    return True


def queue_notifications(
    newsletter_id: str,
    matched_rules: List[Dict[str, Any]]
) -> int:
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

    supabase = get_supabase_client()

    # Generate digest batch ID for daily grouping (YYYY-MM-DD)
    today = date.today().isoformat()

    # Prepare notifications for batch insert
    notifications = []
    for match in matched_rules:
        notifications.append({
            'user_id': match['user_id'],
            'newsletter_id': newsletter_id,
            'rule_id': match['rule_id'],
            'status': 'pending',
            'digest_batch_id': today
        })

    # Insert notifications individually to handle duplicates gracefully
    # Unique constraint on (user_id, newsletter_id, rule_id) will prevent duplicates
    queued_count = 0
    for notification in notifications:
        try:
            supabase.table('notification_queue') \
                .insert(notification, returning='minimal') \
                .execute()
            queued_count += 1
        except Exception as e:
            # Skip duplicate entries silently (unique constraint violation)
            # All other errors are also caught to prevent ingestion failures
            pass

    return queued_count


def get_pending_notifications_by_user(digest_batch_id: Optional[str] = None) -> Dict[str, List[Dict[str, Any]]]:
    """
    Get all pending notifications grouped by user.

    Args:
        digest_batch_id: Optional batch ID to filter by (YYYY-MM-DD format)
                         If None, gets all pending notifications

    Returns:
        Dictionary mapping user_id to list of notification records
    """
    supabase = get_supabase_client()

    # Build query
    query = supabase.table('notification_queue') \
        .select('*, newsletter:newsletters(id, subject, received_date, plain_text, summary, topics, relevance_score, source:sources(name, ward_number))') \
        .eq('status', 'pending') \
        .order('created_at', desc=False)

    if digest_batch_id:
        query = query.eq('digest_batch_id', digest_batch_id)

    response = query.execute()

    if not response.data:
        return {}

    # Group by user_id
    notifications_by_user = {}
    for notification in response.data:
        user_id = notification['user_id']
        if user_id not in notifications_by_user:
            notifications_by_user[user_id] = []
        notifications_by_user[user_id].append(notification)

    return notifications_by_user
