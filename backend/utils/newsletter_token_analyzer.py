"""
Newsletter token analysis module.

Simulates LLM calls for newsletter processing to estimate token usage and costs.
Replicates exact prompt construction from llm_processor.py and weekly_report_generator.py
without actually calling LLMs.
"""

from datetime import datetime
from dataclasses import dataclass
from typing import Any

from processing.llm_client import parse_model_string
from processing.llm_processor import (
    TOPICS,
    TopicsExtraction,
    Summary,
    RelevanceScore,
    MAX_NEWSLETTER_CHARS,
)
from models.weekly_report import FactExtraction, WeeklySynthesis
from utils.token_counter import (
    estimate_llm_call_tokens,
)


# Estimated response sizes based on actual newsletter data
# These are median values derived from real LLM outputs
ESTIMATED_RESPONSE_SIZES = {
    "topics": 100,  # JSON array of 0-5 topic strings
    "summary": 150,  # 2-3 sentences
    "relevance_score": 120,  # score + reasoning
    "weekly_facts": 200,  # List of KeyDevelopments per newsletter
    "weekly_synthesis": 800,  # 2-4 paragraphs
}


@dataclass
class OperationTokens:
    """Token counts for a single LLM operation."""

    operation: str
    input_tokens: int
    output_tokens: int
    total_tokens: int


@dataclass
class NewsletterTokenAnalysis:
    """Complete token analysis for newsletter processing (3 LLM calls)."""

    newsletter_id: str | None
    topic_extraction: OperationTokens
    summary_generation: OperationTokens
    relevance_scoring: OperationTokens
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int


@dataclass
class WeeklyReportTokenAnalysis:
    """Token analysis for weekly report generation (Phase 1 + Phase 2)."""

    topic: str
    week_id: str
    newsletter_count: int
    phase1_operations: list[OperationTokens]  # One per newsletter
    phase2_operation: OperationTokens
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int


def analyze_newsletter_tokens(
    newsletter: dict[str, Any],
    model_name: str,
    max_chars: int = MAX_NEWSLETTER_CHARS,
) -> NewsletterTokenAnalysis:
    """
    Simulate all 3 LLM calls for newsletter processing and count tokens.

    Replicates exact prompt construction from llm_processor.py:
    1. extract_topics()
    2. generate_summary()
    3. score_relevance()

    Args:
        newsletter: Newsletter dict with 'subject' and 'plain_text' keys
        model_name: Model identifier for encoding selection
        max_chars: Maximum characters to send to LLM (default: MAX_NEWSLETTER_CHARS)

    Returns:
        NewsletterTokenAnalysis with token counts for each operation
    """
    # Replicate truncation logic from llm_processor.py:367-370
    plain_text = newsletter.get("plain_text", "")
    if len(plain_text) > max_chars:
        plain_text = plain_text[:max_chars]

    # Replicate content construction from llm_processor.py:372-374
    today = datetime.now().strftime("%Y-%m-%d")
    content = (
        f"Today's date: {today}\n\nSubject: {newsletter['subject']}\n\n{plain_text}"
    )

    # Determine if schema goes in prompt (gpt-oss Ollama models embed schema in prompt)
    _, bare_model = parse_model_string(model_name)
    include_schema = bare_model.startswith("gpt-oss")

    # Operation 1: Topic Extraction (llm_processor.py:180-192)
    topics_prompt = f"""Identify topics from this Chicago alderman newsletter relevant to Strong Towns Chicago.

STC focuses on: Housing (4-flats, zoning, ADUs), Parking Reform, Safe Streets (bike/ped, traffic calming), Transit (CTA/Metra/bus), Budget/Fiscal Policy, Governance (meetings, development approvals, ordinances).

Topics: {", ".join(TOPICS)}

Select ONLY explicitly discussed topics. Prioritize: zoning/development approvals, housing/transit/budget meetings, parking/transit policy.

Return empty list if none apply.

Newsletter:
{content}
"""
    topics_response = (
        '{"topics": ["bike_lanes", "transit_funding"]}'  # Typical response
    )
    topics_tokens = estimate_llm_call_tokens(
        topics_prompt,
        topics_response,
        TopicsExtraction.model_json_schema(),
        model_name,
        include_schema_in_prompt=include_schema,
    )

    # Operation 2: Summary Generation (llm_processor.py:226-241)
    summary_prompt = f"""Summarize this alderman's newsletter in 2-3 sentences.

PRIORITIZE mentioning (in order of importance):
1. Meetings/hearings about zoning, development, housing, transit, or budget
2. Policy changes or ordinances related to housing, parking reform, transit, or streets
3. Development approvals or zoning changes
4. Budget/infrastructure spending decisions
5. Long term transit service changes or funding (not routine maintenance or temporary changes)
6. Street safety or redesign projects

Then briefly mention other major announcements or events. Be concise and factual.
Reference the name of the alderman and ward if they are mentioned. Do not assume an alderman's first name is Alfred.

Newsletter:
{content}
"""
    summary_response = '{"summary": "Alderman announces new bike lanes on Main St. Community meeting scheduled for Tuesday to discuss transit improvements. Office hours this Friday."}'
    summary_tokens = estimate_llm_call_tokens(
        summary_prompt,
        summary_response,
        Summary.model_json_schema(),
        model_name,
        include_schema_in_prompt=include_schema,
    )

    # Operation 3: Relevance Scoring (llm_processor.py:278-334)
    # This includes context from previous operations (topics + summary)
    extracted_topics = ["bike_lanes", "transit_funding"]  # From operation 1
    extracted_summary = "Alderman announces new bike lanes..."  # From operation 2

    context_section = (
        "\nFor context, here is what was already extracted from this newsletter:\n"
    )
    if extracted_topics:
        context_section += f"Topics identified: {', '.join(extracted_topics)}\n"
    if extracted_summary:
        context_section += f"Summary: {extracted_summary}\n"

    relevance_prompt = f"""Rate this newsletter's relevance to Strong Towns Chicago (0-10).

Strong Towns Chicago's 5 Priority Campaigns:
1. Incremental Housing: Re-legalizing 4-flats, missing middle housing, ADUs, zoning reform
2. Ending Parking Mandates: Eliminating parking minimums, reducing parking subsidies
3. Safe & Productive Streets: Bike lanes, pedestrian safety, tactical urbanism, traffic calming
4. Transit: CTA/Metra funding, bus network improvements, L maintenance, stopping Lake Shore Drive expansion
5. Transparent Local Accounting: Budget transparency, fiscal sustainability, infrastructure ROI

SCORING:

9-10 = Major announcements (rare and exciting):
• Major policy changes (eliminating parking minimums, legalizing 4-flats, upzoning)
• Citywide or major public feedback periods on housing/transit/parking
• NEW transit service routes or frequency expansion
Example: "City Council passes ordinance eliminating parking minimums" or "Alderman announces support for upzoning major corridor"

7-8 = Action opportunities and significant housing/transit announcements:
• Large housing developments approved (many units) or moving to committee
• Public feedback periods on zoning changes or development
• Public hearings/meetings on housing, transit, budget, or street design
• Multiple street safety improvements announced
• Significant budget allocations for bike/transit infrastructure
• NEW bike lanes or protected bike infrastructure announced
Example: "Plan Commission approves 500-unit development, moves to Zoning Committee" or "Public feedback open on zoning change"

5-6 = Minor relevant announcements:
• Small housing developments (several units)
• Single plot zoning approval or variance
• Minor street design project (crosswalk, signage)
• Brief transit/budget mentions
Example: "Zoning approved for 4-unit building at 2415 W Peterson"

3-4 = Vague mentions:
• General community meetings that might touch on STC topics
• Economic development mentioning transit
Example: "Town hall to discuss neighborhood priorities"

0-2 = Not relevant (many newsletters fall here):
• Holidays, office hours, festivals, constituent services, CAPS meetings
• Bridge/viaduct/road construction or maintenance
• Police/crime updates, poll workers, volunteer opportunities
Example: "CAPS meeting Tuesday" or "Lake St bridge work continues"
{context_section}
Newsletter:
{content}
"""
    relevance_response = '{"score": 7, "reasoning": "Newsletter announces new protected bike lanes, which is a significant street safety improvement."}'
    relevance_tokens = estimate_llm_call_tokens(
        relevance_prompt,
        relevance_response,
        RelevanceScore.model_json_schema(),
        model_name,
        include_schema_in_prompt=include_schema,
    )

    # Create operation summaries
    topics_op = OperationTokens(
        operation="topic_extraction",
        input_tokens=topics_tokens["input_tokens"],
        output_tokens=topics_tokens["output_tokens"],
        total_tokens=topics_tokens["total_tokens"],
    )

    summary_op = OperationTokens(
        operation="summary_generation",
        input_tokens=summary_tokens["input_tokens"],
        output_tokens=summary_tokens["output_tokens"],
        total_tokens=summary_tokens["total_tokens"],
    )

    relevance_op = OperationTokens(
        operation="relevance_scoring",
        input_tokens=relevance_tokens["input_tokens"],
        output_tokens=relevance_tokens["output_tokens"],
        total_tokens=relevance_tokens["total_tokens"],
    )

    # Calculate totals
    total_input = (
        topics_op.input_tokens + summary_op.input_tokens + relevance_op.input_tokens
    )
    total_output = (
        topics_op.output_tokens + summary_op.output_tokens + relevance_op.output_tokens
    )

    return NewsletterTokenAnalysis(
        newsletter_id=newsletter.get("id"),
        topic_extraction=topics_op,
        summary_generation=summary_op,
        relevance_scoring=relevance_op,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_input + total_output,
    )


def analyze_weekly_report_tokens(
    topic: str,
    newsletters: list[dict[str, Any]],
    week_id: str,
    model_name: str,
) -> WeeklyReportTokenAnalysis:
    """
    Simulate weekly report LLM calls and count tokens.

    Replicates two-phase process from weekly_report_generator.py:
    Phase 1: Extract facts from each newsletter individually
    Phase 2: Synthesize summary from aggregated facts

    Args:
        topic: Topic identifier (from TOPICS constant)
        newsletters: List of newsletter dicts with id, subject, plain_text, source, ward
        week_id: Week identifier (YYYY-WXX)
        model_name: Model identifier for encoding selection

    Returns:
        WeeklyReportTokenAnalysis with Phase 1 and Phase 2 token counts
    """
    _, bare_model = parse_model_string(model_name)
    include_schema = bare_model.startswith("gpt-oss")

    # Phase 1: Extract facts from each newsletter
    phase1_operations = []

    for newsletter in newsletters:
        ward_info = (
            f"Ward {newsletter.get('ward_number', 'Unknown')}"
            if newsletter.get("ward_number")
            else "Citywide"
        )
        source_info = newsletter.get("source_name", "Unknown Source")

        # Replicate content from weekly_report_generator.py:54-59
        content = f"""Source: {source_info} ({ward_info})
Subject: {newsletter["subject"]}

{newsletter["plain_text"]}
"""

        # Replicate prompt from weekly_report_generator.py:61-89
        phase1_prompt = f"""Extract key developments from this Chicago alderman newsletter about {topic}.

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

        # Typical response with 1-2 developments
        phase1_response = '{"developments": [{"description": "Plan Commission approved 120-unit development at 1234 Main St", "newsletter_ids": [], "wards": ["42"]}]}'

        phase1_tokens = estimate_llm_call_tokens(
            phase1_prompt,
            phase1_response,
            FactExtraction.model_json_schema(),
            model_name,
            include_schema_in_prompt=include_schema,
        )

        phase1_op = OperationTokens(
            operation=f"phase1_fact_extraction_{newsletter.get('id', 'unknown')[:8]}",
            input_tokens=phase1_tokens["input_tokens"],
            output_tokens=phase1_tokens["output_tokens"],
            total_tokens=phase1_tokens["total_tokens"],
        )
        phase1_operations.append(phase1_op)

    # Phase 2: Synthesize summary from aggregated facts
    # Create mock facts list for prompt
    facts_text = []
    for i in range(1, min(len(newsletters), 10) + 1):  # Up to 10 example facts
        facts_text.append(
            f"{i}. New bike lane approved on Main Street, construction starts March (Ward 42)"
        )

    facts_list = "\n".join(facts_text)

    # Replicate from weekly_report_generator.py:196-198
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

    # Simplified version of FACTUAL_SUMMARY prompt (from prompts/weekly_synthesis.py)
    phase2_prompt = f"""Create a 2-4 paragraph weekly summary for {topic_display} ({week_id}).

Based on these developments from Chicago alderman newsletters:

{facts_list}

Write a narrative summary that:
- Identifies patterns or trends across wards
- Highlights most significant developments
- Notes any citywide implications
- Provides Strong Towns perspective (safe streets, housing, transit, fiscal responsibility)

Keep it concise and informative.
"""

    # Typical response: 2-4 paragraphs
    phase2_response = '{"summary": "This week saw significant progress on bike infrastructure across multiple wards. The most notable development was the approval of protected bike lanes on Main Street in Ward 42, with construction scheduled to begin in March. This represents a major step forward for safe streets advocacy in the city. Several other wards also announced plans for traffic calming measures and pedestrian safety improvements. Overall, the week demonstrated growing momentum for Vision Zero initiatives and a shift toward prioritizing active transportation in Chicago\'s neighborhoods."}'

    phase2_tokens = estimate_llm_call_tokens(
        phase2_prompt,
        phase2_response,
        WeeklySynthesis.model_json_schema(),
        model_name,
        include_schema_in_prompt=include_schema,
    )

    phase2_op = OperationTokens(
        operation="phase2_synthesis",
        input_tokens=phase2_tokens["input_tokens"],
        output_tokens=phase2_tokens["output_tokens"],
        total_tokens=phase2_tokens["total_tokens"],
    )

    # Calculate totals
    phase1_input = sum(op.input_tokens for op in phase1_operations)
    phase1_output = sum(op.output_tokens for op in phase1_operations)
    total_input = phase1_input + phase2_op.input_tokens
    total_output = phase1_output + phase2_op.output_tokens

    return WeeklyReportTokenAnalysis(
        topic=topic,
        week_id=week_id,
        newsletter_count=len(newsletters),
        phase1_operations=phase1_operations,
        phase2_operation=phase2_op,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_input + total_output,
    )
