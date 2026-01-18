from ollama import Client
from pydantic import BaseModel, Field
from typing import List
import time

TOPICS = [
    # Incremental Housing
    "4_flats_legalization",
    "missing_middle_housing",
    "zoning_reform",
    "adu_coach_house",
    "housing_development",
    "single_stair_reform",

    # Ending Parking Mandates
    "parking_minimums_elimination",

    # Safe & Productive Streets
    "pedestrian_safety",
    "bike_infrastructure",
    "tactical_urbanism",
    "traffic_calming",
    "street_redesign",

    # Transit
    "transit_improvement",
    "cta_metra_funding",
    "transit_service_expansion",

    # Transparent Local Accounting
    "budget_transparency",
    "fiscal_sustainability",
    "tax_policy",

    # Governance & Community Engagement
    "community_meeting",
    "development_approval",
    "ordinance_debate",
    "public_hearing",
    "city_charter",
]

class TopicsExtraction(BaseModel):
    topics: List[str] = Field(description="List of relevant topics from predefined list")

class Summary(BaseModel):
    summary: str = Field(max_length=2000, description="2-3 sentence summary")

class RelevanceScore(BaseModel):
    score: int = Field(ge=0, le=10, description="Relevance score 0-10")
    reasoning: str = Field(max_length=1000, description="Brief explanation")


# Sometimes Ollama calls hang indefinitely. We create a global client with a set timeout to avoid this breaking things.
ollama_client = Client(timeout=240.0)


def call_llm(model: str, prompt: str, schema: dict, temperature: float = 0, max_retries: int = 3) -> str:
    """
    Central LLM calling method with structured output and retry logic.
    
    Args:
        model: Ollama model name
        prompt: User prompt
        schema: Pydantic model JSON schema
        temperature: Temperature for generation
        max_retries: Maximum number of retry attempts
        
    Returns:
        JSON string response
        
    Raises:
        Exception: If all retries fail
    """
    for attempt in range(max_retries):
        try:
            response = ollama_client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                format=schema,
                options={
                    "temperature": temperature,
                    }
            )
            content = response.message.content
            
            # Validate it's not empty
            if not content or content.strip() == "":
                raise ValueError("LLM returned empty response")
                
            return content
            
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Simple exponential backoff: 1s, 2s, 4s
                print(f"  ⚠ Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise Exception(f"LLM call failed after {max_retries} attempts: {e}")


def extract_topics(content: str, model: str) -> List[str]:
    """Extract relevant topics from newsletter content."""

    prompt = f"""Identify topics from this Chicago alderman newsletter relevant to Strong Towns Chicago.

STC focuses on: Housing (4-flats, zoning, ADUs), Parking Reform, Safe Streets (bike/ped, traffic calming), Transit (CTA/Metra/bus), Budget/Fiscal Policy, Governance (meetings, development approvals, ordinances).

Topics: {', '.join(TOPICS)}

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
        
        print(f"  ✓ Valid Topics: {', '.join(valid_topics) if valid_topics else 'none'}")
        return valid_topics
    except Exception as e:
        print(f"  ✗ Topic extraction failed: {e}")
        return []


def generate_summary(content: str, model: str) -> str:
    """Generate concise summary of newsletter."""

    prompt = f"""Summarize this alderman's newsletter in 2-3 sentences.

PRIORITIZE mentioning (in order of importance):
1. Meetings/hearings about zoning, development, housing, transit, or budget
2. Policy changes or ordinances related to housing, parking, transit, or streets
3. Development approvals or zoning changes
4. Budget/infrastructure spending decisions
5. Transit service changes or funding
6. Street safety or redesign projects

Then briefly mention other major announcements or events. Be concise and factual.
Reference the name of the alderman and ward if they are mentioned.

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


def score_relevance(content: str, model: str) -> int | None:
    """Score newsletter relevance to urban planning/policy topics."""

    prompt = f"""Rate this newsletter's relevance to Strong Towns Chicago (0-10).

Strong Towns Chicago's 5 Priority Campaigns:
1. Incremental Housing: Re-legalizing 4-flats, missing middle housing, ADUs, zoning reform
2. Ending Parking Mandates: Eliminating parking minimums, reducing parking subsidies
3. Safe & Productive Streets: Bike lanes, pedestrian safety, tactical urbanism, traffic calming
4. Transit: CTA/Metra funding, bus network improvements, L maintenance, stopping Lake Shore Drive expansion
5. Transparent Local Accounting: Budget transparency, fiscal sustainability, infrastructure ROI

SCORING:

9-10 = Major action opportunity OR multiple high-impact announcements:
• Upcoming votes on housing/parking/transit ordinances
• Public feedback periods on zoning changes
• Budget hearings on infrastructure/transit
• Multiple significant STC-related projects announced together
• Major policy changes (eliminating parking minimums, legalizing 4-flats)
Example: "Feedback open until Jan 19 on zoning change + multiple bike lane projects announced"

7-8 = Multiple relevant announcements OR single significant project:
• 2+ street safety projects (bike lanes, traffic calming, etc.)
• 2+ housing developments or zoning changes
• Significant transit service/funding changes
• Detailed budget allocations for infrastructure
Example: "New bike medians on Pratt + resurfacing Ashland + Lincoln streetscape complete"

5-6 = Single relevant announcement:
• One street safety improvement
• One housing development or zoning change
• Minor transit updates
• Brief budget mention
Example: "New bike lane installed on Main Street"

3-4 = Vague mention of STC topics:
• General community meeting that might touch on housing/transit
• Economic development mentioning transit access
Example: "Town hall on neighborhood priorities"

0-2 = Not relevant:
• Holidays, office hours, festivals, constituent services
Example: "Annual neighborhood BBQ Saturday"

Weight public feedback periods and upcoming meetings/votes highly.

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


def process_with_ollama(newsletter: dict, model: str = "gpt-oss:20b", max_chars: int = 100000) -> dict:
    """
    Process newsletter with LLM.
    
    Args:
        max_chars: Max characters to send to LLM (truncates to prevent passing in more chars than the token limit
    """
    plain_text = newsletter['plain_text']
    
    if len(plain_text) > max_chars:
        plain_text = plain_text[:max_chars]
        print(f"  ⚠ Truncated: {len(newsletter['plain_text'])} → {max_chars} chars")
    
    content = f"Subject: {newsletter['subject']}\n\n{plain_text}"
    
    topics = extract_topics(content, model)
    summary = generate_summary(content, model)
    relevance_score = score_relevance(content, model)
    
    return {
        "topics": topics,
        "summary": summary,
        "relevance_score": relevance_score
    }