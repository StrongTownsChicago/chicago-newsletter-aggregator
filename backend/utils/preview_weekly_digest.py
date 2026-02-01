"""
Preview weekly digest email output.

Generates complete HTML and plain text email previews for a weekly digest
to validate formatting and content before sending.

Usage:
    # Preview with real data from database
    uv run python -m utils.preview_weekly_digest --topic bike_lanes --week 2026-W04

    # Preview with sample data
    uv run python -m utils.preview_weekly_digest --sample

    # Save output to files
    uv run python -m utils.preview_weekly_digest --topic bike_lanes --week 2026-W04 --save
"""

import argparse
from typing import Any

from notifications.email_sender import (
    DigestType,
    _build_digest_html,
    _build_digest_text,
    _fetch_newsletter_details,
    _format_topic_name,
    _format_week_range,
)
from shared.db import get_supabase_client


def fetch_weekly_report(topic: str, week_id: str) -> dict[str, Any] | None:
    """
    Fetch a weekly report from the database.

    Args:
        topic: Topic identifier (e.g., "bike_lanes")
        week_id: Week identifier (YYYY-WXX)

    Returns:
        Report dict or None if not found
    """
    supabase = get_supabase_client()

    try:
        response = (
            supabase.table("weekly_topic_reports")
            .select("*")
            .eq("topic", topic)
            .eq("week_id", week_id)
            .single()
            .execute()
        )

        if not response.data:
            print(f"✗ No report found for {topic} / {week_id}")
            return None

        return dict(response.data)  # type: ignore

    except Exception as e:
        print(f"✗ Error fetching report: {e}")
        return None


def get_sample_report() -> dict[str, Any]:
    """Get sample report data for testing."""
    return {
        "topic": "bike_lanes",
        "week_id": "2026-W04",
        "report_summary": """In the 40th Ward, concrete bike medians were completed along Pratt Boulevard, with signage installation and striping modifications pending. CDOT also temporarily closed the northern turning lane on Lincoln Avenue between Ainslie and Western to install new traffic lights and adjust signal timing for improved bike lane alignment.

The 43rd Ward introduced new enforcement tools, with the Department of Finance adding "Vehicle Parked in Bike Lane" as a reportable offense through 311, the CHI311 app, and the 311 website. CDOT also updated guidance on scooter and e-bike use, clarifying how these modes interact with bike lanes.

In the 48th Ward, CDOT installed new bike racks on the 5600 block of North Kenmore and launched the Bike Chicago program, offering 5,000 free bicycles with safety and maintenance equipment to eligible Chicagoans.""",
        "newsletter_ids": [
            "98d9f7a0-8d3a-43ce-ac09-c31e4287bd6e",
            "f32c50a1-3402-4cfe-9f26-739d83942885",
            "976ac29c-ac71-4b8b-8965-f7b80e4be47d",
        ],
    }


def get_sample_newsletters() -> list[dict[str, Any]]:
    """Get sample newsletter data for testing."""
    return [
        {
            "id": "98d9f7a0-8d3a-43ce-ac09-c31e4287bd6e",
            "subject": "Pratt Boulevard Bike Lane Updates",
            "received_date": "2026-01-20T12:00:00Z",
            "ward_number": 40,
        },
        {
            "id": "f32c50a1-3402-4cfe-9f26-739d83942885",
            "subject": "New Bike Lane Parking Enforcement Tools",
            "received_date": "2026-01-22T14:30:00Z",
            "ward_number": 43,
        },
        {
            "id": "976ac29c-ac71-4b8b-8965-f7b80e4be47d",
            "subject": "Bike Infrastructure and Access Improvements",
            "received_date": "2026-01-24T10:15:00Z",
            "ward_number": 48,
        },
    ]


def prepare_report_for_preview(
    report: dict[str, Any], use_sample_newsletters: bool = False
) -> list[dict[str, Any]]:
    """
    Prepare report data in the format expected by email templates.

    Args:
        report: Report dict from database or sample
        use_sample_newsletters: If True, use sample newsletter data instead of fetching

    Returns:
        List containing single prepared report dict
    """
    topic = report["topic"]
    week_id = report["week_id"]
    newsletter_ids = report.get("newsletter_ids", [])

    # Fetch or use sample newsletter details
    if use_sample_newsletters:
        referenced_newsletters = get_sample_newsletters()
    else:
        referenced_newsletters = _fetch_newsletter_details(newsletter_ids)

    # Format data
    topic_display = _format_topic_name(topic)
    week_range = _format_week_range(week_id)
    newsletter_count = len(newsletter_ids)

    return [
        {
            "topic": topic,
            "topic_display": topic_display,
            "summary": report.get("report_summary", ""),
            "newsletter_count": newsletter_count,
            "week_range": week_range,
            "week_id": week_id,
            "matched_rules": ["Test Rule"],  # Sample rule for preview
            "referenced_newsletters": referenced_newsletters,
        }
    ]


def preview_digest(
    prepared_reports: list[dict[str, Any]], save_files: bool = False
) -> None:
    """
    Generate and display/save email preview.

    Args:
        prepared_reports: List of prepared report dicts
        save_files: If True, save HTML and text to files
    """
    # Sample URLs
    preferences_url = "https://example.com/preferences"
    unsubscribe_url = "https://example.com/unsubscribe?token=xxx"

    # Generate HTML and text
    html_output = _build_digest_html(
        prepared_reports, DigestType.WEEKLY, preferences_url, unsubscribe_url
    )
    text_output = _build_digest_text(
        prepared_reports, DigestType.WEEKLY, preferences_url, unsubscribe_url
    )

    if save_files:
        # Save to files
        html_file = "weekly_digest_preview.html"
        text_file = "weekly_digest_preview.txt"

        with open(html_file, "w", encoding="utf-8") as f:
            f.write(html_output)

        with open(text_file, "w", encoding="utf-8") as f:
            f.write(text_output)

        print(f"\nSaved HTML preview to: {html_file}")
        print(f"Saved text preview to: {text_file}")
        print(f"\nOpen {html_file} in a browser to view the formatted email.")

    else:
        # Print to console
        print("\n" + "=" * 80)
        print("HTML EMAIL PREVIEW")
        print("=" * 80)
        print(html_output)

        print("\n" + "=" * 80)
        print("PLAIN TEXT EMAIL PREVIEW")
        print("=" * 80)
        print(text_output)

    # Print stats
    print("\n" + "=" * 80)
    print("STATS")
    print("=" * 80)
    print(f"HTML length: {len(html_output)} characters")
    print(f"Text length: {len(text_output)} characters")
    print(f"Reports: {len(prepared_reports)}")
    if prepared_reports:
        print(
            f"Referenced newsletters: {len(prepared_reports[0].get('referenced_newsletters', []))}"
        )


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Preview weekly digest email output")

    parser.add_argument(
        "--topic",
        type=str,
        help="Topic to preview (e.g., bike_lanes)",
    )

    parser.add_argument(
        "--week",
        type=str,
        help="Week ID (YYYY-WXX format)",
    )

    parser.add_argument(
        "--sample",
        action="store_true",
        help="Use sample data instead of fetching from database",
    )

    parser.add_argument(
        "--save",
        action="store_true",
        help="Save output to HTML and text files instead of printing to console",
    )

    args = parser.parse_args()

    # Get report data
    if args.sample:
        print("Using sample data for preview...")
        report = get_sample_report()
        prepared_reports = prepare_report_for_preview(
            report, use_sample_newsletters=True
        )
    else:
        if not args.topic or not args.week:
            print("✗ Error: --topic and --week required unless using --sample")
            parser.print_help()
            exit(1)

        print(f"Fetching report for {args.topic} / {args.week}...")
        fetched_report = fetch_weekly_report(args.topic, args.week)
        if not fetched_report:
            exit(1)

        print("✓ Report found, preparing preview...")
        prepared_reports = prepare_report_for_preview(
            fetched_report, use_sample_newsletters=False
        )

    # Generate preview
    preview_digest(prepared_reports, save_files=args.save)


if __name__ == "__main__":
    main()
