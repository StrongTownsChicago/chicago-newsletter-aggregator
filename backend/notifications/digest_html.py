"""HTML bodies for daily and weekly digest emails."""

from datetime import datetime
from html import escape
from typing import Any
from urllib.parse import quote

from notifications.digest_config import DigestType, frontend_base_url


def _render_daily_content_html(prepared_newsletters: list[dict[str, Any]]) -> str:
    """Render daily digest content section (newsletter cards) as HTML."""
    content = ""
    for newsletter in prepared_newsletters:
        content += f"""
        <div class="newsletter">
            <h2 class="newsletter-title">{escape(newsletter["title"])}</h2>
            <div class="newsletter-meta">
                From <strong>{escape(newsletter["source_name"])}</strong>{escape(newsletter["ward_text"])} • {escape(newsletter["date_formatted"])}
            </div>
"""

        # Add matched rules indicator
        if newsletter["matched_rules"]:
            rules_text = escape(", ".join(newsletter["matched_rules"]))
            content += f"""
            <div class="matched-rules">
                <strong>✓ Matched your rules:</strong> {rules_text}
            </div>
"""

        if newsletter["summary"]:
            content += f"""
            <div class="newsletter-summary">{escape(newsletter["summary"])}</div>
"""

        if newsletter["topics"]:
            content += """
            <div class="topics">
"""
            for topic in newsletter["topics"][:5]:  # Limit to 5 topics
                content += f"""
                <span class="topic">{escape(topic)}</span>
"""
            content += """
            </div>
"""

        content += f"""
            <a href="{escape(newsletter["newsletter_url"])}" class="read-more">Read full newsletter →</a>
        </div>
"""
    return content


def _render_weekly_content_html(prepared_reports: list[dict[str, Any]]) -> str:
    """Render weekly digest content section (topic reports) as HTML."""
    content = ""
    base_url = frontend_base_url()

    for report in prepared_reports:
        # Build search URL for this topic
        topic_url = f"{base_url}/search?topic={quote(report['topic'])}"

        content += f"""
        <div class="topic-report">
            <h2 class="topic-title">{escape(report["topic_display"])}</h2>
            <p class="topic-meta">
                Week of {escape(report["week_range"])} &bull; Based on {report["newsletter_count"]} newsletters
            </p>

            <div class="summary">
                {_format_summary_paragraphs(report["summary"])}
            </div>

            <div class="matched-rules">
                ✓ Matched your rule: {escape(", ".join(report["matched_rules"]))}
            </div>
"""

        # Add referenced newsletters section
        if report.get("referenced_newsletters"):
            content += """
            <div class="referenced-newsletters">
                <strong>Referenced newsletters:</strong>
                <ul style="margin: 8px 0; padding-left: 20px;">
"""
            for nl in report["referenced_newsletters"]:
                # Format date
                try:
                    date_obj = datetime.fromisoformat(nl["received_date"])
                    date_str = date_obj.strftime("%B %d, %Y")
                except (ValueError, TypeError):
                    date_str = nl["received_date"][:10]

                # Format ward
                ward_str = (
                    f"Ward {nl['ward_number']}" if nl["ward_number"] else "Citywide"
                )

                # Build newsletter URL
                nl_url = f"{base_url}/newsletter/{nl['id']}"

                content += f"""
                    <li style="margin: 4px 0;">
                        <a href="{escape(nl_url)}" style="color: #2563eb; text-decoration: none;">
                            {escape(ward_str)}: {escape(nl["subject"])}
                        </a>
                        <span style="color: #6b7280; font-size: 13px;"> &bull; {escape(date_str)}</span>
                    </li>
"""

            content += """
                </ul>
            </div>
"""

        content += f"""
            <p style="margin-top: 15px;">
                <a href="{escape(topic_url)}" class="view-link">
                    View all newsletters on {escape(report["topic_display"])} →
                </a>
            </p>
        </div>
"""
    return content


def build_digest_html(
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
        .referenced-newsletters {{
            margin: 15px 0;
            padding: 12px;
            background-color: #f9fafb;
            border-left: 3px solid #e5e7eb;
            font-size: 13px;
        }}
        .referenced-newsletters strong {{
            color: #374151;
        }}
        .referenced-newsletters ul {{
            list-style: none;
            margin: 8px 0;
            padding: 0;
        }}
        .referenced-newsletters li {{
            margin: 6px 0;
            padding-left: 0;
        }}
        .referenced-newsletters a {{
            color: #2563eb;
            text-decoration: none;
        }}
        .referenced-newsletters a:hover {{
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
            <h1>{title}</h1>
            <p class="subtitle">{subtitle}</p>
        </div>

        {content_section}

        <div class="footer">
            <p>
                <a href="{escape(preferences_url)}">Manage your notification preferences</a>
                •
                <a href="{escape(unsubscribe_url)}">Unsubscribe</a>
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
    return "\n".join(f"<p>{escape(p)}</p>" for p in paragraphs)
