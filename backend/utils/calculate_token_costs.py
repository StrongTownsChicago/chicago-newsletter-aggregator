"""
CLI utility for calculating LLM token costs.

Analyzes newsletter processing costs for different LLM models without making actual API calls.
Simulates prompts and counts tokens to estimate costs across providers.

Usage:
    # Analyze latest 10 newsletters with GPT-5 pricing
    uv run python -m utils.calculate_token_costs --latest 10 --model gpt-5

    # Include weekly report synthesis costs
    uv run python -m utils.calculate_token_costs --latest 10 --model gpt-5 --include-weekly

    # Compare multiple models
    uv run python -m utils.calculate_token_costs --latest 10 --models gpt-5,claude-sonnet-4.5,gemini-2.5-pro

    # List available models
    uv run python -m utils.calculate_token_costs --list-models

    # Output to JSON/CSV
    uv run python -m utils.calculate_token_costs --latest 10 --model gpt-5 --output-json costs.json
"""

import argparse
import sys
from typing import Any
from datetime import datetime
from collections import defaultdict

from shared.db import get_supabase_client
from utils.cost_calculator import PricingData
from utils.newsletter_token_analyzer import (
    analyze_newsletter_tokens,
    analyze_weekly_report_tokens,
)
from utils.cost_report_generator import (
    generate_text_report,
    generate_json_report,
    generate_csv_report,
    generate_comparison_report,
    generate_combined_text_report,
)


def fetch_newsletters(
    latest: int | None = None,
    newsletter_id: str | None = None,
    source_id: int | None = None,
) -> list[dict[str, Any]]:
    """
    Fetch newsletters from database based on filters.

    Args:
        latest: Number of most recent newsletters to fetch
        newsletter_id: Specific newsletter ID
        source_id: Filter by source ID

    Returns:
        List of newsletter dicts with id, subject, plain_text, topics, source info
    """
    supabase = get_supabase_client()

    # Fetch newsletters with source join for ward/name info (needed for weekly reports)
    query = supabase.table("newsletters").select(
        """
        id,
        subject,
        plain_text,
        received_date,
        topics,
        sources!inner(
            name,
            ward_number
        )
        """
    )

    if newsletter_id:
        query = query.eq("id", newsletter_id)
    elif source_id:
        query = query.eq("source_id", source_id)

    # Order by received_date descending to get latest first
    query = query.order("received_date", desc=True)

    if latest:
        query = query.limit(latest)

    response = query.execute()

    if not response.data:
        print("No newsletters found matching criteria.")
        return []

    # Flatten source data into newsletter dict
    newsletters = []
    for nl in response.data:
        # Type cast: we know nl is a dict-like object from Supabase
        if not isinstance(nl, dict):
            continue
        nl_dict: dict[str, Any] = dict(nl)
        if "sources" in nl_dict and nl_dict["sources"]:
            source = nl_dict["sources"]
            # Type narrow: source should be a dict from the join
            if isinstance(source, dict):
                nl_dict["source_name"] = source.get("name", "Unknown")
                nl_dict["ward_number"] = source.get("ward_number")
            del nl_dict["sources"]
        newsletters.append(nl_dict)

    print(f"Fetched {len(newsletters)} newsletters for analysis")
    return newsletters


def get_iso_week_id(date_str: str) -> str:
    """
    Convert date string to ISO week ID (YYYY-WXX).

    Args:
        date_str: ISO format date string (YYYY-MM-DD)

    Returns:
        Week ID string (e.g., "2026-W05")
    """
    date = datetime.fromisoformat(date_str.replace("Z", "+00:00"))
    year, week, _ = date.isocalendar()
    return f"{year}-W{week:02d}"


def group_newsletters_by_week(
    newsletters: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """
    Group newsletters by ISO week.

    Args:
        newsletters: List of newsletter dicts with received_date

    Returns:
        Dict mapping week_id to list of newsletters
    """
    weeks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for nl in newsletters:
        if nl.get("received_date"):
            week_id = get_iso_week_id(nl["received_date"])
            weeks[week_id].append(nl)
    return dict(weeks)


def get_topics_from_newsletters(
    newsletters: list[dict[str, Any]],
) -> set[str]:
    """
    Extract all unique topics from a list of newsletters.

    Args:
        newsletters: List of newsletter dicts with topics field

    Returns:
        Set of unique topic strings
    """
    all_topics = set()
    for nl in newsletters:
        topics = nl.get("topics")
        if isinstance(topics, list):
            all_topics.update(topics)
    return all_topics


def main() -> None:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Calculate LLM token costs for newsletter processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --latest 10 --model gpt-5
  %(prog)s --latest 10 --model gpt-5 --include-weekly
  %(prog)s --latest 10 --models gpt-5,claude-sonnet-4.5,gemini-2.5-pro
  %(prog)s --newsletter-id abc123 --model gpt-5
  %(prog)s --source-id 1 --latest 5 --model gpt-5
  %(prog)s --list-models
  %(prog)s --latest 10 --model gpt-5 --output-json costs.json
        """,
    )

    # Newsletter selection arguments
    selection_group = parser.add_argument_group("newsletter selection")
    selection_group.add_argument(
        "--latest", type=int, help="Analyze N most recent newsletters"
    )
    selection_group.add_argument(
        "--newsletter-id", help="Analyze specific newsletter by ID"
    )
    selection_group.add_argument(
        "--source-id", type=int, help="Filter newsletters by source ID"
    )

    # Model selection arguments
    model_group = parser.add_argument_group("model selection")
    model_group.add_argument(
        "--model",
        help="Model to calculate costs for (default: gpt-5)",
        default="gpt-5",
    )
    model_group.add_argument(
        "--models", help="Comma-separated list of models to compare"
    )
    model_group.add_argument(
        "--list-models",
        action="store_true",
        help="List available models and exit",
    )

    # Output arguments
    output_group = parser.add_argument_group("output options")
    output_group.add_argument("--output-json", help="Save JSON report to file")
    output_group.add_argument("--output-csv", help="Save CSV report to file")

    # Weekly report analysis
    parser.add_argument(
        "--include-weekly",
        action="store_true",
        help="Include weekly topic report synthesis costs (Phase 1 + Phase 2)",
    )

    args = parser.parse_args()

    # Load pricing data
    try:
        pricing_data = PricingData()
    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Error loading pricing data: {e}")
        sys.exit(1)

    # Handle --list-models
    if args.list_models:
        print("\nAvailable Models:")
        print("=" * 60)
        for provider in pricing_data.list_providers():
            models = pricing_data.list_models(provider=provider)
            print(f"\n{provider.upper()}:")
            for model in models:
                model_pricing = pricing_data.get_model_pricing(model)
                print(
                    f"  {model:<25} ${model_pricing.input_cost_per_1m:>6.2f}/1M input, "
                    f"${model_pricing.output_cost_per_1m:>6.2f}/1M output"
                )
        print()
        sys.exit(0)

    # Validate newsletter selection
    if not any([args.latest, args.newsletter_id, args.source_id]):
        print("Error: Must specify --latest, --newsletter-id, or --source-id")
        parser.print_help()
        sys.exit(1)

    # Fetch newsletters
    newsletters = fetch_newsletters(
        latest=args.latest,
        newsletter_id=args.newsletter_id,
        source_id=args.source_id,
    )

    if not newsletters:
        sys.exit(1)

    # Determine which models to analyze
    if args.models:
        model_names = [m.strip() for m in args.models.split(",")]
    else:
        model_names = [args.model]

    # Validate models exist in pricing data
    for model_name in model_names:
        try:
            pricing_data.get_model_pricing(model_name)
        except KeyError as e:
            print(f"Error: {e}")
            sys.exit(1)

    # Analyze newsletters for each model
    analyses_by_model = {}
    weekly_analyses_by_model = {}
    pricing_by_model = {}

    for model_name in model_names:
        print(f"\nAnalyzing with model: {model_name}")
        model_pricing = pricing_data.get_model_pricing(model_name)
        pricing_by_model[model_name] = model_pricing

        # Phase 1: Analyze individual newsletter processing (3 LLM calls each)
        analyses = []
        for i, newsletter in enumerate(newsletters, 1):
            if not newsletter.get("plain_text"):
                print(f"  Warning: Newsletter {i} has no plain_text, skipping")
                continue

            print(f"  Analyzing newsletter {i}/{len(newsletters)}...", end=" ")
            analysis = analyze_newsletter_tokens(newsletter, model_name)
            analyses.append(analysis)
            print("OK")

        analyses_by_model[model_name] = analyses
        print(f"  Completed {len(analyses)} newsletters")

        # Phase 2: Analyze weekly report synthesis (if requested)
        weekly_analyses = []
        if args.include_weekly:
            print("\n  Analyzing weekly report synthesis...")

            # Group newsletters by week
            weeks = group_newsletters_by_week(newsletters)
            print(f"  Found {len(weeks)} weeks of newsletters")

            for week_id, week_newsletters in sorted(weeks.items()):
                print(f"\n  > Week {week_id} ({len(week_newsletters)} newsletters)")

                # Get all topics across all newsletters in this week
                all_topics = get_topics_from_newsletters(week_newsletters)

                if not all_topics:
                    print(
                        "    WARNING: No topics found in newsletters (have they been processed with LLM?)"
                    )
                    print(
                        "    Skipping weekly analysis - run process_llm_metadata first"
                    )
                    continue

                print(f"    Topics to analyze: {', '.join(sorted(all_topics))}")

                # For each topic, simulate weekly report generation
                for topic in sorted(all_topics):
                    # Filter newsletters that have this topic
                    topic_newsletters = [
                        nl
                        for nl in week_newsletters
                        if nl.get("topics") and topic in nl["topics"]
                    ]

                    if not topic_newsletters:
                        continue

                    print(
                        f"    > {topic}: {len(topic_newsletters)} newsletters...",
                        end=" ",
                    )
                    weekly_analysis = analyze_weekly_report_tokens(
                        topic=topic,
                        newsletters=topic_newsletters,
                        week_id=week_id,
                        model_name=model_name,
                    )
                    weekly_analyses.append(weekly_analysis)
                    print("OK")

            weekly_analyses_by_model[model_name] = weekly_analyses
            print(f"\n  Completed {len(weekly_analyses)} weekly reports")

    # Generate and output reports
    if len(model_names) == 1:
        # Single model report
        model_name = model_names[0]
        analyses = analyses_by_model[model_name]
        weekly_analyses = weekly_analyses_by_model.get(model_name, [])
        model_pricing = pricing_by_model[model_name]

        # Text report (always to stdout unless only JSON/CSV requested)
        if not (args.output_json or args.output_csv):
            print("\n")
            if weekly_analyses:
                print(
                    generate_combined_text_report(
                        analyses, weekly_analyses, model_pricing
                    )
                )
            else:
                print(generate_text_report(analyses, model_pricing))

        # JSON output
        if args.output_json:
            import json

            report_data = generate_json_report(analyses, model_pricing)
            # TODO: Add weekly data to JSON report
            with open(args.output_json, "w") as f:
                json.dump(report_data, f, indent=2)
            print(f"\nJSON report saved to: {args.output_json}")

        # CSV output
        if args.output_csv:
            csv_data = generate_csv_report(analyses, model_pricing)
            # TODO: Add weekly data to CSV report
            with open(args.output_csv, "w") as f:
                f.write(csv_data)
            print(f"CSV report saved to: {args.output_csv}")

    else:
        # Comparison report
        # TODO: Add weekly costs to comparison report
        print("\n")
        print(generate_comparison_report(analyses_by_model, pricing_by_model))


if __name__ == "__main__":
    main()
