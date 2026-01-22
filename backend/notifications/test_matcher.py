"""
Test utility for notification rule matching.

Fetches a recent newsletter and tests rule matching without sending emails.
Useful for debugging and verifying matching logic.

Usage:
    uv run python -m notifications.test_matcher
"""

from shared.db import get_supabase_client
from notifications.rule_matcher import match_newsletter_to_rules


def test_matching():
    """Test notification matching with a recent newsletter."""
    supabase = get_supabase_client()

    # Fetch most recent newsletter with topics
    response = supabase.table('newsletters') \
        .select('id, subject, topics, plain_text, source_id, relevance_score, sources(ward_number)') \
        .not_('topics', 'is', None) \
        .order('created_at', desc=True) \
        .limit(1) \
        .execute()

    if not response.data:
        print("No newsletters found in database")
        return

    newsletter = response.data[0]
    newsletter_id = newsletter['id']

    print("Testing notification matching")
    print("=" * 60)
    print(f"Newsletter: {newsletter['subject'][:60]}...")
    print(f"ID: {newsletter_id}")
    print(f"Topics: {newsletter.get('topics', [])}")
    print(f"Relevance: {newsletter.get('relevance_score')}")
    print()

    # Prepare newsletter data
    newsletter_data = {
        'topics': newsletter.get('topics', []),
        'plain_text': newsletter.get('plain_text', ''),
        'source_id': newsletter.get('source_id'),
        'ward_number': newsletter.get('sources', {}).get('ward_number') if newsletter.get('sources') else None,
        'relevance_score': newsletter.get('relevance_score')
    }

    # Find matching rules
    matched_rules = match_newsletter_to_rules(newsletter_id, newsletter_data)

    if not matched_rules:
        print("No matching rules found")
        print()
        print("Possible reasons:")
        print("- No users have created notification rules yet")
        print("- No rules match this newsletter's topics")
        print("- Users have notifications disabled")
    else:
        print(f"Found {len(matched_rules)} matching rule(s):")
        print("-" * 60)
        for match in matched_rules:
            print(f"User ID: {match['user_id']}")
            print(f"Rule ID: {match['rule_id']}")
            print(f"Rule Name: {match['rule_name']}")
            print()

        # Show what would happen if we queued these
        print("If these were queued:")
        for match in matched_rules:
            print(f"  - User {match['user_id']} would receive notification for rule '{match['rule_name']}'")

    print("=" * 60)
    print("Test complete (no emails sent)")


if __name__ == '__main__':
    test_matching()
