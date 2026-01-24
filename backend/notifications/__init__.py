"""
Notification system for Chicago Newsletter Aggregator.

This module handles:
- Matching newsletters against user-defined notification rules
- Queuing notifications for delivery
- Sending notification emails via Resend
- Processing notification queue (daily digests)
"""

from .rule_matcher import match_newsletter_to_rules, queue_notifications
from .email_sender import send_daily_digest

__all__ = [
    'match_newsletter_to_rules',
    'queue_notifications',
    'send_daily_digest',
]
