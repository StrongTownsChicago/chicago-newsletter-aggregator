"""
Email sending via Resend API for notification system.

Handles sending digest emails (daily and weekly) to users with matched content.
"""

import os
from enum import Enum
from typing import Any
from datetime import datetime
import resend
from notifications.unsubscribe_tokens import generate_unsubscribe_token


class DigestType(Enum):
    """Type of digest email to send."""

    DAILY = "daily"
    WEEKLY = "weekly"


# Initialize Resend with API key from environment
resend.api_key = os.getenv("RESEND_API_KEY")


def _get_frontend_base_url() -> str:
    """Get frontend base URL from environment (allows runtime override for tests)."""
    return os.getenv(
        "FRONTEND_BASE_URL", "https://chicago-newsletter-aggregator.open-advocacy.com"
    )


def _build_unsubscribe_url(user_id: str) -> str:
    """
    Build unsubscribe URL with signed token.

    Args:
        user_id: User's unique identifier

    Returns:
        Complete unsubscribe URL with token parameter
    """
    token = generate_unsubscribe_token(user_id)
    base_url = _get_frontend_base_url()
    return f"{base_url}/unsubscribe?token={token}"


def _prepare_newsletter_data(
    notifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
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
        newsletter_data = notif.get("newsletter", {})
        if not newsletter_data:
            continue

        newsletter_id = newsletter_data.get("id")
        if not newsletter_id:
            continue

        # Get rule name
        rule_data = notif.get("rule", {})
        rule_name = (
            rule_data.get("name", "Unknown Rule") if rule_data else "Unknown Rule"
        )

        # Group by newsletter ID
        if newsletter_id not in newsletters_with_rules:
            newsletters_with_rules[newsletter_id] = {
                "newsletter": newsletter_data,
                "matched_rules": [],
            }

        # Add rule name if not already in list
        if rule_name not in newsletters_with_rules[newsletter_id]["matched_rules"]:
            newsletters_with_rules[newsletter_id]["matched_rules"].append(rule_name)

    # Sort by received date
    sorted_items = sorted(
        newsletters_with_rules.values(),
        key=lambda n: n["newsletter"].get("received_date", ""),
        reverse=True,
    )

    # Extract and format all data once
    prepared_newsletters = []
    for item in sorted_items:
        newsletter = item["newsletter"]

        # Extract source info
        source = newsletter.get("source", {})
        source_name = (
            source.get("name", "Unknown Source") if source else "Unknown Source"
        )
        ward_number = source.get("ward_number") if source else None
        ward_text = f" (Ward {ward_number})" if ward_number else ""

        # Format date
        received_date = newsletter.get("received_date", "")
        if received_date:
            try:
                date_obj = datetime.fromisoformat(received_date.replace("Z", "+00:00"))
                date_formatted = date_obj.strftime("%B %d, %Y")
            except (ValueError, TypeError):
                date_formatted = received_date[:10]
        else:
            date_formatted = "Unknown date"

        # Build newsletter URL
        newsletter_id = newsletter.get("id", "")
        base_url = _get_frontend_base_url()
        newsletter_url = f"{base_url}/newsletter/{newsletter_id}"

        # Prepare complete newsletter data
        prepared_newsletters.append(
            {
                "title": newsletter.get("subject", "Untitled Newsletter"),
                "source_name": source_name,
                "ward_text": ward_text,
                "date_formatted": date_formatted,
                "summary": newsletter.get("summary", ""),
                "topics": newsletter.get("topics", []),
                "newsletter_url": newsletter_url,
                "matched_rules": item["matched_rules"],
            }
        )

    return prepared_newsletters


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
            base_url = _get_frontend_base_url()
            preferences_url = f"{base_url}/preferences"

        # Generate one-click unsubscribe URL (RFC 8058)
        unsubscribe_url = _build_unsubscribe_url(user_id)

        # Get from email from environment
        from_email = os.getenv(
            "NOTIFICATION_FROM_EMAIL", "newsletter-notifications@open-advocacy.com"
        )

        # Prepare data based on digest type
        if digest_type == DigestType.DAILY:
            prepared_data = _prepare_newsletter_data(notifications)
            subject = f"Your Daily Chicago Alderman Newsletter Digest ({len(prepared_data)} newsletters)"
        else:  # WEEKLY
            prepared_data = _prepare_weekly_report_data(notifications)
            subject = f"Your Weekly Chicago Alderman Topic Digest ({len(prepared_data)} topics)"

        # Build email content using templates
        html_body = _build_digest_html(
            prepared_data, digest_type, preferences_url, unsubscribe_url
        )
        text_body = _build_digest_text(
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

    except Exception as e:
        return {"success": False, "error": str(e)}


def send_daily_digest(
    user_id: str,
    user_email: str,
    notifications: list[dict[str, Any]],
    preferences_url: str | None = None,
) -> dict[str, Any]:
    """
    Send a daily digest email with all matched newsletters.

    Wrapper around send_digest() for backward compatibility.

    Args:
        user_id: User's unique identifier (for generating unsubscribe token)
        user_email: Recipient email address
        notifications: List of notification records (from notification_queue)
        preferences_url: URL to preferences page for managing notifications

    Returns:
        Dictionary with 'success' (bool), 'email_id' (str if success), 'error' (str if failed)
    """
    return send_digest(
        user_id, user_email, notifications, DigestType.DAILY, preferences_url
    )


def _render_daily_content_html(prepared_newsletters: list[dict[str, Any]]) -> str:
    """Render daily digest content section (newsletter cards) as HTML."""
    content = ""
    for newsletter in prepared_newsletters:
        content += f"""
        <div class="newsletter">
            <h2 class="newsletter-title">{newsletter["title"]}</h2>
            <div class="newsletter-meta">
                From <strong>{newsletter["source_name"]}</strong>{newsletter["ward_text"]} • {newsletter["date_formatted"]}
            </div>
"""

        # Add matched rules indicator
        if newsletter["matched_rules"]:
            rules_text = ", ".join(newsletter["matched_rules"])
            content += f"""
            <div class="matched-rules">
                <strong>✓ Matched your rules:</strong> {rules_text}
            </div>
"""

        if newsletter["summary"]:
            content += f"""
            <div class="newsletter-summary">{newsletter["summary"]}</div>
"""

        if newsletter["topics"]:
            content += """
            <div class="topics">
"""
            for topic in newsletter["topics"][:5]:  # Limit to 5 topics
                content += f"""
                <span class="topic">{topic}</span>
"""
            content += """
            </div>
"""

        content += f"""
            <a href="{newsletter["newsletter_url"]}" class="read-more">Read full newsletter →</a>
        </div>
"""
    return content


def _render_weekly_content_html(prepared_reports: list[dict[str, Any]]) -> str:
    """Render weekly digest content section (topic reports) as HTML."""
    content = ""
    base_url = _get_frontend_base_url()

    for report in prepared_reports:
        # Build search URL for this topic
        topic_url = f"{base_url}/search?topics={report['topic']}"

        content += f"""
        <div class="topic-report">
            <h2 class="topic-title">{report["topic_display"]}</h2>
            <p class="topic-meta">
                Week of {report["week_range"]} &bull; Based on {report["newsletter_count"]} newsletters
            </p>

            <div class="summary">
                {_format_summary_paragraphs(report["summary"])}
            </div>

            <div class="matched-rules">
                ✓ Matched your rule: {", ".join(report["matched_rules"])}
            </div>

            <p style="margin-top: 15px;">
                <a href="{topic_url}" class="view-link">
                    View all {report["topic_display"]} newsletters from this week →
                </a>
            </p>
        </div>
"""
    return content


def _build_digest_html(
    prepared_data: list[dict[str, Any]],
    digest_type: DigestType,
    preferences_url: str,
    unsubscribe_url: str,
) -> str:
    """
    Build HTML email body for digest (daily or weekly).

    Uses template-based rendering with type-specific content sections.

    Args:
        prepared_data: List of prepared data (newsletters or reports)
        digest_type: Type of digest (DAILY or WEEKLY)
        preferences_url: URL to preferences page
        unsubscribe_url: One-click unsubscribe URL with signed token

    Returns:
        HTML string
    """
    # Determine header and content based on digest type
    if digest_type == DigestType.DAILY:
        title = "Daily Chicago Aldermen Newsletter Digest"
        subtitle = "Chicago aldermen newsletters matching your interests"
        content_section = _render_daily_content_html(prepared_data)
    else:  # WEEKLY
        title = "Weekly Topic Digest"
        subtitle = "Chicago aldermen newsletters on topics you're following"
        content_section = _render_weekly_content_html(prepared_data)

    # Build HTML with shared template structure
    html = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
            line-height: 1.6;
            color: #333;
            max-width: 650px;
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
        /* Daily digest styles */
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
        /* Weekly digest styles */
        .topic-report {{
            border-left: 4px solid #10b981;
            padding: 20px;
            margin-bottom: 30px;
            background-color: #f9fafb;
        }}
        .topic-title {{
            font-size: 20px;
            font-weight: 600;
            color: #1f2937;
            margin: 0 0 8px 0;
        }}
        .topic-meta {{
            color: #6b7280;
            font-size: 13px;
            margin-bottom: 15px;
        }}
        .summary {{
            margin: 15px 0;
            color: #374151;
        }}
        .summary p {{
            margin: 12px 0;
        }}
        .view-link {{
            color: #2563eb;
            text-decoration: none;
            font-weight: 500;
            font-size: 14px;
        }}
        .view-link:hover {{
            text-decoration: underline;
        }}
        /* Shared styles */
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
            <h1>{title}</h1>
            <p class="subtitle">{subtitle}</p>
        </div>

        {content_section}

        <div class="footer">
            <p>
                <a href="{preferences_url}">Manage your notification preferences</a>
                •
                <a href="{unsubscribe_url}">Unsubscribe</a>
            </p>
            <p style="margin-top: 15px; color: #9ca3af; font-size: 12px;">
                <a href="https://www.strongtownschicago.org/chicago-alderman-newsletters">Chicago Alderman Newsletter Tracker</a> • Built for <a href="https://strongtownschicago.org">Strong Towns Chicago</a>
            </p>
        </div>
    </div>
</body>
</html>
"""

    return html


def _render_daily_content_text(prepared_newsletters: list[dict[str, Any]]) -> str:
    """Render daily digest content section (newsletters) as plain text."""
    content = f"You have {len(prepared_newsletters)} newsletters to review:\n\n"

    for i, newsletter in enumerate(prepared_newsletters, 1):
        content += f"""{i}. {newsletter["title"]}
From: {newsletter["source_name"]}{newsletter["ward_text"]}
Date: {newsletter["date_formatted"]}
"""

        if newsletter["matched_rules"]:
            rules_text = ", ".join(newsletter["matched_rules"])
            content += f"✓ Matched your rules: {rules_text}\n"

        if newsletter["summary"]:
            content += f"\n{newsletter['summary']}\n"

        if newsletter["topics"]:
            content += f"\nTopics: {', '.join(newsletter['topics'][:5])}\n"

        content += f"\nRead more: {newsletter['newsletter_url']}\n\n"
        content += "-" * 60 + "\n\n"

    return content


def _render_weekly_content_text(prepared_reports: list[dict[str, Any]]) -> str:
    """Render weekly digest content section (topic reports) as plain text."""
    base_url = _get_frontend_base_url()
    content = f"You have {len(prepared_reports)} topic reports this week:\n\n"
    content += "=" * 70 + "\n\n"

    for i, report in enumerate(prepared_reports, 1):
        content += f"{i}. {report['topic_display']}\n"
        content += f"Week of {report['week_range']}\n"
        content += f"Based on {report['newsletter_count']} newsletters\n"

        if report["matched_rules"]:
            rules_text = ", ".join(report["matched_rules"])
            content += f"✓ Matched your rule: {rules_text}\n"

        content += "\n"
        content += report["summary"]
        content += "\n\n"

        topic_url = f"{base_url}/search?q=&ward=&topics={report['topic']}"
        content += f"View all {report['topic_display']} newsletters:\n"
        content += f"{topic_url}\n\n"
        content += "=" * 70 + "\n\n"

    return content


def _build_digest_text(
    prepared_data: list[dict[str, Any]],
    digest_type: DigestType,
    preferences_url: str,
    unsubscribe_url: str,
) -> str:
    """
    Build plain text email body for digest (daily or weekly).

    Uses template-based rendering with type-specific content sections.

    Args:
        prepared_data: List of prepared data (newsletters or reports)
        digest_type: Type of digest (DAILY or WEEKLY)
        preferences_url: URL to preferences page
        unsubscribe_url: One-click unsubscribe URL with signed token

    Returns:
        Plain text string
    """
    # Determine header and content based on digest type
    if digest_type == DigestType.DAILY:
        header = """DAILY NEWSLETTER DIGEST
Chicago aldermen newsletters matching your interests

"""
        content_section = _render_daily_content_text(prepared_data)
    else:  # WEEKLY
        header = """WEEKLY TOPIC DIGEST
Chicago aldermen newsletters on topics you're following

"""
        content_section = _render_weekly_content_text(prepared_data)

    # Build text with shared template structure
    text = header + content_section

    # Add shared footer
    text += f"""
Manage your notification preferences: {preferences_url}
Unsubscribe: {unsubscribe_url}

---
Chicago Alderman Newsletter Tracker
Built for Strong Towns Chicago - https://strongtownschicago.org
"""

    return text


def send_weekly_digest(
    user_id: str,
    user_email: str,
    notifications: list[dict[str, Any]],
    preferences_url: str | None = None,
) -> dict[str, Any]:
    """
    Send a weekly digest email with topic-based reports.

    Wrapper around send_digest() for backward compatibility.

    Args:
        user_id: User's unique identifier
        user_email: Recipient email address
        notifications: List of notification records (report references)
        preferences_url: URL to preferences page

    Returns:
        Dictionary with 'success' (bool), 'email_id' (str if success), 'error' (str if failed)
    """
    return send_digest(
        user_id, user_email, notifications, DigestType.WEEKLY, preferences_url
    )


# ============================================================================
# DATA PREPARATION FUNCTIONS
# ============================================================================


def _prepare_weekly_report_data(
    notifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extract and format weekly report data for email rendering.

    Groups notifications by topic, fetches report summaries, formats data.

    Args:
        notifications: List of notification records from database
                      (report data should be joined as 'report')

    Returns:
        List of dicts with topic, summary, newsletter_count, week_id, matched_rules
    """
    # Group by topic and collect rule names
    reports_with_rules = {}

    for notif in notifications:
        # For weekly notifications, report data is joined as "report"
        report_data = notif.get("report")
        if not report_data:
            continue

        topic = report_data.get("topic")
        if not topic:
            continue

        # Get rule name
        rule_data = notif.get("rule", {})
        rule_name = (
            rule_data.get("name", "Unknown Rule") if rule_data else "Unknown Rule"
        )

        # Group by topic
        if topic not in reports_with_rules:
            reports_with_rules[topic] = {
                "report": report_data,
                "matched_rules": [],
            }

        # Add rule name if not already in list
        if rule_name not in reports_with_rules[topic]["matched_rules"]:
            reports_with_rules[topic]["matched_rules"].append(rule_name)

    # Sort by topic name
    sorted_items = sorted(reports_with_rules.items(), key=lambda x: x[0])

    # Extract and format all data
    prepared_reports = []
    for topic, item in sorted_items:
        report = item["report"]

        # Parse week_id to readable date range
        week_id = report.get("week_id", "")
        week_range = _format_week_range(week_id)

        # Map topic to friendly name
        topic_display = _format_topic_name(topic)

        # Count newsletters
        newsletter_ids = report.get("newsletter_ids", [])
        newsletter_count = len(newsletter_ids) if newsletter_ids else 0

        prepared_reports.append(
            {
                "topic": topic,
                "topic_display": topic_display,
                "summary": report.get("report_summary", ""),
                "newsletter_count": newsletter_count,
                "week_range": week_range,
                "week_id": week_id,
                "matched_rules": item["matched_rules"],
            }
        )

    return prepared_reports


def _format_week_range(week_id: str) -> str:
    """
    Convert ISO week ID (YYYY-WXX) to readable date range.

    Args:
        week_id: ISO week identifier (e.g., "2026-W05")

    Returns:
        Formatted string (e.g., "January 26 - February 1, 2026")
    """
    try:
        year_str, week_str = week_id.split("-W")
        year = int(year_str)
        week = int(week_str)

        # Calculate week start (Monday)
        from datetime import datetime, timedelta

        jan_4 = datetime(year, 1, 4)  # Always in week 1
        week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
        week_start = week_1_monday + timedelta(weeks=week - 1)
        week_end = week_start + timedelta(days=6)

        # Format: "January 26 - February 1, 2026"
        if week_start.month == week_end.month:
            return f"{week_start.strftime('%B %d')} - {week_end.strftime('%d, %Y')}"
        else:
            return f"{week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}"

    except (ValueError, AttributeError):
        return week_id


def _format_topic_name(topic: str) -> str:
    """
    Convert topic identifier to friendly display name.

    Args:
        topic: Topic identifier (e.g., "bike_lanes")

    Returns:
        Formatted string (e.g., "Bike Lanes and Cycling Infrastructure")
    """
    topic_names = {
        "4_flats_legalization": "4-Flats and Small-Scale Housing",
        "missing_middle_housing": "Missing Middle Housing",
        "accessory_dwelling_units": "Accessory Dwelling Units (ADUs)",
        "single_stair_reform": "Single-Stair Building Reform",
        "bike_lanes": "Bike Lanes and Cycling Infrastructure",
        "street_redesign": "Street Redesign and Reconstruction",
        "street_safety_or_traffic_calming": "Street Safety and Traffic Calming",
        "transit_funding": "Public Transit Funding and Service",
        "city_budget": "City Budget and Fiscal Policy",
        "tax_policy": "Tax Policy and Revenue",
        "zoning_or_development_meeting_or_approval": "Zoning and Development Approvals",
        "city_charter": "City Charter and Governance Reform",
    }
    return topic_names.get(topic, topic.replace("_", " ").title())


# Helper function for formatting summary paragraphs (used by weekly digest HTML)
def _format_summary_paragraphs(summary: str) -> str:
    """
    Format summary text as HTML paragraphs.

    Args:
        summary: Plain text summary with paragraph breaks

    Returns:
        HTML with <p> tags
    """
    if not summary:
        return ""

    # Split on double newlines for paragraphs
    paragraphs = [p.strip() for p in summary.split("\n\n") if p.strip()]

    # Wrap each in <p> tags
    return "\n".join(f"<p>{p}</p>" for p in paragraphs)
