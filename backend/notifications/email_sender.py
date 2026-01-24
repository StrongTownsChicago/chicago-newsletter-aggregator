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

# Frontend base URL for links in emails
FRONTEND_BASE_URL = os.getenv('FRONTEND_BASE_URL', 'https://chicago-newsletter-aggregator.open-advocacy.com')


def _prepare_newsletter_data(notifications: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Group notifications by newsletter, collect matching rules, and extract all needed data.

    This does ALL data processing once so formatters only handle presentation.

    Args:
        notifications: List of notification records from database

    Returns:
        List of dicts with all formatted fields ready for display
    """
    # Group by newsletter and collect rule names
    newsletters_with_rules = {}
    for notif in notifications:
        newsletter_data = notif.get('newsletter', {})
        if not newsletter_data:
            continue

        newsletter_id = newsletter_data.get('id')
        if not newsletter_id:
            continue

        # Get rule name
        rule_data = notif.get('rule', {})
        rule_name = rule_data.get('name', 'Unknown Rule') if rule_data else 'Unknown Rule'

        # Group by newsletter ID
        if newsletter_id not in newsletters_with_rules:
            newsletters_with_rules[newsletter_id] = {
                'newsletter': newsletter_data,
                'matched_rules': []
            }

        # Add rule name if not already in list
        if rule_name not in newsletters_with_rules[newsletter_id]['matched_rules']:
            newsletters_with_rules[newsletter_id]['matched_rules'].append(rule_name)

    # Sort by received date
    sorted_items = sorted(
        newsletters_with_rules.values(),
        key=lambda n: n['newsletter'].get('received_date', ''),
        reverse=True
    )

    # Extract and format all data once
    prepared_newsletters = []
    for item in sorted_items:
        newsletter = item['newsletter']

        # Extract source info
        source = newsletter.get('source', {})
        source_name = source.get('name', 'Unknown Source') if source else 'Unknown Source'
        ward_number = source.get('ward_number') if source else None
        ward_text = f" (Ward {ward_number})" if ward_number else ""

        # Format date
        received_date = newsletter.get('received_date', '')
        if received_date:
            try:
                date_obj = datetime.fromisoformat(received_date.replace('Z', '+00:00'))
                date_formatted = date_obj.strftime('%B %d, %Y')
            except:
                date_formatted = received_date[:10]
        else:
            date_formatted = 'Unknown date'

        # Build newsletter URL
        newsletter_id = newsletter.get('id', '')
        newsletter_url = f"{FRONTEND_BASE_URL}/newsletter/{newsletter_id}"

        # Prepare complete newsletter data
        prepared_newsletters.append({
            'title': newsletter.get('subject', 'Untitled Newsletter'),
            'source_name': source_name,
            'ward_text': ward_text,
            'date_formatted': date_formatted,
            'summary': newsletter.get('summary', ''),
            'topics': newsletter.get('topics', []),
            'newsletter_url': newsletter_url,
            'matched_rules': item['matched_rules']
        })

    return prepared_newsletters


def send_daily_digest(
    user_email: str,
    notifications: List[Dict[str, Any]],
    preferences_url: str = None
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

    # Use default preferences URL if not provided
    if preferences_url is None:
        preferences_url = f"{FRONTEND_BASE_URL}/preferences"

    # Get from email from environment
    from_email = os.getenv('NOTIFICATION_FROM_EMAIL', 'newsletter-notifications@open-advocacy.com')

    # Prepare all newsletter data once (grouping, extraction, formatting)
    prepared_newsletters = _prepare_newsletter_data(notifications)

    # Build email content (formatters only handle presentation)
    subject = f"Your Daily Chicago Newsletter Digest ({len(prepared_newsletters)} newsletters)"
    html_body = _build_digest_html(prepared_newsletters, preferences_url)
    text_body = _build_digest_text(prepared_newsletters, preferences_url)

    try:
        # Send email via Resend
        response = resend.Emails.send({
            "from": f"Chicago Alderman Newsletter Tracker <{from_email}>",
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


def _build_digest_html(prepared_newsletters: List[Dict[str, Any]], preferences_url: str) -> str:
    """
    Build HTML email body for daily digest.

    Args:
        prepared_newsletters: List of dicts with all newsletter data pre-extracted and formatted
        preferences_url: URL to preferences page

    Returns:
        HTML string
    """

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
        .matched-rules {{
            background-color: #f0fdf4;
            border-left: 3px solid #10b981;
            padding: 8px 12px;
            margin: 10px 0;
            font-size: 13px;
            color: #065f46;
        }}
        .matched-rules strong {{
            color: #047857;
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

    # Add each newsletter (all data already extracted and formatted)
    for newsletter in prepared_newsletters:
        html += f"""
        <div class="newsletter">
            <h2 class="newsletter-title">{newsletter['title']}</h2>
            <div class="newsletter-meta">
                From <strong>{newsletter['source_name']}</strong>{newsletter['ward_text']} • {newsletter['date_formatted']}
            </div>
"""

        # Add matched rules indicator
        if newsletter['matched_rules']:
            rules_text = ', '.join(newsletter['matched_rules'])
            html += f"""
            <div class="matched-rules">
                <strong>✓ Matched your rules:</strong> {rules_text}
            </div>
"""

        if newsletter['summary']:
            html += f"""
            <div class="newsletter-summary">{newsletter['summary']}</div>
"""

        if newsletter['topics']:
            html += """
            <div class="topics">
"""
            for topic in newsletter['topics'][:5]:  # Limit to 5 topics for readability
                html += f"""
                <span class="topic">{topic}</span>
"""
            html += """
            </div>
"""

        html += f"""
            <a href="{newsletter['newsletter_url']}" class="read-more">Read full newsletter →</a>
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
                <a href="https://www.strongtownschicago.org/chicago-alderman-newsletters">Chicago Newsletter Aggregator</a> • Built for <a href="https://strongtownschicago.org">Strong Towns Chicago</a>
            </p>
        </div>
    </div>
</body>
</html>
"""

    return html


def _build_digest_text(prepared_newsletters: List[Dict[str, Any]], preferences_url: str) -> str:
    """
    Build plain text email body for daily digest.

    Args:
        prepared_newsletters: List of dicts with all newsletter data pre-extracted and formatted
        preferences_url: URL to preferences page

    Returns:
        Plain text string
    """
    # Build plain text
    text = f"""DAILY NEWSLETTER DIGEST
Chicago aldermen newsletters matching your interests

You have {len(prepared_newsletters)} newsletters to review:

"""

    # Add each newsletter (all data already extracted and formatted)
    for i, newsletter in enumerate(prepared_newsletters, 1):
        text += f"""{i}. {newsletter['title']}
From: {newsletter['source_name']}{newsletter['ward_text']}
Date: {newsletter['date_formatted']}
"""

        # Add matched rules
        if newsletter['matched_rules']:
            rules_text = ', '.join(newsletter['matched_rules'])
            text += f"✓ Matched your rules: {rules_text}\n"

        if newsletter['summary']:
            text += f"\n{newsletter['summary']}\n"

        if newsletter['topics']:
            text += f"\nTopics: {', '.join(newsletter['topics'][:5])}\n"

        text += f"\nRead more: {newsletter['newsletter_url']}\n\n"
        text += "-" * 60 + "\n\n"

    # Add footer
    text += f"""
Manage your notification preferences: {preferences_url}

---
Chicago Newsletter Aggregator
Built for Strong Towns Chicago - https://strongtownschicago.org
"""

    return text
