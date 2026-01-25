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

# Process unread emails from Gmail (queues notifications if ENABLE_NOTIFICATIONS=true)
uv run python -m ingest.email.process_emails

# Scrape all sources with newsletter_archive_url set
uv run python -m ingest.scraper.process_scraped_newsletters

# Scrape specific source (source_id, archive_url, optional limit)
uv run python -m ingest.scraper.process_scraped_newsletters 1 "https://..." 10

# Reprocess newsletters with updated LLM prompts
uv run python utils/reprocess_newsletters.py --latest 10
uv run python utils/reprocess_newsletters.py --source-id 5
uv run python utils/reprocess_newsletters.py --dry-run --latest 10

# Reapply privacy sanitization to existing newsletters
uv run python utils/reprocess_newsletters_privacy.py <newsletter_id> --update
uv run python utils/reprocess_newsletters_privacy.py --all --update --quiet

# Test notification rule matching (dry run)
uv run python -m notifications.test_matcher

# Test matching and queue notifications
uv run python -m notifications.test_matcher --queue

# Send daily digest emails (dry run)
uv run python -m notifications.process_notification_queue --daily-digest --dry-run

# Send today's digest
uv run python -m notifications.process_notification_queue --daily-digest

# Send specific date's digest
uv run python -m notifications.process_notification_queue --daily-digest --batch-id 2026-01-21

# Run all tests
uv run python -m unittest discover -s tests

# Lint and format (run after making Python changes)
uv run ruff check --fix  # Fix auto-fixable issues, manually fix remaining
uv run ruff format       # Format code
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

# Run unit tests
npm run test

# Run tests with coverage
npm run test:coverage

# Run tests in watch mode
npm run test:watch

# Run linting
npm run lint
```

### LLM Setup (one-time)

```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Pull the model
ollama pull gpt-oss:20b
```

## Automation

**GitHub Actions Workflows:**
- Email ingestion (`.github/workflows/email_ingestion.yml`) - Polls Gmail, stores newsletters without LLM metadata, queues notifications
- Notification sending (`.github/workflows/send_notifications.yml`) - Sends daily digest emails

Both workflows support manual triggering via Actions tab. See workflow files for schedules and configuration details.

**Local LLM Processing:**
```bash
# Process newsletters with Ollama (runs locally, not in GitHub Actions)
uv run python utils/reprocess_newsletters.py --latest 50
```

See `backend/docs/LOCAL_LLM_PROCESSING.md` for full guide.

## Architecture

### Data Flow

1. **Ingestion**: Emails arrive via Gmail IMAP polling OR web scraping from MailChimp archives
2. **Source Matching**: Email patterns matched against `email_source_mappings` table with wildcard support
3. **Storage**: Raw newsletters stored in `newsletters` table (plain_text, raw_html, metadata)
4. **LLM Processing**: Three separate Ollama calls per newsletter for topic extraction, summarization, and relevance scoring (see `llm_processor.py` for details)
5. **Frontend**: Astro SSR queries Supabase for search/display

### Backend Structure

```
backend/
├── ingest/
│   ├── email/
│   │   ├── email_parser.py       # Converts IMAP messages to newsletter dicts with privacy sanitization
│   │   └── process_emails.py     # Gmail IMAP polling orchestration
│   └── scraper/
│       ├── scraper_strategies.py # Strategy pattern for archive formats (MailChimp, generic)
│       ├── newsletter_scraper.py # Fetches and parses individual newsletter pages
│       └── process_scraped_newsletters.py  # Orchestrates scraping workflow
├── processing/
│   └── llm_processor.py          # LLM topic/summary/scoring with Pydantic schemas
├── notifications/
│   ├── rule_matcher.py           # Match newsletters to user notification rules
│   ├── email_sender.py           # Send digest emails via Resend API
│   ├── process_notification_queue.py  # Daily digest orchestration
│   ├── test_matcher.py           # Testing utility for rule matching
│   └── error_logger.py           # Timestamped error logging
├── utils/
│   ├── reprocess_newsletters.py  # Reprocess existing newsletters with updated LLM prompts
│   ├── reprocess_newsletters_privacy.py  # Reapply privacy sanitization to existing newsletters
│   ├── migrate_topics.py         # Topic migration utility
│   └── download_samples.py       # Download sample newsletters for testing
├── tests/
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   ├── fixtures/                 # Test data and fixtures
│   ├── test_sanitization.py      # Privacy sanitization tests
│   ├── test_sanitization_comprehensive.py  # Comprehensive privacy tests
│   └── test_user_cases.py        # Real-world newsletter test cases
├── config/
│   └── privacy_patterns.py     # URL patterns, text patterns, CSS selectors for privacy filtering
├── shared/
│   ├── db.py                     # Supabase client singleton
│   └── utils.py                  # Shared utilities
└── migrations/
    ├── 001_notification_system.sql  # User profiles, rules, queue, history tables
    └── 002_add_search_term.sql      # Added search_term column to rules
```

### Frontend Structure

```
frontend/src/
├── pages/
│   ├── index.astro               # Homepage with recent newsletters
│   ├── search.astro              # Search interface with filters
│   ├── preferences.astro         # User notification preferences (protected route)
│   ├── newsletter/[id].astro     # Newsletter detail view
│   └── api/notifications/        # Notification management API routes
│       ├── create-rule.ts        # Create notification rule
│       ├── update-rule.ts        # Update existing rule
│       ├── delete-rule.ts        # Delete rule
│       └── update-preferences.ts # Toggle notifications on/off
├── tests/                        # Vitest unit tests
│   ├── unit/                     # Utility tests (supabase.test.ts)
│   ├── api/                      # API route tests (auth.test.ts, notifications.test.ts)
│   ├── middleware.test.ts        # Middleware logic tests
│   ├── helpers.ts                # Test factories for mocking Astro context
│   └── mocks/                    # Global mocks (astro:middleware)
├── components/
│   ├── NewsletterCard.astro      # Reusable card component
│   └── AuthButton.astro          # Auth UI
└── lib/
    └── supabase.ts               # Supabase client + TypeScript interfaces + notificationsEnabled() helper
```

### Database Schema

**Core Tables:** `sources` (aldermen/officials), `email_source_mappings` (pattern matching), `newsletters` (content with full-text search)

**Notification Tables:** `user_profiles`, `notification_rules`, `notification_queue`, `notification_history`

**Full schema and RLS policies:** See [backend/SCHEMA.md](backend/SCHEMA.md)

### Key Design Patterns

**Email Source Matching** (`email_parser.py:lookup_source_by_email()`): Flexible pattern matching with SQL wildcard support (e.g., `%@40thward.org`), regex conversion, and fallback to substring matching.

**Web Scraping Strategy Pattern** (`scraper_strategies.py`): Strategy pattern for different archive formats. `get_strategy_for_url()` selects between `MailChimpArchiveStrategy` (most common) and `GenericListStrategy` fallback.

**LLM Processing** (`llm_processor.py:process_with_ollama()`): Three separate Ollama calls using Pydantic models for structured output validation. Filters extracted topics against predefined list to prevent hallucinations.

**Newsletter Deduplication**: Both ingest paths check for existing `email_uid` (email) or URL+subject combination (scraping) before inserting.

**Notification System** (`notifications/`):

- `rule_matcher.py` - Matches newsletters against user rules (topics, search terms, wards). All filters AND-ed, within categories OR-ed.
- `email_sender.py` - Sends daily digests via Resend API with HTML/plain text templates
- `process_notification_queue.py` - Orchestrates digest sending, groups by user, updates queue status, records in history
- Integration: Email ingestion queues notifications when `ENABLE_NOTIFICATIONS=true`. Web scraping does NOT trigger notifications (intentional). Failures don't break ingestion.

**Privacy Sanitization** (`email_parser.py:sanitize_content()`): Config-driven filtering using `backend/config/privacy_patterns.py` (URL patterns, text patterns, CSS selectors defined as Python constants). Pure function receives patterns as parameter for testability. Links with images unwrapped; text-only privacy links removed. See `backend/tests/test_sanitization*.py` for test coverage.

**Newsletter Content Storage** (`newsletters` table): Both `plain_text` and `raw_html` columns serve distinct, critical purposes:

- **`plain_text`** - Primary format for all processing:
  - Powers full-text search via generated `search_vector` column (combined with subject)
  - Required input for all LLM operations (topic extraction, summarization, relevance scoring via `llm_processor.py`)
  - Used for notification rule keyword matching (`rule_matcher.py`)
  - Fallback display when HTML unavailable
  - Generated from email plain text body or HTML-to-text conversion (`html2text`)

- **`raw_html`** - Display-only format:
  - Used solely for formatted frontend presentation (`newsletter/[id].astro`)
  - Preserves original newsletter styling and layout

Both formats are independently sanitized during ingestion for privacy protection. Without `plain_text`, search, LLM features, and notification matching would be non-functional.

## Environment Variables

**Backend** (`.env` in `backend/`):

```
# Gmail IMAP
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=

# Supabase
SUPABASE_URL=
SUPABASE_SERVICE_KEY=

# LLM Processing (optional, default: false)
ENABLE_LLM=true
OLLAMA_MODEL=gpt-oss:20b

# Notifications (optional, default: false)
ENABLE_NOTIFICATIONS=true        # Enables notification queuing during email ingestion
RESEND_API_KEY=re_xxxxx         # Resend API key for sending digest emails
NOTIFICATION_FROM_EMAIL=noreply@yourdomain.com  # Must be verified in Resend
FRONTEND_BASE_URL=your_base_url  # Optional, for preference links

# Privacy (optional)
PRIVACY_STRIP_PHRASES=           # Comma-separated phrases to redact (e.g., "John Doe,personal@example.com")
```

**Frontend** (`.env` in `frontend/`):

```
PUBLIC_SUPABASE_URL=
PUBLIC_SUPABASE_ANON_KEY=
PUBLIC_ENABLE_NOTIFICATIONS=
```

## Testing

### Privacy Sanitization Tests

**Test suites** in `backend/tests/`:

- `test_sanitization.py` - Basic tests (unsubscribe links, footers, text filtering)
- `test_sanitization_comprehensive.py` - Comprehensive coverage (URL patterns, link text, CSS selectors, false positive prevention)
- `test_user_cases.py` - Real-world integration tests (Mailchimp, Constant Contact, various newsletter formats)

All tests validate privacy patterns defined in `backend/config/privacy_patterns.py`.

**Run tests:**

```bash
cd backend
uv run python -m unittest tests.test_sanitization
uv run python -m unittest tests.test_sanitization_comprehensive
uv run python -m unittest tests.test_user_cases
```

### Notification Testing

Test rule matching against recent newsletters:

```bash
uv run python -m notifications.test_matcher          # Dry run
uv run python -m notifications.test_matcher --queue  # Actually queue notifications
```

## Deployment

- **Backend**: Manual local execution of ingestion scripts (not automated)
- **Frontend**: Auto-deploys via Cloudflare Pages on push to main branch
- **Notifications**: Can be automated via GitHub Actions (daily cron) or local cron job

## Documentation

- **[README.md](../README.md)** - Project overview, quick start, commands
- **[backend/SCHEMA.md](backend/SCHEMA.md)** - Complete database schema with RLS policies, migrations, useful queries
- **Topic definitions**: See `backend/processing/llm_processor.py:TOPICS`
- **Privacy patterns**: See `backend/config/privacy_patterns.py`

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

### Testing & Validation Requirements

All new features must have clear, useful tests that validate correctness. Tests are not optional - they're part of the feature. Always run tests to validate changes before considering work complete.

**Backend**: Write unit tests for business logic, integration tests for data flows. Tests live in `backend/tests/`.

**Frontend**: Write unit tests for logic (utilities, data transforms, component behavior). Use ChromeDevTools MCP server to validate UI/styling changes (snapshots, layouts, interactions). Run `npm run lint` to validate code quality.

**Pattern**: Feature isn't done until tests prove it works. Use tests to prevent regressions, not just to check boxes.

### Production-Grade Code Quality

Code must be maintainable, readable, and understandable. Always choose production-grade patterns over quick hacks. Code is read far more than it's written - optimize for the next developer.

**Python Code Quality**: After making any Python changes, run `uv run ruff check --fix` and `uv run ruff format`. Fix any issues flagged by the checker before considering work complete.

**Frontend Code Quality**: After making any frontend changes, run `npm run lint`. Fix any issues flagged by ESLint before considering work complete.

**Never**:

- Ship hacky solutions or temporary workarounds
- Leave TODOs or commented-out code in production
- Use magic numbers or unclear abbreviations
- Write code only you can understand
- Don't overengineer things when a cleaner pattern exists

**Always**:

- Use clear, self-documenting code with meaningful names
- Follow established patterns in the codebase
- Write code that's easy to debug and modify
- Consider maintainability and long-term consequences

**Standard**: Every line of code should be production-ready. No shortcuts, no "fix it later", no clever tricks that obscure intent.

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

### Documentation Maintainability

Documentation should be concise and point to source code instead of duplicating implementation details.

**Avoid**:

- Specific counts that change ("23 topics", "40+ tests", "max 5 rules")
- Implementation details duplicated from code (topic lists, pattern counts, exact scoring ranges)
- File-by-file structure listings

**Prefer**:

- High-level descriptions with references ("See `llm_processor.py:TOPICS` for topic definitions")
- Directory-level structure explanations
- Links to actual code files for details
- Focus on concepts and patterns, not specifics

**Good**: "Tests validate privacy patterns defined in `backend/config/privacy_patterns.json`"
**Bad**: "Tests validate 18 URL patterns, 9 text patterns, and 6 CSS selectors for privacy filtering"

**Reason**: Numbers and implementation details go stale. References to actual code always stay accurate.

### Documentation Updates

Update documentation when making significant changes. Be concise - only document what's necessary, avoid redundant explanations.

**Files to update:**

- **CLAUDE.md** - Architecture changes, new env vars, new patterns
- **README.md** - User-facing setup/feature changes
- **backend/SCHEMA.md** - **REQUIRED** for any database changes

**Principle**: Keep docs synchronized with reality. Update immediately after changes while context is fresh. Don't add fluff - if it doesn't add clarity, don't write it.
