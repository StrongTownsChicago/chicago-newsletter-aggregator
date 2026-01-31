"""
Weekly topic report generation for Strong Towns Chicago.

Two-phase LLM processing:
1. Extract structured facts from newsletters about a topic
2. Synthesize facts into narrative weekly summary with Strong Towns perspective

Designed to aggregate newsletter content by topic and generate insight-driven summaries.
"""

from typing import Any
from datetime import datetime

from models.weekly_report import (
    FactExtraction,
    KeyDevelopment,
    WeeklySynthesis,
    WeeklyTopicReport,
)
from models.types import NewsletterID
from processing.llm_processor import TOPICS, call_llm
from prompts.weekly_synthesis import FACTUAL_SUMMARY
from shared.db import get_supabase_client


def extract_facts_from_single_newsletter(
    topic: str, newsletter: dict[str, Any], model: str = "gpt-oss:20b"
) -> list[KeyDevelopment]:
    """
    Phase 1a: Extract structured facts from a single newsletter about a topic.

    Analyzes one newsletter and extracts:
    - Key decisions or announcements
    - Development approvals or zoning changes
    - Policy changes or ordinances
    - Community meetings or hearings

    Args:
        topic: Topic identifier (from TOPICS constant)
        newsletter: Newsletter dict with id, subject, plain_text, source_name, ward_number
        model: Ollama model name

    Returns:
        List of KeyDevelopment objects with structured facts from this newsletter
    """
    ward_info = (
        f"Ward {newsletter.get('ward_number', 'Unknown')}"
        if newsletter.get("ward_number")
        else "Citywide"
    )
    source_info = newsletter.get("source_name", "Unknown Source")
    newsletter_id = newsletter.get("id", "")

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
- Ward number involved (if mentioned)

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

        # Add newsletter_id to each development
        for dev in data.developments:
            dev.newsletter_ids = [NewsletterID(newsletter_id)]

        return data.developments

    except Exception as e:
        print(f"    ⚠ Extraction failed for newsletter {newsletter_id[:8]}: {e}")
        return []


def extract_facts_from_newsletters(
    topic: str, newsletters: list[dict[str, Any]], model: str = "gpt-oss:20b"
) -> list[KeyDevelopment]:
    """
    Phase 1b: Extract and aggregate facts from multiple newsletters.

    Processes each newsletter individually to avoid context limit issues,
    then aggregates all extracted facts.

    Args:
        topic: Topic identifier (from TOPICS constant)
        newsletters: List of newsletter dicts with id, subject, plain_text, source, ward
        model: Ollama model name

    Returns:
        Aggregated list of KeyDevelopment objects from all newsletters
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
    Phase 2: Synthesize facts into narrative weekly summary.

    Takes structured facts and creates a 2-4 paragraph summary that:
    - Identifies trends or patterns across wards
    - Highlights most significant developments
    - Notes any citywide implications
    - Provides context on topic-specific activity level
    - Applies Strong Towns perspective (safe streets, more housing, transit, fiscal responsibility)

    Args:
        topic: Topic identifier (from TOPICS constant)
        facts: Extracted KeyDevelopment objects from Phase 1
        week_id: Week identifier (YYYY-WXX)
        model: Ollama model name

    Returns:
        Weekly summary text (2-4 paragraphs)
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

    except Exception as e:
        print(f"  ✗ Summary synthesis failed for {topic}: {e}")
        return ""


def generate_weekly_topic_report(
    topic: str, week_id: str, model: str = "gpt-oss:20b"
) -> WeeklyTopicReport | None:
    """
    Complete pipeline: Fetch newsletters, extract facts, synthesize summary.

    Orchestrates the full two-phase process:
    1. Query newsletters tagged with topic from specified week
    2. Extract structured facts via LLM (Phase 1)
    3. Synthesize narrative summary via LLM (Phase 2)
    4. Return complete WeeklyTopicReport object

    Returns None if no newsletters found for topic/week or if processing fails.

    Args:
        topic: Topic identifier (from TOPICS constant)
        week_id: Week identifier (YYYY-WXX)
        model: Ollama model name

    Returns:
        WeeklyTopicReport object or None if no content or processing failed
    """
    # Validate topic
    if topic not in TOPICS:
        print(f"  ✗ Invalid topic: {topic}")
        return None

    # Parse week_id to get date range
    try:
        year_str, week_str = week_id.split("-W")
        year = int(year_str)
        week = int(week_str)
    except ValueError:
        print(f"  ✗ Invalid week_id format: {week_id} (expected YYYY-WXX)")
        return None

    # Query newsletters for this topic and week
    print(f"\n=== Generating report for {topic} (week {week_id}) ===")

    supabase = get_supabase_client()

    try:
        # Use PostgreSQL's ISO week functions to filter by week
        response = (
            supabase.table("newsletters")
            .select(
                "id, subject, plain_text, received_date, source:sources(name, ward_number)"
            )
            .filter("topics", "cs", f"{{{topic}}}")  # Contains topic
            .execute()
        )

        # Filter results to only include newsletters from the target week
        # (Supabase PostgREST doesn't support EXTRACT directly, so we filter in Python)
        newsletters = []
        for nl_data in response.data:
            # Type assertions for Supabase response
            nl_dict = dict(nl_data)  # type: ignore
            received_date = datetime.fromisoformat(
                str(nl_dict["received_date"]).replace("Z", "+00:00")
            )
            nl_year, nl_week, _ = received_date.isocalendar()
            if nl_year == year and nl_week == week:
                # Flatten source data
                source_data = nl_dict.get("source")
                newsletter = {
                    "id": str(nl_dict["id"]),
                    "subject": str(nl_dict["subject"]),
                    "plain_text": str(nl_dict["plain_text"] or ""),
                    "received_date": str(nl_dict["received_date"]),
                    "source_name": str(source_data["name"])
                    if source_data and isinstance(source_data, dict)
                    else "Unknown",
                    "ward_number": str(source_data["ward_number"])
                    if source_data
                    and isinstance(source_data, dict)
                    and source_data.get("ward_number")
                    else None,
                }
                newsletters.append(newsletter)

        if not newsletters:
            print(f"  ℹ No newsletters found for {topic} in week {week_id}")
            return None

        print(f"  ✓ Found {len(newsletters)} newsletters")

        # Phase 1: Extract facts (per-newsletter, then aggregate)
        facts = extract_facts_from_newsletters(topic, newsletters, model)

        if not facts:
            print("  ℹ No developments extracted, skipping report generation")
            return None

        # Phase 2: Synthesize summary
        summary = synthesize_weekly_summary(topic, facts, week_id, model)

        if not summary:
            print("  ℹ No summary generated, skipping report creation")
            return None

        # Build report object
        newsletter_ids: list[NewsletterID] = []
        for nl in newsletters:
            nl_id = nl.get("id")
            if nl_id:
                newsletter_ids.append(NewsletterID(nl_id))
        report = WeeklyTopicReport(
            id="",  # Will be generated by database
            topic=topic,
            week_id=week_id,
            report_summary=summary,
            newsletter_ids=newsletter_ids,
            key_developments=facts,
            created_at=datetime.now(),
        )

        print("  ✓ Report generated successfully")
        return report

    except Exception as e:
        print(f"  ✗ Report generation failed: {e}")
        return None
