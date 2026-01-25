# Local LLM Processing Guide

Since LLM processing runs locally with Ollama (not in GitHub Actions), follow these steps to process newsletters that were ingested via automation.

## Prerequisites

1. Ollama installed locally: `curl -fsSL https://ollama.com/install.sh | sh`
2. Model downloaded: `ollama pull gpt-oss:20b`
3. Backend dependencies installed: `cd backend && uv sync`

## Process Recent Newsletters

```bash
cd backend

# Process latest 50 newsletters (default behavior)
uv run python utils/reprocess_newsletters.py --latest 50

# Process all newsletters from a specific source
uv run python utils/reprocess_newsletters.py --source-id 5

# Dry run to see what would be processed
uv run python utils/reprocess_newsletters.py --latest 10 --dry-run
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
