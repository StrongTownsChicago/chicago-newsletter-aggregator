# Local LLM Processing Guide

Since LLM processing runs locally with Ollama (not in GitHub Actions), follow these steps to process newsletters that were ingested via automation.

## Prerequisites

1. Ollama installed locally: `curl -fsSL https://ollama.com/install.sh | sh`
2. Model downloaded: `ollama pull gpt-oss:20b`
3. Backend dependencies installed: `cd backend && uv sync`

### Manual Processing of Existing Newsletters

You can run the LLM processor on already-ingested newsletters using the `process_llm_metadata.py` utility:

```bash
# Process the 10 most recent newsletters
uv run python -m utils.process_llm_metadata --latest 10

# Process newsletters that are missing LLM metadata
uv run python -m utils.process_llm_metadata --missing-metadata --latest 50

# Process newsletters and trigger notifications for matched rules
uv run python -m utils.process_llm_metadata --latest 10 --queue-notifications

# Process all newsletters from a specific source
uv run python -m utils.process_llm_metadata --source-id 5

# Process a single newsletter by ID
uv run python -m utils.process_llm_metadata --newsletter-id <uuid>
```

## Recommended Schedule

- **Daily**: Process newsletters from the last 24 hours
- **Weekly**: Catch up on any missed newsletters
- **After changes**: Reprocess when updating LLM prompts

## Verification

Check that newsletters have LLM metadata populated:

```sql
-- In Supabase SQL editor
SELECT id, subject, topics, summary, relevance_score
FROM newsletters
WHERE topics IS NULL OR summary IS NULL
ORDER BY received_date DESC
LIMIT 10;
```

If results show NULL values, those newsletters need LLM processing.
