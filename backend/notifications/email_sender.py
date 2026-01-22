"""
Email sending via Resend API for notification system.

Handles sending daily digest emails to users with matched newsletters.
"""

import os
from typing import List, Dict, Any
from datetime import datetime
import resend


# Initialize Resend with API key from environment
resend.api_key = os.getenv('RESEND_API_KEY')


def send_daily_digest(
    user_email: str,
    notifications: List[Dict[str, Any]],
    preferences_url: str = "http://localhost:4321/preferences"
) -> Dict[str, Any]:
    """
    Send a daily digest email with all matched newsletters.

    Args:
        user_email: Recipient email address
        notifications: List of notification records (from notification_queue)
        preferences_url: URL to preferences page for managing notifications

    Returns:
        Dictionary with 'success' (bool), 'email_id' (str if success), 'error' (str if failed)
    """
    if not notifications:
        return {'success': False, 'error': 'No notifications to send'}

    # Get from email from environment
    from_email = os.getenv('NOTIFICATION_FROM_EMAIL', 'newsletter-notifications@open-advocacy.com')

    # Build email content
    subject = f"Your Daily Chicago Newsletter Digest ({len(notifications)} newsletters)"
    html_body = _build_digest_html(notifications, preferences_url)
    text_body = _build_digest_text(notifications, preferences_url)

    try:
        # Send email via Resend
        response = resend.Emails.send({
            "from": from_email,
            "to": user_email,
            "subject": subject,
            "html": html_body,
            "text": text_body
        })

        return {
            'success': True,
            'email_id': response.get('id')
        }

    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }


def _build_digest_html(notifications: List[Dict[str, Any]], preferences_url: str) -> str:
    """Build HTML email body for daily digest."""

    # Group newsletters (extract newsletter data from joined query)
    newsletters = []
    for notif in notifications:
        newsletter_data = notif.get('newsletter', {})
        if newsletter_data:
            newsletters.append(newsletter_data)

    # Deduplicate newsletters (same newsletter might match multiple rules)
    unique_newsletters = {}
    for newsletter in newsletters:
        newsletter_id = newsletter.get('id')
        if newsletter_id and newsletter_id not in unique_newsletters:
            unique_newsletters[newsletter_id] = newsletter

    sorted_newsletters = sorted(
        unique_newsletters.values(),
        key=lambda n: n.get('received_date', ''),
        reverse=True
    )

    # Build HTML
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Daily Newsletter Digest</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 600px;
            margin: 0 auto;
            padding: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        .header {{
            border-bottom: 3px solid #2563eb;
            padding-bottom: 15px;
            margin-bottom: 25px;
        }}
        h1 {{
            margin: 0;
            color: #1e40af;
            font-size: 24px;
        }}
        .subtitle {{
            color: #6b7280;
            margin: 5px 0 0 0;
            font-size: 14px;
        }}
        .newsletter {{
            border-left: 4px solid #e5e7eb;
            padding: 15px;
            margin-bottom: 20px;
            background-color: #f9fafb;
        }}
        .newsletter-title {{
            font-size: 18px;
            font-weight: 600;
            color: #1f2937;
            margin: 0 0 8px 0;
        }}
        .newsletter-meta {{
            color: #6b7280;
            font-size: 13px;
            margin-bottom: 10px;
        }}
        .newsletter-summary {{
            margin: 10px 0;
            color: #374151;
        }}
        .topics {{
            display: flex;
            flex-wrap: wrap;
            gap: 6px;
            margin: 10px 0;
        }}
        .topic {{
            background-color: #dbeafe;
            color: #1e40af;
            padding: 4px 10px;
            border-radius: 12px;
            font-size: 12px;
            font-weight: 500;
        }}
        .read-more {{
            display: inline-block;
            margin-top: 8px;
            color: #2563eb;
            text-decoration: none;
            font-weight: 500;
        }}
        .read-more:hover {{
            text-decoration: underline;
        }}
        .footer {{
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #e5e7eb;
            font-size: 13px;
            color: #6b7280;
            text-align: center;
        }}
        .footer a {{
            color: #2563eb;
            text-decoration: none;
        }}
        .footer a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📬 Daily Newsletter Digest</h1>
            <p class="subtitle">Chicago aldermen newsletters matching your interests</p>
        </div>
"""

    # Add each newsletter
    for newsletter in sorted_newsletters:
        title = newsletter.get('subject', 'Untitled Newsletter')
        source = newsletter.get('source', {})
        source_name = source.get('name', 'Unknown Source') if source else 'Unknown Source'
        ward_number = source.get('ward_number') if source else None
        ward_text = f" (Ward {ward_number})" if ward_number else ""

        received_date = newsletter.get('received_date', '')
        if received_date:
            try:
                date_obj = datetime.fromisoformat(received_date.replace('Z', '+00:00'))
                date_formatted = date_obj.strftime('%B %d, %Y')
            except:
                date_formatted = received_date[:10]
        else:
            date_formatted = 'Unknown date'

        summary = newsletter.get('summary', '')
        topics = newsletter.get('topics', [])
        newsletter_id = newsletter.get('id', '')

        # Build newsletter link (assuming frontend URL pattern)
        newsletter_url = f"http://localhost:4321/newsletter/{newsletter_id}"

        html += f"""
        <div class="newsletter">
            <h2 class="newsletter-title">{title}</h2>
            <div class="newsletter-meta">
                From <strong>{source_name}</strong>{ward_text} • {date_formatted}
            </div>
"""

        if summary:
            html += f"""
            <div class="newsletter-summary">{summary}</div>
"""

        if topics:
            html += """
            <div class="topics">
"""
            for topic in topics[:5]:  # Limit to 5 topics for readability
                html += f"""
                <span class="topic">{topic}</span>
"""
            html += """
            </div>
"""

        html += f"""
            <a href="{newsletter_url}" class="read-more">Read full newsletter →</a>
        </div>
"""

    # Add footer
    html += f"""
        <div class="footer">
            <p>
                You received this email because you have active notification rules.
                <br>
                <a href="{preferences_url}">Manage your notification preferences</a>
            </p>
            <p style="margin-top: 15px; color: #9ca3af; font-size: 12px;">
                Chicago Newsletter Aggregator • Built for Strong Towns Chicago
            </p>
        </div>
    </div>
</body>
</html>
"""

    return html


def _build_digest_text(notifications: List[Dict[str, Any]], preferences_url: str) -> str:
    """Build plain text email body for daily digest."""

    # Group and deduplicate newsletters (same logic as HTML)
    newsletters = []
    for notif in notifications:
        newsletter_data = notif.get('newsletter', {})
        if newsletter_data:
            newsletters.append(newsletter_data)

    unique_newsletters = {}
    for newsletter in newsletters:
        newsletter_id = newsletter.get('id')
        if newsletter_id and newsletter_id not in unique_newsletters:
            unique_newsletters[newsletter_id] = newsletter

    sorted_newsletters = sorted(
        unique_newsletters.values(),
        key=lambda n: n.get('received_date', ''),
        reverse=True
    )

    # Build plain text
    text = f"""DAILY NEWSLETTER DIGEST
Chicago aldermen newsletters matching your interests

You have {len(sorted_newsletters)} newsletters to review:

"""

    # Add each newsletter
    for i, newsletter in enumerate(sorted_newsletters, 1):
        title = newsletter.get('subject', 'Untitled Newsletter')
        source = newsletter.get('source', {})
        source_name = source.get('name', 'Unknown Source') if source else 'Unknown Source'
        ward_number = source.get('ward_number') if source else None
        ward_text = f" (Ward {ward_number})" if ward_number else ""

        received_date = newsletter.get('received_date', '')
        if received_date:
            try:
                date_obj = datetime.fromisoformat(received_date.replace('Z', '+00:00'))
                date_formatted = date_obj.strftime('%B %d, %Y')
            except:
                date_formatted = received_date[:10]
        else:
            date_formatted = 'Unknown date'

        summary = newsletter.get('summary', '')
        topics = newsletter.get('topics', [])
        newsletter_id = newsletter.get('id', '')
        newsletter_url = f"http://localhost:4321/newsletter/{newsletter_id}"

        text += f"""{i}. {title}
From: {source_name}{ward_text}
Date: {date_formatted}
"""

        if summary:
            text += f"\n{summary}\n"

        if topics:
            text += f"\nTopics: {', '.join(topics[:5])}\n"

        text += f"\nRead more: {newsletter_url}\n\n"
        text += "-" * 60 + "\n\n"

    # Add footer
    text += f"""
Manage your notification preferences: {preferences_url}

---
Chicago Newsletter Aggregator
Built for Strong Towns Chicago
"""

    return text
