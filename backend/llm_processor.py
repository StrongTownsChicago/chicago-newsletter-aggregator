from ollama import chat
from pydantic import BaseModel, Field
from typing import List

TOPICS = [
    "housing_density",
    "parking_reform", 
    "zoning_reform",
    "zoning",
    "bike_infrastructure",
    "pedestrian_safety",
    "transit_improvement",
    "bus_rapid_transit",
    "transit_funding",
    "highway_opposition",
    "traffic_calming",
    "budget_transparency",
    "community_meeting",
    "4_flats_legalization",
    "parking_minimums",
    "walkability",
    "missing_middle_housing",
    "street_design",
    "fiscal_resilience",
    "city_charter",
    "city_budget",
    "accessory_dwelling_unit"
]

class TopicsExtraction(BaseModel):
    topics: List[str] = Field(description="List of relevant topics from predefined list")

class Summary(BaseModel):
    summary: str = Field(max_length=2000, description="2-3 sentence summary")

class RelevanceScore(BaseModel):
    score: int = Field(ge=0, le=10, description="Relevance score 0-10")
    reasoning: str = Field(max_length=1000, description="Brief explanation")


def call_llm(model: str, prompt: str, schema: dict, temperature: float = 0) -> str:
    """
    Central LLM calling method with structured output.
    
    Args:
        model: Ollama model name
        prompt: User prompt
        schema: Pydantic model JSON schema
        temperature: Temperature for generation
        
    Returns:
        JSON string response
    """
    response = chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        format=schema,
        options={"temperature": temperature}
    )
    return response.message.content


def extract_topics(content: str, model: str) -> List[str]:
    """Extract relevant topics from newsletter content."""
    
    prompt = f"""Analyze this Chicago newsletter and identify relevant topics.

Focus on: housing, zoning, parking, transit, bike/pedestrian infrastructure, 
budget/fiscal policy, community development, and urban planning.

Available topics: {', '.join(TOPICS)}

Select only topics clearly discussed. Return empty list if none apply.

Newsletter:
{content}
"""
    print("  → Extracting topics...")
    response = call_llm(model, prompt, TopicsExtraction.model_json_schema())
    data = TopicsExtraction.model_validate_json(response)
    # Filter to only valid topics
    valid_topics = [t for t in data.topics if t in TOPICS]
    
    print(f"  ✓ Valid Topics: {', '.join(valid_topics) if valid_topics else 'none'}")
    return valid_topics


def generate_summary(content: str, model: str) -> str:
    """Generate concise summary of newsletter."""
    
    prompt = f"""Summarize this newsletter in 2-3 sentences. Focus on key announcements, 
events, or policy changes. Be concise and factual.

Newsletter:
{content}
"""
    
    print("  → Generating summary...")
    response = call_llm(model, prompt, Summary.model_json_schema())
    data = Summary.model_validate_json(response)
    print(f"  ✓ Summary: {data.summary}")
    return data.summary


def score_relevance(content: str, model: str) -> int:
    """Score newsletter relevance to urban planning/policy topics."""
    
    prompt = f"""Rate this newsletter's relevance to Strong Towns Chicago (0-10).

Strong Towns Chicago advocates for:
- Housing: Zoning reform, density, eliminating parking minimums, legalizing 4-flats
- Transit: CTA/Metra improvements, bus rapid transit
- Streets: Bike lanes, pedestrian safety, traffic calming
- Fiscal: Budget transparency
- Governance Reform: Establishing a city charter
- Anti-sprawl: Opposing highway expansion

Scoring:
0-2: Not relevant (routine announcements, unrelated topics)
3-5: Tangentially relevant (mentions topics but not focus)
6-8: Relevant (addresses Strong Towns priorities)
9-10: Highly relevant (major campaign, policy change, or advocacy opportunity)

Newsletter:
{content}
"""
    
    response = call_llm(model, prompt, RelevanceScore.model_json_schema())
    data = RelevanceScore.model_validate_json(response)
    print(f"  ✓ Score: {data.score}/10 ({data.reasoning})")
    return data.score


def process_with_ollama(newsletter: dict, model: str = "gpt-oss:20b") -> dict:
    """
    Process newsletter with LLM.
    
    Args:
        newsletter: Dict with subject, plain_text
        model: Ollama model name
        
    Returns:
        Dict with summary, topics, relevance_score
    """
    content = f"Subject: {newsletter['subject']}\n\n{newsletter['plain_text']}"
    
    return {
        "topics": extract_topics(content, model),
        "summary": generate_summary(content, model),
        "relevance_score": score_relevance(content, model)
    }