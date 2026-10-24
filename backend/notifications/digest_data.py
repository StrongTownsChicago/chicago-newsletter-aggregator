"""Digest data: notification records grouped, fetched and formatted for rendering.

Each function does all data work once, so the renderers only handle presentation.
"""

from datetime import datetime
from typing import Any

from notifications.digest_config import frontend_base_url
from shared.db import get_supabase_client


def prepare_newsletter_data(
    notifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Group notifications by newsletter, collect matching rules, and extract all needed data.

    This does ALL data processing once so formatters only handle presentation:
    each returned dict holds the formatted fields ready for display.
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
                date_obj = datetime.fromisoformat(received_date)
                date_formatted = date_obj.strftime("%B %d, %Y")
            except (ValueError, TypeError):
                date_formatted = received_date[:10]
        else:
            date_formatted = "Unknown date"

        # Build newsletter URL
        newsletter_id = newsletter.get("id", "")
        base_url = frontend_base_url()
        newsletter_url = f"{base_url}/newsletter/{newsletter_id}"

        # Prepare complete newsletter data
        prepared_newsletters.append(
            {
                "title": newsletter.get("subject", "Untitled Newsletter"),
                "source_name": source_name,
                "ward_text": ward_text,
                "date_formatted": date_formatted,
                "summary": newsletter.get("summary", ""),
                "topics": [
                    format_topic_name(topic) for topic in newsletter.get("topics") or []
                ],
                "newsletter_url": newsletter_url,
                "matched_rules": item["matched_rules"],
            }
        )

    return prepared_newsletters


def fetch_newsletter_details(newsletter_ids: list[str]) -> list[dict[str, Any]]:
    """
    Fetch newsletter details for referenced newsletters.

    Args:
        newsletter_ids: List of newsletter UUIDs

    Returns:
        List of dicts with id, subject, received_date, ward_number, sorted by ward
    """
    if not newsletter_ids:
        return []

    supabase = get_supabase_client()

    try:
        response = (
            supabase.table("newsletters")
            .select("id, subject, received_date, source:sources(ward_number)")
            .in_("id", newsletter_ids)
            .execute()
        )

        newsletters = []
        for nl in response.data:
            nl_dict = dict(nl)  # type: ignore[arg-type]
            source_data = nl_dict.get("source")
            ward_number = (
                source_data.get("ward_number")
                if source_data and isinstance(source_data, dict)
                else None
            )

            newsletters.append(
                {
                    "id": str(nl_dict["id"]),
                    "subject": str(nl_dict["subject"]),
                    "received_date": str(nl_dict["received_date"]),
                    "ward_number": ward_number,
                }
            )

        # Sort by ward number (put None/citywide last)
        newsletters.sort(
            key=lambda x: (x["ward_number"] is None, x["ward_number"] or 999)
        )

        return newsletters

    except Exception as e:  # noqa: BLE001  database boundary: log and return no newsletters
        print(f"Warning: Failed to fetch newsletter details: {e}")
        return []


def prepare_weekly_report_data(
    notifications: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Extract and format weekly report data for email rendering.

    Groups notifications by topic; report data must be joined on each record
    as 'report'. Returns dicts with topic, summary, newsletter_count, week_id
    and matched_rules.
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
        week_range = format_week_range(week_id)

        # Map topic to friendly name
        topic_display = format_topic_name(topic)

        # Count newsletters
        newsletter_ids = report.get("newsletter_ids", [])
        newsletter_count = len(newsletter_ids) if newsletter_ids else 0

        # Fetch newsletter details for referenced newsletters
        referenced_newsletters = fetch_newsletter_details(newsletter_ids)

        prepared_reports.append(
            {
                "topic": topic,
                "topic_display": topic_display,
                "summary": report.get("report_summary", ""),
                "newsletter_count": newsletter_count,
                "week_range": week_range,
                "week_id": week_id,
                "matched_rules": item["matched_rules"],
                "referenced_newsletters": referenced_newsletters,
            }
        )

    return prepared_reports


def format_week_range(week_id: str) -> str:
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
        from datetime import date, timedelta

        jan_4 = date(year, 1, 4)  # Always in week 1
        week_1_monday = jan_4 - timedelta(days=jan_4.weekday())
        week_start = week_1_monday + timedelta(weeks=week - 1)
        week_end = week_start + timedelta(days=6)

        # Formats as "January 26 - February 1, 2026"
        if week_start.month == week_end.month:
            return f"{week_start.strftime('%B %d')} - {week_end.strftime('%d, %Y')}"
        return f"{week_start.strftime('%B %d')} - {week_end.strftime('%B %d, %Y')}"

    except (ValueError, AttributeError):
        return week_id


# Display labels for processing/llm_processor.py:TOPICS.
# Must match frontend/src/lib/topics.ts:TOPIC_LABELS so emails and the site agree.
TOPIC_LABELS: dict[str, str] = {
    "4_flats_legalization": "4-flats legalization",
    "missing_middle_housing": "Missing middle housing",
    "accessory_dwelling_units": "Accessory dwelling units (ADUs)",
    "single_stair_reform": "Single-stair reform",
    "bike_lanes": "Bike lanes",
    "street_redesign": "Street redesign",
    "street_safety_or_traffic_calming": "Street safety & traffic calming",
    "transit_funding": "Transit funding",
    "city_budget": "City budget",
    "tax_policy": "Tax policy",
    "zoning_or_development_meeting_or_approval": "Zoning & development approvals",
    "city_charter": "City charter",
}


def format_topic_name(topic: str) -> str:
    """Display label for a topic id, e.g. "bike_lanes" -> "Bike lanes".

    Unknown ids get spaces for underscores and a capitalized first letter.
    """
    if topic in TOPIC_LABELS:
        return TOPIC_LABELS[topic]
    spaced = " ".join(part for part in topic.split("_") if part)
    return spaced[:1].upper() + spaced[1:]
