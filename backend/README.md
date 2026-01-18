# Chicago Newsletter Aggregator - Backend

Ingests Chicago alderman newsletters via email (Gmail) and web scraping (MailChimp archives), processes them with LLM for topic extraction and relevance scoring, and stores in Supabase.

## Setup

```bash
# Install dependencies
uv sync

# Configure environment (.env)
GMAIL_ADDRESS=your-email@gmail.com
GMAIL_APP_PASSWORD=your-app-password
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your-service-key
ENABLE_LLM=true
OLLAMA_MODEL=gpt-oss:20b
```

## Email Ingestion

Fetches unread emails from Gmail, parses them, and stores in database.

```bash
# Process new emails
uv run python -m ingest.email.process_emails
```

## Web Scraping

Scrapes newsletter archives from alderman websites (MailChimp).

```bash
# Scrape all sources with newsletter_archive_url set
uv run python -m ingest.scraper.process_scraped

# Scrape specific source (with optional limit)
uv run python -m ingest.scraper.process_scraped <source_id> <archive_url> [limit]

# Example: Scrape Ward 1, limit 10 newsletters
uv run python -m ingest.scraper.process_scraped 1 "https://us4.campaign-archive.com/home/?u=e4d2e8115e36fe98f1fbf8f5f&id=218af5f0b5" 10

# Reprocess existing newsletters with LLM prompts
uv run python -m processing.reprocess_newsletters --latest 10
uv run python -m processing.reprocess_newsletters --source-id 5
uv run python -m processing.reprocess_newsletters --all
uv run python -m processing.reprocess_newsletters --latest 20 --source-id 3
uv run python -m processing.reprocess_newsletters --dry-run --latest 10
```

## LLM Processing

When `ENABLE_LLM=true`, each newsletter is processed to extract:

- **Topics**: Housing, transit, zoning, etc.
- **Summary**: 2-3 sentence overview
- **Relevance Score**: 0-10 for Strong Towns Chicago priorities

Requires Ollama running locally with `gpt-oss:20b` model.

## Directory Structure

```
backend/
├── ingest/
│   ├── email/          # Gmail ingestion
│   └── scraper/        # Web scraping
├── processing/         # LLM processing
└── shared/            # Shared utilities
```
