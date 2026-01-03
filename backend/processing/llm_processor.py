from ollama import chat
from pydantic import BaseModel, Field
from typing import List
import time

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
            response = chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                format=schema,
                options={
                    "temperature": temperature,
                    "num_ctx": 32768  # Ollama defaults to a small context window. We want more for processing newsletters.
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
    
    prompt = f"""Analyze this Chicago newsletter and identify relevant topics.

Focus on: housing, zoning, parking, transit, bike/pedestrian infrastructure, 
budget/fiscal policy, community development, and urban planning.

Available topics: {', '.join(TOPICS)}

Select only topics clearly discussed. Return empty list if none apply.

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
    
    prompt = f"""Summarize this newsletter in 2-3 sentences. Focus on key announcements, 
events, or policy changes. Be concise and factual.

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
    
    try:
        response = call_llm(model, prompt, RelevanceScore.model_json_schema())
        data = RelevanceScore.model_validate_json(response)
        print(f"  ✓ Score: {data.score}/10 ({data.reasoning})")
        return data.score
    except Exception as e:
        print(f"  ✗ Relevance scoring failed: {e}")
        return None


def process_with_ollama(newsletter: dict, model: str = "gpt-oss:20b") -> dict:
    """
    Process newsletter with LLM. Each operation is independent - if one fails, others continue.
    
    Args:
        newsletter: Dict with subject, plain_text
        model: Ollama model name
        
    Returns:
        Dict with summary, topics, relevance_score (failed fields will have default values)
    """
    content = f"Subject: {newsletter['subject']}\n\n{newsletter['plain_text']}"
    
    topics = extract_topics(content, model)
    summary = generate_summary(content, model)
    relevance_score = score_relevance(content, model)
    
    return {
        "topics": topics,
        "summary": summary,
        "relevance_score": relevance_score
    }