# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Chicago Newsletter Aggregator: A searchable archive of newsletters from Chicago aldermen, built for Strong Towns Chicago. The system ingests newsletters via Gmail IMAP and web scraping, processes them with LLM for topic extraction and relevance scoring, and presents them through an Astro frontend.

## Tech Stack

- **Frontend**: Astro v5 + Tailwind CSS v4 (deployed on Cloudflare Pages)
- **Backend**: Python 3.13+ with uv package manager
- **Database**: Supabase PostgreSQL
- **LLM**: Ollama (local inference with gpt-oss:20b model)

## Common Commands

### Backend (from `backend/` directory)

```bash
# Install dependencies
uv sync

# Process unread emails from Gmail
uv run python -m ingest.email.process_emails

# Scrape all sources with newsletter_archive_url set
uv run python -m ingest.scraper.process_scraped_newsletters

# Scrape specific source (source_id, archive_url, optional limit)
uv run python -m ingest.scraper.process_scraped_newsletters 1 "https://..." 10

# Reprocess existing newsletters with LLM prompts
uv run python -m processing.reprocess_newsletters --latest 10
uv run python -m processing.reprocess_newsletters --latest 10 --skip 20  # Skip first 20, process next 10
uv run python -m processing.reprocess_newsletters --source-id 5
uv run python -m processing.reprocess_newsletters --all
uv run python -m processing.reprocess_newsletters --latest 20 --source-id 3
uv run python -m processing.reprocess_newsletters --dry-run --latest 10
```

### Frontend (from `frontend/` directory)

```bash
# Install dependencies
npm install

# Run dev server (http://localhost:4321)
npm run dev

# Build for production
npm run build

# Preview production build
npm run preview
```

### LLM Setup (one-time)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model
ollama pull gpt-oss:20b
```

## Architecture

### Data Flow

1. **Ingestion**: Emails arrive via Gmail IMAP polling OR web scraping from MailChimp archives
2. **Source Matching**: Email patterns matched against `email_source_mappings` table with wildcard support
3. **Storage**: Raw newsletters stored in `newsletters` table (plain_text, raw_html, metadata)
4. **LLM Processing**: Three separate Ollama calls per newsletter:
   - Topic extraction (from predefined list in `llm_processor.py:TOPICS`)
   - Summarization (2-3 sentences)
   - Relevance scoring (0-10 for Strong Towns Chicago priorities)
5. **Frontend**: Astro SSR queries Supabase for search/display

### Backend Structure

```
backend/
├── ingest/
│   ├── email/
│   │   ├── email_parser.py       # Converts IMAP messages to newsletter dicts
│   │   └── process_emails.py     # Gmail IMAP polling orchestration
│   └── scraper/
│       ├── scraper_strategies.py # Strategy pattern for archive formats (MailChimp, generic)
│       ├── newsletter_scraper.py # Fetches and parses individual newsletter pages
│       └── process_scraped_newsletters.py  # Orchestrates scraping workflow
├── processing/
│   └── llm_processor.py          # LLM topic/summary/scoring with Pydantic schemas
└── shared/
    ├── db.py                     # Supabase client singleton
    └── utils.py                  # Shared utilities
```

### Frontend Structure

```
frontend/src/
├── pages/
│   ├── index.astro               # Homepage with recent newsletters
│   ├── search.astro              # Search interface with filters
│   └── newsletter/[id].astro     # Newsletter detail view
├── components/
│   └── NewsletterCard.astro      # Reusable card component
└── lib/
    └── supabase.ts               # Supabase client + TypeScript interfaces
```

### Database Schema (Key Tables)

- **sources**: Aldermen/officials (name, ward_number, email_address, newsletter_archive_url)
- **email_source_mappings**: Email pattern → source_id mapping (supports SQL wildcards like `%@40thward.org`)
- **newsletters**: Main data table with full-text search (`search_vector` TSVECTOR), topics array, relevance_score

### Key Design Patterns

**Email Source Matching**: Uses flexible pattern matching in `email_parser.py:lookup_source_by_email()`:

- SQL wildcards (`%`) converted to regex for matching
- Exact and substring matching as fallback
- Returns full source record with joined data

**Web Scraping Strategy Pattern**: `scraper_strategies.py` defines:

- `MailChimpArchiveStrategy` for MailChimp archives (most aldermen use this)
- `GenericListStrategy` as fallback
- `get_strategy_for_url()` selects strategy based on URL

**LLM Processing**: `llm_processor.py:process_with_ollama()` orchestrates three separate calls:

- Uses Pydantic models for structured output validation
- Truncates content to 100k chars to avoid token limits
- Filters extracted topics against predefined `TOPICS` list to prevent hallucinations
- Global Ollama client with 120s timeout to prevent hanging

**Newsletter Deduplication**: Both ingest paths check for existing `email_uid` (email) or URL+subject combination (scraping) before inserting

## Environment Variables

**Backend** (`.env` in `backend/`):

```
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
ENABLE_LLM=true
ENABLE_NOTIFICATIONS=true
OLLAMA_MODEL=gpt-oss:20b
RESEND_API_KEY=
NOTIFICATION_FROM_EMAIL=
FRONTEND_BASE_URL=  # Optional, defaults to https://chicago-newsletter-aggregator.open-advocacy.com
```

**Frontend** (`.env` in `frontend/`):

```
PUBLIC_SUPABASE_URL=
PUBLIC_SUPABASE_ANON_KEY=
```

## Deployment

- **Backend**: Manual local execution of ingestion scripts (not automated)
- **Frontend**: Auto-deploys via Cloudflare Pages on push to main branch

## Engineering Best Practices

When writing or refactoring code in this repository, follow these core principles:

### Single Responsibility Principle (SRP)
Each function should do one thing well. Separate data extraction from transformation from presentation. If a function has "and" in its description, it probably does too much.

**Bad**: `process_and_send_newsletter()` - fetches data, transforms it, AND sends email
**Good**: Separate functions for fetching, transforming, sending

### DRY (Don't Repeat Yourself)
Never duplicate logic. If you're extracting/formatting the same data in multiple places, create a shared helper function. Process data once, pass the result to consumers.

**Bad**: Parsing dates in 5 different functions
**Good**: One `parse_newsletter_date()` function used everywhere

### Separation of Concerns
Data access, business logic, and presentation should be separate layers. Database code shouldn't know about email templates. Email templates shouldn't contain rule matching logic.

**Example**: Ingestion fetches data → LLM processes it → Notification rules match it → Email renderer presents it (separate files, clear boundaries)

### Performance Matters
Fetch what you need in one query, not in a loop. Group operations. Avoid processing the same data multiple times.

**Bad**: Loop over 100 newsletters, fetch source for each (101 queries)
**Good**: Join with sources table (1 query)

### Testability First
Write code that's easy to test. Pure functions (same input = same output) are ideal. Extract business logic from I/O operations so you can test without databases/APIs.

**Testable**: `rule_matches_newsletter(rule_data, newsletter_data)` - pure function
**Hard to test**: Function that queries DB, checks rules, and sends email all in one

### Meaningful Names
Function names should be verbs. Variables should describe their content. Be specific.

**Good**: `match_newsletter_to_rules()`, `active_rules`, `newsletter_url`
**Bad**: `process()`, `data`, `temp`, `x`

### Declarative Over Imperative
Use declarative patterns when they improve clarity. Strategy pattern over if/else chains. List comprehensions over loops with append. Pydantic models over manual validation.

**Example**: Scraping uses strategy pattern - URL determines strategy, not a long if/elif chain checking URL patterns.

### Error Handling
Catch exceptions at appropriate boundaries. Log errors with context for debugging. Don't let one failure break the entire pipeline. Return meaningful errors, not generic "failed" messages.

**Pattern**: Ingestion catches errors per newsletter, logs details, continues processing remaining newsletters.
