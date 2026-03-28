"""
Test and iterate on weekly summary generation.

Allows you to quickly test the summary prompt against real or sample data
without running the full weekly report pipeline.

Usage:
    # Test with an existing report from database
    uv run python -m utils.test_weekly_summary --topic bike_lanes --week 2026-W04

    # Test with sample data (no database query)
    uv run python -m utils.test_weekly_summary --sample
"""

import argparse
import os
from dotenv import load_dotenv

from models.types import NewsletterID
from models.weekly_report import KeyDevelopment, WeeklySynthesis
from processing.llm_processor import call_llm
from prompts.weekly_synthesis import FACTUAL_SUMMARY
from shared.db import get_supabase_client

load_dotenv()

ENABLE_LLM = os.getenv("ENABLE_LLM", "false").lower() == "true"


def get_sample_facts() -> list[KeyDevelopment]:
    """Get sample facts for testing without database access."""
    return [
        KeyDevelopment(
            description="Concrete bike medians completed along Pratt Boulevard; remaining tasks include installing signage and modifying striping.",
            wards=["40"],
            newsletter_ids=[NewsletterID("98d9f7a0-8d3a-43ce-ac09-c31e4287bd6e")],
        ),
        KeyDevelopment(
            description="CDOT temporarily closed the northern turning lane from Ainslie to Western heading south on Lincoln Avenue to install new traffic lights and adjust signal timing for improved bike lane alignment.",
            wards=["40"],
            newsletter_ids=[NewsletterID("98d9f7a0-8d3a-43ce-ac09-c31e4287bd6e")],
        ),
        KeyDevelopment(
            description='The City of Chicago\'s Department of Finance announced a new reporting option for parking violations, adding "Vehicle Parked in Bike Lane" as a reportable offense. Residents can file these reports via 311, the CHI311 app, or the 311 website.',
            wards=["43"],
            newsletter_ids=[NewsletterID("f32c50a1-3402-4cfe-9f26-739d83942885")],
        ),
        KeyDevelopment(
            description="The City of Chicago updated guidance and rules from CDOT on scooter and e-bike rides, providing new rules that may affect interactions with bike lanes.",
            wards=["43"],
            newsletter_ids=[NewsletterID("f32c50a1-3402-4cfe-9f26-739d83942885")],
        ),
        KeyDevelopment(
            description="CDOT installed new bike racks on the 5600 block of North Kenmore, providing additional bike parking for residents and commuters in the 48th Ward.",
            wards=["48"],
            newsletter_ids=[NewsletterID("976ac29c-ac71-4b8b-8965-f7b80e4be47d")],
        ),
        KeyDevelopment(
            description="CDOT launched the Bike Chicago program, offering 5,000 free bicycles with safety and maintenance equipment to age- and income-eligible Chicagoans.",
            wards=["48"],
            newsletter_ids=[NewsletterID("976ac29c-ac71-4b8b-8965-f7b80e4be47d")],
        ),
    ]


def fetch_report_facts(
    topic: str, week_id: str
) -> tuple[list[KeyDevelopment], str] | None:
    """
    Fetch existing report facts from database.

    Returns:
        Tuple of (facts, topic_display_name) or None if not found
    """
    supabase = get_supabase_client()

    try:
        response = (
            supabase.table("weekly_topic_reports")
            .select("topic, key_developments")
            .eq("topic", topic)
            .eq("week_id", week_id)
            .single()
            .execute()
        )

        if not response.data:
            print(f"✗ No report found for {topic} / {week_id}")
            return None

        data = response.data
        raw_developments = data.get("key_developments", [])  # type: ignore

        # Convert raw dicts to KeyDevelopment objects
        facts = [KeyDevelopment(**dev) for dev in raw_developments]  # type: ignore

        # Get friendly topic name
        topic_names = {
            "bike_lanes": "Bike Lanes and Cycling Infrastructure",
            "4_flats_legalization": "4-Flats and Small-Scale Housing",
            "missing_middle_housing": "Missing Middle Housing",
            "accessory_dwelling_units": "Accessory Dwelling Units (ADUs)",
            "single_stair_reform": "Single-Stair Building Reform",
            "street_redesign": "Street Redesign and Reconstruction",
            "street_safety_or_traffic_calming": "Street Safety and Traffic Calming",
            "transit_funding": "Public Transit Funding and Service",
            "city_budget": "City Budget and Fiscal Policy",
            "tax_policy": "Tax Policy and Revenue",
            "zoning_or_development_meeting_or_approval": "Zoning and Development Approvals",
            "city_charter": "City Charter and Governance Reform",
        }
        topic_display = topic_names.get(topic, topic.replace("_", " ").title())

        return (facts, topic_display)

    except Exception as e:
        print(f"✗ Error fetching report: {e}")
        return None


def synthesize_summary(
    facts: list[KeyDevelopment],
    topic_display: str,
    week_id: str,
    model: str = "gpt-oss:20b",
) -> str:
    """
    Generate summary using the FACTUAL_SUMMARY prompt.

    Args:
        facts: List of KeyDevelopment objects
        topic_display: Human-readable topic name
        week_id: Week identifier (YYYY-WXX)
        model: Ollama model name

    Returns:
        Generated summary text or error message
    """
    # Format facts for prompt
    facts_text = []
    for i, fact in enumerate(facts, 1):
        ward_str = f"Wards {', '.join(fact.wards)}" if fact.wards else "Citywide"
        facts_text.append(f"{i}. {fact.description} ({ward_str})")

    facts_list = "\n".join(facts_text)

    # Build prompt using FACTUAL_SUMMARY template
    prompt = FACTUAL_SUMMARY.format(
        topic_display=topic_display, week_id=week_id, facts_list=facts_list
    )

    # Call LLM
    try:
        print("\nGenerating summary...")
        response = call_llm(model, prompt, WeeklySynthesis.model_json_schema())
        data = WeeklySynthesis.model_validate_json(response)
        return data.summary
    except Exception as e:
        return f"ERROR: {e}"


def main() -> None:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Test weekly summary generation")

    parser.add_argument(
        "--topic",
        type=str,
        help="Topic to test (e.g., bike_lanes)",
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
        "--model",
        type=str,
        default=os.getenv("LLM_MODEL", os.getenv("OLLAMA_MODEL", "gpt-oss:20b")),
        help="LLM model to use, with optional provider prefix (e.g., openai:gpt-5, ollama:gpt-oss:20b). Default: from LLM_MODEL or OLLAMA_MODEL env var",
    )

    args = parser.parse_args()

    if not ENABLE_LLM:
        print("✗ ENABLE_LLM is false. Set ENABLE_LLM=true in .env to test.")
        exit(1)

    # Get facts and topic display
    if args.sample:
        facts = get_sample_facts()
        topic_display = "Bike Lanes and Cycling Infrastructure"
        week_id = "2026-W04"
        print("Using sample data for testing...")
    else:
        if not args.topic or not args.week:
            print("✗ Error: --topic and --week required unless using --sample")
            parser.print_help()
            exit(1)

        result = fetch_report_facts(args.topic, args.week)
        if not result:
            exit(1)

        facts, topic_display = result
        week_id = args.week
        print(f"✓ Loaded {len(facts)} facts from database")

    print(f"\nTopic: {topic_display}")
    print(f"Week: {week_id}")
    print(f"Facts: {len(facts)}")
    print()

    # Print facts for reference
    print("FACTS BEING SYNTHESIZED:")
    print("-" * 80)
    for i, fact in enumerate(facts, 1):
        ward_str = f"Wards {', '.join(fact.wards)}" if fact.wards else "Citywide"
        print(f"{i}. {fact.description} ({ward_str})")
    print()

    # Generate summary
    summary = synthesize_summary(facts, topic_display, week_id, args.model)

    # Display result
    print("\n" + "=" * 80)
    print("GENERATED SUMMARY:")
    print("-" * 80)
    print(summary)
    print()
    print(f"Character count: {len(summary)}")
    print(f"Word count: {len(summary.split())}")
    print("=" * 80)


if __name__ == "__main__":
    main()
