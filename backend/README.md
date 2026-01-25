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
ENABLE_NOTIFICATIONS=true
OLLAMA_MODEL=gpt-oss:20b
RESEND_API_KEY=re_xxxxxxxxxxxxxxxxxxxxx
NOTIFICATION_FROM_EMAIL=notifications@yourdomain.com
FRONTEND_BASE_URL=https://chicago-newsletter-aggregator.open-advocacy.com  # Optional, defaults to production
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

### LLM Metadata Processing

Process existing newsletters with LLM (add/update topics, summary, relevance score):

```bash
# Process latest 10 newsletters
uv run python -m utils.process_llm_metadata --latest 10

# Process all newsletters from source 5
uv run python -m utils.process_llm_metadata --source-id 5

# Process only newsletters missing metadata
uv run python -m utils.process_llm_metadata --missing-metadata --latest 50

# Process and trigger notifications
uv run python -m utils.process_llm_metadata --missing-metadata --queue-notifications

# Dry run (preview what would be processed)
uv run python -m utils.process_llm_metadata --latest 10 --dry-run
```
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
