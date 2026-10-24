"""Plain-text bodies for daily and weekly digest emails."""

from typing import Any

from notifications.digest_config import DigestType, frontend_base_url
from shared.dates import format_received_date


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
    base_url = frontend_base_url()
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

        # Add referenced newsletters
        if report.get("referenced_newsletters"):
            content += "Referenced newsletters:\n"
            for nl in report["referenced_newsletters"]:
                date_str = format_received_date(nl["received_date"])

                # Format ward
                ward_str = (
                    f"Ward {nl['ward_number']}" if nl["ward_number"] else "Citywide"
                )

                # Build newsletter URL
                nl_url = f"{base_url}/newsletter/{nl['id']}"

                content += f"  • {ward_str}: {nl['subject']} ({date_str})\n"
                content += f"    {nl_url}\n"

            content += "\n"

        topic_url = f"{base_url}/search?topic={report['topic']}"
        content += f"View all {report['topic_display']} newsletters:\n"
        content += f"{topic_url}\n\n"
        content += "=" * 70 + "\n\n"

    return content


def build_digest_text(
    prepared_data: list[dict[str, Any]],
    digest_type: DigestType,
    preferences_url: str,
    unsubscribe_url: str,
) -> str:
    """
    Build plain text email body for digest (daily or weekly).

    Uses template-based rendering with type-specific content sections.
    `prepared_data` holds newsletters (daily) or reports (weekly);
    `unsubscribe_url` is the one-click link with a signed token.
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
