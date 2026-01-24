"""
Test utility for notification rule matching.

Fetches a recent newsletter and tests rule matching + queuing without sending emails.

Usage:
    # Test matching only (don't queue)
    uv run python -m notifications.test_matcher

    # Test matching AND queuing
    uv run python -m notifications.test_matcher --queue
"""

import argparse
from shared.db import get_supabase_client
from notifications.rule_matcher import match_newsletter_to_rules, queue_notifications


def test_matching(should_queue: bool = False):
    """
    Test notification matching with a recent newsletter.

    Args:
        should_queue: If True, actually queue the notifications
    """
    supabase = get_supabase_client()

    # Fetch most recent newsletters with topics
    response = supabase.table('newsletters') \
        .select('id, subject, topics, plain_text, source_id, relevance_score, sources(ward_number)') \
        .not_.is_('topics', None) \
        .order('created_at', desc=True) \
        .limit(10) \
        .execute()

    if not response.data:
        print("No newsletters found in database")
        return

    for newsletter in response.data:
        newsletter_id = newsletter['id']

        print("Testing Notification Matching")
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
        print("Running match_newsletter_to_rules()...")
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
                print(f"  User ID: {match['user_id']}")
                print(f"  Rule ID: {match['rule_id']}")
                print(f"  Rule Name: {match['rule_name']}")
                print()

            # Queue or simulate queuing
            if should_queue:
                print("Queuing notifications...")
                queued_count = queue_notifications(newsletter_id, matched_rules)
                print(f"✓ Queued {queued_count} notification(s)")
            else:
                print("Dry run mode - would queue the following:")
                for match in matched_rules:
                    print(f"  - User {match['user_id']} would be notified for rule '{match['rule_name']}'")
                print()
                print("(Use --queue flag to actually queue these notifications)")

    print("=" * 60)
    print("Test complete")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Test notification matching logic'
    )

    parser.add_argument(
        '--queue',
        action='store_true',
        help='Actually queue the notifications (not just a dry run)'
    )

    args = parser.parse_args()
    test_matching(should_queue=args.queue)


if __name__ == '__main__':
    main()
