"""
LLM-based newsletter processing for Strong Towns Chicago.

This module analyzes alderman newsletters and extracts:
- Relevant topics from a predefined list aligned with STC's 5 priority campaigns
- Concise summaries that prioritize STC-relevant content
- Relevance scores (0-10) indicating how important the newsletter is to STC members

The processing pipeline runs three sequential LLM calls per newsletter, with the relevance scoring
step building on the previous ones for better accuracy.

LLM calls are dispatched via `processing.llm_client`, which supports multiple providers.
Pass a provider-prefixed model string (e.g., "openai:gpt-5") to use a cloud provider.
Bare model names default to Ollama for backward compatibility.
"""

from pydantic import BaseModel, Field
from datetime import datetime

from processing.llm_client import call_llm

__all__ = ["call_llm"]

# LLM processing limits
MAX_NEWSLETTER_CHARS = 100000  # Maximum newsletter content length before truncation
MAX_LLM_RETRIES = 6  # Maximum retry attempts for failed LLM calls

TOPICS = [
    # Incremental Housing
    "4_flats_legalization",
    "missing_middle_housing",
    "accessory_dwelling_units",
    "single_stair_reform",
    # Safe & Productive Streets
    "bike_lanes",
    "street_redesign",
    "street_safety_or_traffic_calming",
    # Transit
    "transit_funding",
    # Transparent Local Accounting
    "city_budget",
    "tax_policy",
    # Governance & Community Engagement
    "zoning_or_development_meeting_or_approval",
    "city_charter",
]


class TopicsExtraction(BaseModel):
    topics: list[str] = Field(
        description="List of relevant topics from predefined list"
    )


class Summary(BaseModel):
    summary: str = Field(max_length=2000, description="2-3 sentence summary")


class RelevanceScore(BaseModel):
    score: int = Field(ge=0, le=10, description="Relevance score 0-10")
    reasoning: str = Field(max_length=1000, description="Brief explanation")


def extract_topics(content: str, model: str) -> list[str]:
    """
    Extract STC-relevant topics from newsletter content.

    Uses LLM to identify which predefined topics (from TOPICS constant) are explicitly discussed
    in the newsletter. Filters results to only valid topics. Prioritizes housing, transit, parking,
    and governance-related content.

    Args:
        content: Newsletter text (subject + body)
        model: Ollama model name to use

    Returns:
        List of topic strings from TOPICS that are relevant (empty list if none found or on error)
    """

    prompt = f"""Identify topics from this Chicago alderman newsletter relevant to Strong Towns Chicago.

STC focuses on: Housing (4-flats, zoning, ADUs), Parking Reform, Safe Streets (bike/ped, traffic calming), Transit (CTA/Metra/bus), Budget/Fiscal Policy, Governance (meetings, development approvals, ordinances).

Topics: {", ".join(TOPICS)}

Select ONLY explicitly discussed topics. Prioritize: zoning/development approvals, housing/transit/budget meetings, parking/transit policy.

Return empty list if none apply.

Newsletter:
{content}
"""
    try:
        print("  → Extracting topics...")
        response = call_llm(model, prompt, TopicsExtraction.model_json_schema())
        data = TopicsExtraction.model_validate_json(response)
        # Filter to only valid topics
        valid_topics = [t for t in data.topics if t in TOPICS]

        print(
            f"  ✓ Valid Topics: {', '.join(valid_topics) if valid_topics else 'none'}"
        )
        return valid_topics
    except Exception as e:
        print(f"  ✗ Topic extraction failed: {e}")
        return []


def generate_summary(content: str, model: str) -> str:
    """
    Generate a 2-3 sentence summary prioritizing STC-relevant content.

    Uses LLM to create a concise summary that leads with the most relevant content (meetings,
    policy changes, development approvals, budget decisions, transit/street projects) before
    mentioning other announcements. Includes alderman and ward information when available.

    Args:
        content: Newsletter text (subject + body)
        model: Ollama model name to use

    Returns:
        2-3 sentence summary string (empty string on error)
    """

    # The sentence about Alfred is to avoid hallucinations by the gpt-oss 20b.
    prompt = f"""Summarize this alderman's newsletter in 2-3 sentences.

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

    try:
        print("  → Generating summary...")
        response = call_llm(model, prompt, Summary.model_json_schema())
        data = Summary.model_validate_json(response)
        print(f"  ✓ Summary: {data.summary}")
        return data.summary
    except Exception as e:
        print(f"  ✗ Summary generation failed: {e}")
        return ""


def score_relevance(
    content: str,
    model: str,
    topics: list[str] | None = None,
    summary: str | None = None,
) -> int | None:
    """
    Score newsletter relevance to Strong Towns Chicago priorities on a 0-10 scale.

    Uses previously extracted topics and summary as context to score how relevant the newsletter
    is to STC members. Higher scores indicate action opportunities (9-10: major policy changes,
    new bike lanes, citywide initiatives), while most routine newsletters score 0-2.

    Args:
        content: Newsletter text (subject + body)
        model: Ollama model name to use
        topics: Previously extracted topic list (optional, improves accuracy)
        summary: Previously generated summary (optional, improves accuracy)

    Returns:
        Integer score 0-10, or None on error
    """

    # Build context from previously extracted info
    context_section = ""
    if topics or summary:
        context_section = (
            "\nFor context, here is what was already extracted from this newsletter:\n"
        )
        if topics and len(topics) > 0:
            context_section += f"Topics identified: {', '.join(topics)}\n"
        if summary:
            context_section += f"Summary: {summary}\n"

    prompt = f"""Rate this newsletter's relevance to Strong Towns Chicago (0-10).

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

    try:
        response = call_llm(model, prompt, RelevanceScore.model_json_schema())
        data = RelevanceScore.model_validate_json(response)
        print(f"  ✓ Score: {data.score}/10 ({data.reasoning})")
        return data.score
    except Exception as e:
        print(f"  ✗ Relevance scoring failed: {e}")
        return None


def extract_newsletter_metadata(
    newsletter: dict[str, str],
    model: str = "gpt-oss:20b",
    max_chars: int = MAX_NEWSLETTER_CHARS,
) -> dict[str, list[str] | str | int | None]:
    """
    Process a newsletter through the complete LLM pipeline.

    Runs three sequential LLM calls to extract topics, generate summary, and score relevance.
    Each step builds on the previous for better accuracy. Truncates content to max_chars to
    prevent token limit issues.

    Args:
        newsletter: Newsletter dict with 'subject' and 'plain_text' keys
        model: Ollama model name (default: "gpt-oss:20b")
        max_chars: Maximum characters to send to LLM (default: MAX_NEWSLETTER_CHARS)

    Returns:
        Dict with keys: 'topics' (list[str]), 'summary' (str), 'relevance_score' (int|None)
    """
    plain_text = newsletter["plain_text"]

    if len(plain_text) > max_chars:
        plain_text = plain_text[:max_chars]
        print(f"  ⚠ Truncated: {len(newsletter['plain_text'])} → {max_chars} chars")

    today = datetime.now().strftime("%Y-%m-%d")
    content = (
        f"Today's date: {today}\n\nSubject: {newsletter['subject']}\n\n{plain_text}"
    )

    topics = extract_topics(content, model)
    summary = generate_summary(content, model)
    relevance_score = score_relevance(content, model, topics, summary)

    return {"topics": topics, "summary": summary, "relevance_score": relevance_score}
