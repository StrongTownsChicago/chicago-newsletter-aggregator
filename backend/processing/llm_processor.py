"""
LLM-based newsletter processing for Strong Towns Chicago.

This module analyzes alderman newsletters and extracts:
- Relevant topics from a predefined list aligned with STC's 5 priority campaigns
- Concise summaries that prioritize STC-relevant content

The processing pipeline runs two sequential LLM calls per newsletter: topic extraction and
summarization.

LLM calls are dispatched via `processing.llm_client`, which supports multiple providers.
Pass a provider-prefixed model string (e.g., "openai:gpt-5") to use a cloud provider.
Bare model names default to Ollama for backward compatibility.
"""

from datetime import datetime

from pydantic import BaseModel, Field

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


def extract_newsletter_metadata(
    newsletter: dict[str, str],
    model: str = "gpt-oss:20b",
    max_chars: int = MAX_NEWSLETTER_CHARS,
) -> dict[str, list[str] | str]:
    """
    Process a newsletter through the complete LLM pipeline.

    Runs two sequential LLM calls to extract topics and generate a summary. Truncates content
    to max_chars to prevent token limit issues.

    Args:
        newsletter: Newsletter dict with 'subject' and 'plain_text' keys
        model: Ollama model name (default: "gpt-oss:20b")
        max_chars: Maximum characters to send to LLM (default: MAX_NEWSLETTER_CHARS)

    Returns:
        Dict with keys: 'topics' (list[str]) and 'summary' (str)
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

    return {"topics": topics, "summary": summary}
