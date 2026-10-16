"""
Email sending via Resend API for notification system.

Handles sending digest emails (daily and weekly) to users with matched content.
Data preparation lives in `digest_data`, rendering in `digest_html` and `digest_text`.
"""

import os
from typing import Any

import resend

from notifications.digest_config import DigestType, frontend_base_url
from notifications.digest_data import (
    prepare_newsletter_data,
    prepare_weekly_report_data,
)
from notifications.digest_html import build_digest_html
from notifications.digest_text import build_digest_text
from notifications.unsubscribe_tokens import generate_unsubscribe_token

# Initialize Resend with API key from environment
resend.api_key = os.getenv("RESEND_API_KEY")


def _build_unsubscribe_url(user_id: str) -> str:
    """
    Build unsubscribe URL with signed token.

    Args:
        user_id: User's unique identifier

    Returns:
        Complete unsubscribe URL with token parameter
    """
    token = generate_unsubscribe_token(user_id)
    base_url = frontend_base_url()
    return f"{base_url}/unsubscribe?token={token}"


def send_digest(
    user_id: str,
    user_email: str,
    notifications: list[dict[str, Any]],
    digest_type: DigestType,
    preferences_url: str | None = None,
) -> dict[str, Any]:
    """
    Send a digest email (daily or weekly) with matched content.

    Generic digest sender that handles both daily newsletter digests and
    weekly topic report digests using template-based rendering.

    Args:
        user_id: User's unique identifier (for generating unsubscribe token)
        user_email: Recipient email address
        notifications: List of notification records (from notification_queue)
        digest_type: Type of digest (DigestType.DAILY or DigestType.WEEKLY)
        preferences_url: URL to preferences page for managing notifications

    Returns:
        Dictionary with 'success' (bool), 'email_id' (str if success), 'error' (str if failed)
    """
    if not notifications:
        return {"success": False, "error": "No notifications to send"}

    try:
        # Use default preferences URL if not provided
        if preferences_url is None:
            base_url = frontend_base_url()
            preferences_url = f"{base_url}/preferences"

        # Generate one-click unsubscribe URL (RFC 8058)
        unsubscribe_url = _build_unsubscribe_url(user_id)

        # Get from email from environment
        from_email = os.getenv(
            "NOTIFICATION_FROM_EMAIL", "newsletter-notifications@open-advocacy.com"
        )

        # Prepare data based on digest type
        if digest_type == DigestType.DAILY:
            prepared_data = prepare_newsletter_data(notifications)
            subject = f"Your Daily Chicago Alderman Newsletter Digest ({len(prepared_data)} newsletters)"
        else:  # WEEKLY
            prepared_data = prepare_weekly_report_data(notifications)
            subject = f"Your Weekly Chicago Alderman Topic Digest ({len(prepared_data)} topics)"

        # Check for empty content - don't send empty digests
        if not prepared_data:
            return {"success": False, "error": "Empty digest content"}

        # Build email content using templates
        html_body = build_digest_html(
            prepared_data, digest_type, preferences_url, unsubscribe_url
        )
        text_body = build_digest_text(
            prepared_data, digest_type, preferences_url, unsubscribe_url
        )

        # Send email via Resend
        response = resend.Emails.send(
            {
                "from": f"Chicago Alderman Newsletter Tracker <{from_email}>",
                "to": user_email,
                "subject": subject,
                "html": html_body,
                "text": text_body,
                "headers": {
                    "List-Unsubscribe": f"<{unsubscribe_url}>",
                    "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
                },
            }
        )

        return {"success": True, "email_id": response.get("id")}

    except Exception as e:  # noqa: BLE001  send boundary: report failure to the caller
        return {"success": False, "error": str(e)}
