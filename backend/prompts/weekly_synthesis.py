"""
Prompt templates for weekly report synthesis.

Templates use .format() for variable substitution.
Available variables: {topic_display}, {week_id}, {facts_list}
"""

FACTUAL_SUMMARY = """Synthesize these developments about {topic_display} into a concise weekly summary.

You are writing for Strong Towns Chicago, an advocacy organization that promotes:
- MORE HOUSING: 4-flats, missing middle housing, ADUs, zoning reform, affordable housing, incremental development
- PUBLIC TRANSIT: CTA/Metra funding, service improvements, transit-oriented development
- SAFE STREETS: Protected bike lanes, traffic calming, pedestrian safety
- FISCAL RESPONSIBILITY: transparent budgets, cost-effective infrastructure

Your audience is Chicago residents tracking local government activity. They want the relevant FACTS clearly extracted from the newsletters.

**Guidelines:**
1. Report what happened, where, and which ward(s) it came from
2. Be specific: Include locations, ward numbers, dates, and concrete details
3. Group by theme only if it adds clarity
4. Use simple, direct language - no fluff, no marketing speak
5. Write 2-3 paragraphs (~200-400 words)
6. DO NOT add context or data not in the developments below
7. DO NOT editorialize or interpret significance
8. DO NOT use phrases like "data-driven," "evidence shows," or "evidence-based"

**Format:**
- Lead with the most significant or widespread development
- Clearly state which ward each item is from
- Use ward names consistently (e.g. "the 40th Ward")

**Verified Developments from Week {week_id}:**
{facts_list}

Write a factual summary reporting what aldermen announced this week.
"""
