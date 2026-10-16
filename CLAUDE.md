# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Chicago Alderman Newsletter Tracker: A searchable archive of newsletters from Chicago aldermen, built for Strong Towns Chicago. The system ingests newsletters via Gmail IMAP and web scraping, processes them with LLM for topic extraction and summarization, and presents them through an Astro frontend.

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

# Process newsletters with LLM (add/update metadata)
uv run python -m utils.process_llm_metadata --latest 10
uv run python -m utils.process_llm_metadata --source-id 5
uv run python -m utils.process_llm_metadata --dry-run --latest 10
uv run python -m utils.process_llm_metadata --missing-metadata --latest 50
uv run python -m utils.process_llm_metadata --latest 10 --queue-notifications

# Reapply privacy sanitization to existing newsletters
uv run python -m utils.reprocess_newsletters_privacy <newsletter_id> --update
uv run python -m utils.reprocess_newsletters_privacy --all --update --quiet

# Replay emails from senders mapped after arrival (dry run; --apply marks them unread for next ingestion)
uv run python -m utils.replay_unprocessed_emails [--source-id 28] [--since 2026-09-01] [--apply]

# Test notification rule matching (dry run)
uv run python -m notifications.test_matcher

# Test matching and queue notifications
uv run python -m notifications.test_matcher --queue

# Send daily digest emails (dry run)
uv run python -m notifications.process_notification_queue --daily-digest --dry-run

# Send yesterday's digest (default behavior)
uv run python -m notifications.process_notification_queue --daily-digest

# Send specific date's digest
uv run python -m notifications.process_notification_queue --daily-digest --batch-id 2026-01-21

# Weekly Reports
uv run python -m utils.process_weekly_reports            # Generate reports (previous week)
uv run python -m utils.process_weekly_reports --current-week  # Generate for current week (manual Sunday runs)
uv run python -m notifications.weekly_notification_queue # Queue notifications
uv run python -m notifications.process_notification_queue --weekly-digest # Send emails

# Test/iterate on weekly summary prompt (without full pipeline)
uv run python -m utils.test_weekly_summary --sample                     # Test with sample data

# LLM Token Cost Analysis
uv run python -m utils.calculate_token_costs --list-models              # List available models
uv run python -m utils.calculate_token_costs --latest 10 --model gpt-5,claude-sonnet-4.5,gemini-2.5-pro  --include-weekly

# Analytics dashboard data (writes committed JSON to frontend/public/analytics-data/ for /analytics)
uv run python -m utils.compute_analytics                  # Fetch only new newsletters into the local snapshot, then compute
uv run python -m utils.compute_analytics --offline        # Compute from the snapshot; no database access
uv run python -m utils.compute_analytics --full-refresh   # Rebuild the snapshot from every newsletter (heavy; rarely)
uv run python -m utils.compute_analytics --min-term-newsletters 30 --output-dir <dir>

# Run all tests
uv run python -m unittest discover -s tests

# Run tests with performance timing
uv run python utils/time_tests.py

# Code quality checks (run before committing Python changes)
uv run ruff check --fix
uv run ruff format
uv run mypy .
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

# Run E2E tests (Playwright)
npm run test:e2e -- --project=chromium

# /analytics E2E on fixture data (own dev server on port 4358, placeholder Supabase env)
npm run test:e2e:analytics

# Run tests with coverage
npm run test:coverage

# Run tests in watch mode
npm run test:watch

# Run linting
npm run lint
```

### LLM Setup (one-time)

```bash
# Option A: Ollama (local inference)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gpt-oss:20b

# Option B: OpenAI (cloud)
# Set OPENAI_API_KEY in backend/.env, then use --model openai:gpt-5
```

## Automation

**GitHub Actions Workflows:**

- Backend CI (`.github/workflows/backend_tests.yml`) - Runs ruff, mypy, and tests on backend changes
- Frontend CI (`.github/workflows/frontend_tests.yml`) - Runs linting and unit tests on frontend changes
- Email ingestion (`.github/workflows/email_ingestion.yml`) - Polls Gmail, stores newsletters, generates summaries and topics (`ENABLE_LLM` and `LLM_MODEL` repository secrets), queues notifications
- Notification sending (`.github/workflows/send_notifications.yml`) - Sends daily digest emails

All workflows support manual triggering via Actions tab. See workflow files for schedules and configuration details.

**LLM Processing:** Email ingestion in GitHub Actions summarizes each newsletter as it is stored, so new newsletters have their summary and topics from the start. Run `process_llm_metadata` locally only to backfill or reprocess (e.g. newsletters stored without metadata, prompt changes):

```bash
uv run python -m utils.process_llm_metadata --missing-metadata --latest 50
```

See `backend/docs/LOCAL_LLM_PROCESSING.md` for full guide.

## Architecture

### Data Flow

1. **Ingestion**: Emails arrive via Gmail IMAP polling OR web scraping from MailChimp archives
2. **Source Matching**: Email patterns matched against `email_source_mappings` table with wildcard support
3. **Storage**: Raw newsletters stored in `newsletters` table (plain_text, raw_html, metadata)
4. **LLM Processing**: Two LLM calls per newsletter for topic extraction and summarization. Provider dispatched via `llm_client.py` (supports Ollama and OpenAI)
5. **Weekly Synthesis**: Aggregated analysis of newsletters by topic using two-phase LLM process (extract facts → synthesize summary)
6. **Frontend**: Astro SSR queries Supabase for search/display

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
│   ├── llm_client.py             # Multi-provider LLM dispatch (Ollama + OpenAI adapters)
│   └── llm_processor.py          # LLM topic extraction and summarization with Pydantic schemas
├── notifications/
│   ├── rule_matcher.py           # Match newsletters to user notification rules
│   ├── email_sender.py           # Send digest emails via Resend API
│   ├── digest_data.py            # Group, fetch and format digest content
│   ├── digest_html.py            # HTML digest bodies (digest_text.py: plain text)
│   ├── process_notification_queue.py  # Daily digest orchestration
│   ├── test_matcher.py           # Testing utility for rule matching
│   └── error_logger.py           # Timestamped error logging
├── analytics/                    # Pure metric logic for the local analytics dashboard (no I/O)
├── utils/
│   ├── compute_analytics.py      # Refresh snapshot → compute → write analytics JSON for /analytics (tuning and lens switches)
│   ├── analytics_snapshot.py     # Read/write the local analytics snapshot (backend/data/, gitignored)
│   ├── analytics_snapshot_refresh.py  # Fetch new rows into the snapshot in small paused pages
│   ├── analytics_output.py       # Write analytics JSON and print the console summary
│   ├── process_llm_metadata.py   # Add/update LLM metadata (topics, summary)
│   ├── reprocess_newsletters_privacy.py  # Reapply privacy sanitization to existing newsletters
│   ├── migrate_topics.py         # Topic migration utility
│   └── download_samples.py       # Download sample newsletters for testing
├── tests/
│   ├── unit/                     # Unit tests
│   ├── integration/              # Integration tests
│   └── fixtures/                 # Test data and fixtures
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
│   ├── wards.astro               # Ward directory (all wards and their aldermen)
│   ├── ward/[ward].astro         # Per-ward page: alderman contact info + paginated newsletters
│   ├── preferences.astro         # User notification preferences (protected route)
│   ├── unsubscribe.astro         # One-click unsubscribe confirmation page
│   ├── newsletter/[id].astro     # Newsletter detail view
│   ├── analytics.astro           # Analytics dashboard (in the nav)
│   ├── api/search-timeline.ts    # Edge-cached monthly match counts for the /search timeline
│   └── api/notifications/        # Notification management API routes
│       ├── create-rule.ts        # Create notification rule
│       ├── update-rule.ts        # Update existing rule
│       ├── delete-rule.ts        # Delete rule
│       ├── update-preferences.ts # Toggle notifications on/off
│       ├── unsubscribe.ts        # Handle token-based unsubscribe
│       └── validate-unsubscribe-token.ts # Validate JWT token
├── e2e/                          # Playwright E2E tests
├── tests/                        # Vitest unit tests
│   ├── unit/                     # Utility tests (supabase.test.ts)
│   ├── api/                      # API route tests (auth.test.ts, notifications.test.ts)
│   ├── middleware.test.ts        # Middleware logic tests
│   ├── helpers.ts                # Test factories for mocking Astro context
│   └── mocks/                    # Global mocks (astro:middleware)
├── layouts/
│   └── Layout.astro              # <head>/SEO tags + site header, single <main>, and footer for every page
├── components/
│   ├── SiteHeader.astro          # Site name, tagline, primary nav, AuthButton
│   ├── SiteFooter.astro          # Strong Towns Chicago credit + source link
│   ├── NewsletterCard.astro      # Reusable card component
│   ├── preferences/              # Rule list and add/edit rule modal for /preferences
│   └── AuthButton.astro          # Auth UI
├── scripts/
│   ├── analytics-dashboard.ts    # Client wiring for /analytics (view layout, rendering, URL state, events)
│   ├── analytics/                # Its panels (panels/), summary tiles, filter bar, PNG export, render state
│   └── rule-modal.ts             # Client wiring for the /preferences rule modal
└── lib/
    ├── analytics.ts              # Pure dashboard aggregations: data shapes, dates, filters, coverage window
    ├── analytics-terms.ts        # Pure term explorer lookups and counts
    ├── analytics-reach.ts        # Pure ward reach per topic and the topic × ward grid
    ├── analytics-coverage.ts     # Pure archive coverage and sending gaps
    ├── analytics-search-links.ts # Dashboard → /search links
    ├── analytics-format.ts       # Text formats shared by charts, tables and tiles
    ├── analytics-ward-profile.ts # Pure per-ward profile (cadence, topics by month, city reference)
    ├── analytics-topic-trends.ts # Pure topic overview: reach vs each topic's average, swing order, headline topics
    ├── analytics-url-state.ts    # Dashboard view ⇄ query string (invalid params ignored)
    ├── analytics-views.ts        # Selection → overview/topic/ward view and its panel order
    ├── analytics-descriptions.ts # Dashboard text built from the data and its rules
    ├── chart-export.ts           # Chart → PNG with title, window, caption, data date, caveat
    ├── charts/                   # Observable Plot chart builders, one module per chart family (common.ts: shared setup)
    ├── analytics-data.ts         # Fetches the static analytics JSON (missing/failed states, lazy term index)
    ├── page-cache.ts             # Edge cache rules for public SSR pages (used by middleware.ts)
    ├── site.ts                   # Site-wide strings/URLs, primary nav items, active-nav matching
    ├── supabase.ts               # Supabase client + TypeScript interfaces + notificationsEnabled() helper
    ├── wards.ts                  # Pure ward helpers (param validation, directory grouping, contact links)
    ├── ward-queries.ts           # Supabase queries for ward pages
    └── supabase-admin.ts         # Server-side ONLY privileged Supabase client
```

### Database Schema

**Core Tables:** `sources` (aldermen/officials), `email_source_mappings` (pattern matching), `newsletters` (content with full-text search)

**Notification Tables:** `user_profiles`, `notification_rules`, `notification_queue`, `notification_history`, `weekly_topic_reports`

**Full schema and RLS policies:** See [backend/SCHEMA.md](backend/SCHEMA.md)

### Key Design Patterns

**Email Source Matching** (`email_parser.py:lookup_source_by_email()`): Each pattern must match the whole sender address, case-insensitively; `%` is a wildcard anywhere in the pattern (e.g., `%@40thward.org`), and `_` is a literal character. See `email_parser.py:email_matches_pattern()`.

**Web Scraping Strategy Pattern** (`scraper_strategies.py`): Strategy pattern for different archive formats. `get_strategy_for_url()` selects between `MailChimpArchiveStrategy` (most common) and `GenericListStrategy` fallback.

**LLM Processing** (`llm_processor.py` + `llm_client.py`): Two sequential LLM calls per newsletter for topic extraction and summarization using Pydantic models for structured output validation. Provider-agnostic: supports Ollama (local) and OpenAI (cloud) via provider-prefixed model strings (e.g., `openai:gpt-5`, `ollama:gpt-oss:20b`). Bare model names default to Ollama for backward compatibility. Filters extracted topics against predefined list to prevent hallucinations. See `backend/processing/llm_client.py` for provider dispatch logic.

**Search Filters** (`frontend/src/lib/search-filters.ts`): The search page parses URL params into a validated `SearchFilters` object (invalid values are dropped, never thrown), then `applySearchFilters()` is applied to both the count and data queries so they always filter identically. `buildSearchBaseUrl()` serializes filters back for pagination. Date filters are inclusive Chicago calendar days (`chicago-dates.ts`). Topic options come from `lib/topics.ts`, not from the database.

**Search Timeline** (`lib/search-timeline.ts`, `components/SearchTimeline.astro`): a month strip of matching newsletters above `/search` results. Counts come from the `search_term_timeline` RPC (`backend/migrations/007_search_term_timeline.sql`, same matching as search) via `/api/search-timeline`, edge-cached per query; ward, source and topic filters don't apply, and date ranges are applied in the browser so they stay out of the cache key. If the RPC fails, the card is removed.

**Page Cache** (`lib/page-cache.ts`, wired in `middleware.ts`): anonymous GETs of allowlisted SSR pages are cached with the Workers Cache API (Pages Functions skip the CDN cache, so `Cache-Control` alone does nothing), checked before any session or database work. Signed-in visitors bypass it. The allowlist and lifetimes are `PAGE_CACHE_RULES`; a page keeps a failed load out with `UNCACHEABLE_PAGE_CACHE_CONTROL`. The key includes the build id, so each deploy starts empty: privacy fixes and deletions stay visible on cached pages until the next deploy or the lifetime expires.

**Site Layout** (`frontend/src/layouts/Layout.astro`): Pages render only their own content; the layout supplies the shared header, nav, and footer and wraps the page in the single `<main>`. Each page owns exactly one `<h1>` (the site name in the header is a link, not a heading). Add nav sections in `lib/site.ts`, not in page markup.

**Newsletter Deduplication**: Both ingest paths check for existing `email_uid` (email) or URL+subject combination (scraping) before inserting.

**Ward Pages** (`frontend/src/pages/ward/[ward].astro`, `lib/wards.ts`): URLs are keyed by ward number (stable) rather than alderman (changes). Invalid wards respond 404; a ward with several `alderman` sources shows all of them and merges their newsletters. Ward pages are server-rendered, so they are listed in the sitemap by `pages/sitemap-wards.xml.ts`.

**Notification System** (`notifications/`):

- `rule_matcher.py` - Matches newsletters against user rules (topics, search terms, wards). All filters AND-ed, within categories OR-ed. **Ward filters only apply to daily digest notifications.**
- `email_sender.py` - Sends daily and weekly digests via Resend API; `digest_data.py` prepares their content and `digest_html.py`/`digest_text.py` render it
- `process_notification_queue.py` - Orchestrates digest sending, groups by user, updates queue status, records in history
- `weekly_notification_queue.py` - Queues weekly topic report notifications (topic-based only, no ward filtering)
- Integration: Email ingestion queues notifications when `ENABLE_NOTIFICATIONS=true`. Web scraping does NOT trigger notifications (intentional). Failures don't break ingestion.

**Notification Types:**

- **Daily Digest**: Real-time alerts when newsletters match user criteria (topics, keywords, wards). Supports ward filtering.
- **Weekly Summary**: Citywide topic reports delivered every Monday. Always covers all wards - ward filters are not supported for weekly summaries.

**Analytics Dashboard** (`/analytics`, public): `utils/compute_analytics.py` computes metrics from a local newsletter snapshot (gitignored `backend/data/analytics_snapshot/`; modes in its docstring) with the pure functions in `backend/analytics/`, and writes JSON to the committed `frontend/public/analytics-data/` and `frontend/src/data/`. **Refresh workflow:** run it, commit both folders, push. **Production DB:** full-table reads have exhausted its disk IO budget before, so analysis and agents use `--offline`; `--full-refresh` only on a fresh checkout or after old rows' text changes. Tuning constants and switches live at the top of `compute_analytics.py`. The page renders no data on the server: its browser script fetches the JSON at runtime (`lib/analytics-data.ts`; register new files in `AnalyticsDataFiles`) and aggregates client-side in `lib/analytics*.ts`.

Subjects come from **keyword lenses** (reviewed phrase lists in `analytics/lenses.py`, matched by `analytics/lens_matching.py`), not LLM topics; analytics deliberately ignores LLM topics and the relevance score. The page calls lenses "topics": keep "lens" out of user-facing copy. The headline metric is **ward reach**: wards mentioning a topic out of wards with readable newsletters that month.

**Framing rules** (dashboard, ward summaries, reports): show ward counts with their denominator, compare a ward only with its own history and the average of active wards, never rank aldermen or list wards missing from a month.

**Views and sharing:** the view lives in the query string (`lib/analytics-url-state.ts`, `lib/analytics-views.ts`). PNG exports (`lib/chart-export.ts`) carry the window, data date, caveat and production URL. `npm run test:e2e:analytics` runs the dashboard on fixture data with off-origin requests aborted; Frontend CI runs it.

**Ward Summaries and Monthly Reports** (public, indexed): built by `analytics/ward_glance.py` and `monthly_reports.py` into `frontend/src/data/`. `ward-glance.json` is bundled into the worker (`components/WardGlance.astro`), so keep it small. `pages/reports/` are prerendered from `monthly-reports.json` (no DB) and excluded from the worker in `astro.config.mjs`. Reports cover only complete months. Distinctive and rising terms stay on the dashboard: they surface personal names and filler words.

**Privacy Sanitization** (`email_parser.py:sanitize_content()`): Config-driven filtering using `backend/config/privacy_patterns.py` (URL patterns, text patterns, CSS selectors defined as Python constants). Pure function receives patterns as parameter for testability. Links with images unwrapped; text-only privacy links removed. See `backend/tests/test_sanitization*.py` for test coverage.

**Newsletter Content Storage** (`newsletters` table): Both `plain_text` and `raw_html` columns serve distinct, critical purposes:

- **`plain_text`** - Primary format for all processing:
  - Powers full-text search via generated `search_vector` column (combined with subject)
  - Required input for all LLM operations (topic extraction and summarization via `llm_processor.py`)
  - Used for notification rule keyword matching (`rule_matcher.py`)
  - Fallback display when HTML unavailable
  - Generated from email plain text body or HTML-to-text conversion (`html2text`)

- **`raw_html`** - Display-only format:
  - Used solely for formatted frontend presentation (`newsletter/[id].astro`)
  - Preserves original newsletter styling and layout

Both formats are independently sanitized during ingestion for privacy protection. Without `plain_text`, search, LLM features, and notification matching would be non-functional.

**Secure One-Click Unsubscribe**:

- **JWT-based Tokens**: Backend generates `HS256` JWTs containing `user_id` and `exp` using `PyJWT`.
- **Stateless Verification**: Frontend validates tokens using `jose` without DB lookups for validation.
- **Privileged Update**: Unsubscribe action uses a server-side-only `supabase-admin` client (bypassing RLS) initialized with `SUPABASE_SERVICE_KEY`. This key is never exposed to the client.

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
LLM_MODEL=gpt-oss:20b              # Supports provider prefix: openai:gpt-5, ollama:gpt-oss:20b
OLLAMA_MODEL=gpt-oss:20b           # Legacy fallback (LLM_MODEL takes precedence)
OPENAI_API_KEY=sk-...              # Required when using openai: provider prefix

# Notifications (optional, default: false)
ENABLE_NOTIFICATIONS=true        # Enables notification queuing during email ingestion
RESEND_API_KEY=re_xxxxx         # Resend API key for sending digest emails
NOTIFICATION_FROM_EMAIL=noreply@yourdomain.com  # Must be verified in Resend
FRONTEND_BASE_URL=your_base_url  # Optional, for preference links
UNSUBSCRIBE_SECRET_KEY=long_random_string  # For signing unsubscribe JWTs

# Privacy (optional)
PRIVACY_STRIP_PHRASES=           # Comma-separated phrases to redact (e.g., "John Doe,personal@example.com")
```

**Frontend** (`.env` in `frontend/`):

```
PUBLIC_SUPABASE_URL=
PUBLIC_SUPABASE_ANON_KEY=
PUBLIC_ENABLE_NOTIFICATIONS=
# Server-side only variables (not exposed to client)
SUPABASE_SERVICE_KEY=      # For privileged actions like unsubscribe
UNSUBSCRIBE_SECRET_KEY=         # Must match backend key
```

## Testing

**Backend**: Tests in `backend/tests/` organized into `unit/` and `integration/` subdirectories. Run all tests with `uv run python -m unittest discover -s tests` or target specific modules (see Common Commands section).

**Frontend**: Tests in `frontend/src/tests/` using Vitest. Run with `npm run test` (see Common Commands section).

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

### Import Path Discipline

Always use proper Python module execution patterns. Never manipulate sys.path.

### Modern Python Type Hints

Use modern Python 3.10+ type hint syntax. Never use legacy typing module imports when built-in types are available.

**Always use**:

- Pipe union: `str | None` instead of `Optional[str]`
- Built-in types: `list[str]`, `dict[str, int]` instead of `List[str]`, `Dict[str, int]`
- Remove unused typing imports: Don't import `Optional`, `List`, `Dict`

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
