"""
Weekly topic report generation for Strong Towns Chicago.

Two-phase LLM processing:
1. Extract structured facts from newsletters about a topic
2. Synthesize facts into narrative weekly summary with Strong Towns perspective

Designed to aggregate newsletter content by topic and generate insight-driven summaries.
"""

from datetime import UTC, datetime
from typing import Any

from models.types import NewsletterID
from models.weekly_report import (
    FactExtraction,
    KeyDevelopment,
    WeeklySynthesis,
    WeeklyTopicReport,
)
from processing.llm_processor import TOPICS, call_llm
from prompts.weekly_synthesis import FACTUAL_SUMMARY
from shared.db import get_supabase_client


def extract_facts_from_single_newsletter(
    topic: str, newsletter: dict[str, Any], model: str = "gpt-oss:20b"
) -> list[KeyDevelopment]:
    """
    Phase 1a: Extract structured facts from a single newsletter about a topic.

    Facts are key decisions or announcements, development approvals or zoning
    changes, policy changes or ordinances, and community meetings or hearings.
    newsletter needs id, subject, plain_text, source_name and ward_number.
    """
    ward_info = (
        f"Ward {newsletter.get('ward_number', 'Unknown')}"
        if newsletter.get("ward_number")
        else "Citywide"
    )
    source_info = newsletter.get("source_name", "Unknown Source")
    newsletter_id = newsletter.get("id", "")
    ward_number = newsletter.get("ward_number")

    # Build content for single newsletter
    content = f"""Source: {source_info} ({ward_info})
Subject: {newsletter["subject"]}

{newsletter["plain_text"]}
"""

    prompt = f"""Extract key developments from this Chicago alderman newsletter about {topic}.

You are analyzing newsletters for Strong Towns Chicago, an advocacy organization focused on:
- Safe streets (protected bike lanes, traffic calming, pedestrian safety)
- More housing (4-flats, missing middle, ADUs, zoning reform)
- Public transit (CTA/Metra funding, service improvements, transit-oriented development)
- Fiscal responsibility (transparent budgets, evidence-based policy)

For each development, provide:
- Concrete, specific description (what happened, where, when)

ONLY extract developments that are:
✓ Specific and factual (include locations, dates, numbers)
✓ Action-oriented (decisions, approvals, announcements, meetings)
✓ Relevant to Strong Towns priorities above

DO NOT extract:
✗ Vague mentions without specifics
✗ Routine announcements (office hours, holiday schedules)
✗ Speculation or predictions

If no meaningful developments, return empty list.

Available topics: {", ".join(TOPICS)}

Newsletter:
{content}
"""

    try:
        response = call_llm(model, prompt, FactExtraction.model_json_schema())
        data = FactExtraction.model_validate_json(response)

        # The LLM returns only descriptions; the newsletter's id and ward are
        # known deterministically from the source, so attach them here.
        wards = [str(ward_number)] if ward_number else []
        return [
            KeyDevelopment(
                description=description,
                newsletter_ids=[NewsletterID(newsletter_id)],
                wards=wards,
            )
            for description in data.developments
        ]

    except Exception as e:  # noqa: BLE001  per-newsletter LLM boundary: log and continue
        print(f"    ⚠ Extraction failed for newsletter {newsletter_id[:8]}: {e}")
        return []


def extract_facts_from_newsletters(
    topic: str, newsletters: list[dict[str, Any]], model: str = "gpt-oss:20b"
) -> list[KeyDevelopment]:
    """
    Phase 1b: Extract and aggregate facts from multiple newsletters.

    Processes each newsletter individually to avoid context limit issues,
    then aggregates all extracted facts.
    """
    if not newsletters:
        print(f"  ℹ No newsletters for {topic}, skipping fact extraction")
        return []

    print(f"  → Extracting facts for {topic} from {len(newsletters)} newsletters...")

    all_developments = []

    # Process each newsletter individually
    for i, newsletter in enumerate(newsletters, 1):
        print(f"    Processing newsletter {i}/{len(newsletters)}...", end=" ")
        developments = extract_facts_from_single_newsletter(topic, newsletter, model)
        all_developments.extend(developments)
        print(f"✓ {len(developments)} developments")

    print(f"  ✓ Extracted {len(all_developments)} total developments")
    return all_developments


def synthesize_weekly_summary(
    topic: str,
    facts: list[KeyDevelopment],
    week_id: str,
    model: str = "gpt-oss:20b",
) -> str:
    """
    Phase 2: Synthesize Phase 1 facts into a 2-4 paragraph weekly summary.

    The summary identifies trends across wards, highlights the most significant
    developments and citywide implications, gives context on the topic's
    activity level, and applies a Strong Towns perspective (safe streets, more
    housing, transit, fiscal responsibility). week_id is YYYY-WXX.
    """
    if not facts:
        print(f"  ℹ No facts to synthesize for {topic}")
        return ""

    # Format facts for prompt
    facts_text = []
    for i, fact in enumerate(facts, 1):
        ward_str = f"Wards {', '.join(fact.wards)}" if fact.wards else "Citywide"
        facts_text.append(f"{i}. {fact.description} ({ward_str})")

    facts_list = "\n".join(facts_text)

    # Map topic to friendly name for summary
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
    topic_display = topic_names.get(topic, topic.replace("_", " ").title())

    prompt = FACTUAL_SUMMARY.format(
        topic_display=topic_display, week_id=week_id, facts_list=facts_list
    )

    try:
        print(f"  → Synthesizing summary for {topic}...")
        response = call_llm(model, prompt, WeeklySynthesis.model_json_schema())
        data = WeeklySynthesis.model_validate_json(response)

        print(f"  ✓ Generated summary ({len(data.summary)} chars)")
        return data.summary

    except Exception as e:  # noqa: BLE001  LLM boundary: a failed call yields no summary
        print(f"  ✗ Summary synthesis failed for {topic}: {e}")
        return ""


def generate_weekly_topic_report(
    topic: str, week_id: str, model: str = "gpt-oss:20b"
) -> WeeklyTopicReport | None:
    """
    Complete pipeline: fetch newsletters, extract facts, synthesize summary.

    Queries newsletters tagged with topic in week_id (YYYY-WXX), extracts facts
    (Phase 1) and synthesizes the summary (Phase 2). Returns None if no
    newsletters are found or processing fails.
    """
    if not _is_valid_report_request(topic, week_id):
        return None

    # Query newsletters for this topic and week
    print(f"\n=== Generating report for {topic} (week {week_id}) ===")

    supabase = get_supabase_client()
    week_range = _fetch_week_range(supabase, week_id)
    if week_range is None:
        return None

    try:
        newsletters = _fetch_topic_newsletters(supabase, topic, *week_range)

        if not newsletters:
            print(f"  ℹ No newsletters found for {topic} in week {week_id}")
            return None

        print(f"  ✓ Found {len(newsletters)} newsletters")
        return _build_report(topic, week_id, newsletters, model)

    except Exception as e:  # noqa: BLE001  per-report boundary: log and skip the report
        print(f"  ✗ Report generation failed: {e}")
        return None


def _is_valid_report_request(topic: str, week_id: str) -> bool:
    """Check the topic is known and week_id looks like YYYY-WXX, before any RPC call."""
    if topic not in TOPICS:
        print(f"  ✗ Invalid topic: {topic}")
        return False

    try:
        year_str, week_str = week_id.split("-W")
        int(year_str)
        int(week_str)
    except ValueError:
        print(f"  ✗ Invalid week_id format: {week_id} (expected YYYY-WXX)")
        return False
    return True


def _fetch_week_range(supabase: Any, week_id: str) -> tuple[str, str] | None:
    """The week's first and last dates from the get_week_date_range function, or None."""
    try:
        week_range_result = supabase.rpc(
            "get_week_date_range", {"week_id_param": week_id}
        ).execute()

        if not week_range_result.data:
            print(f"  ✗ Invalid week_id: {week_id}")
            return None

        week_range = dict(week_range_result.data[0])
        week_start = str(week_range["week_start"])
        week_end = str(week_range["week_end"])
        print(f"  → Querying newsletters from {week_start} to {week_end}...")
        return week_start, week_end

    except Exception as e:  # noqa: BLE001  database boundary: log and skip the report
        print(f"  ✗ Failed to calculate week range: {e}")
        return None


def _fetch_topic_newsletters(
    supabase: Any, topic: str, week_start: str, week_end: str
) -> list[dict[str, Any]]:
    """Newsletters tagged with the topic and received in the week (filtered in PostgreSQL)."""
    response = (
        supabase.table("newsletters")
        .select(
            "id, subject, plain_text, received_date, source:sources(name, ward_number)"
        )
        .filter("topics", "cs", f"{{{topic}}}")  # Contains topic
        .gte("received_date", week_start)
        .lte("received_date", week_end)
        .execute()
    )
    return [_newsletter_from_row(dict(row)) for row in response.data]


def _newsletter_from_row(row: dict[str, Any]) -> dict[str, Any]:
    source = row.get("source")
    source = source if isinstance(source, dict) else {}
    return {
        "id": str(row["id"]),
        "subject": str(row["subject"]),
        "plain_text": str(row["plain_text"] or ""),
        "received_date": str(row["received_date"]),
        "source_name": str(source["name"]) if source else "Unknown",
        "ward_number": str(source["ward_number"])
        if source.get("ward_number")
        else None,
    }


def _build_report(
    topic: str, week_id: str, newsletters: list[dict[str, Any]], model: str
) -> WeeklyTopicReport | None:
    """Extract facts (Phase 1) and synthesize the summary (Phase 2); None if either is empty."""
    facts = extract_facts_from_newsletters(topic, newsletters, model)

    if not facts:
        print("  ℹ No developments extracted, skipping report generation")
        return None

    summary = synthesize_weekly_summary(topic, facts, week_id, model)

    if not summary:
        print("  ℹ No summary generated, skipping report creation")
        return None

    report = WeeklyTopicReport(
        id="",  # Will be generated by database
        topic=topic,
        week_id=week_id,
        report_summary=summary,
        newsletter_ids=[NewsletterID(nl["id"]) for nl in newsletters if nl.get("id")],
        key_developments=facts,
        created_at=datetime.now(UTC),
    )

    print("  ✓ Report generated successfully")
    return report
