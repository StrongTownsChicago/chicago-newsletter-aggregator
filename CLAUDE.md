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

### All gates (from the repo root)

```bash
# Run CI's gates locally, in CI's order; stops at the first failure
bash scripts/check.sh [backend|frontend]

# Enable the pre-commit hook (once per clone): ruff on staged backend files, mypy and the docstring budget when backend files are staged, ESLint on staged frontend files
git config core.hooksPath .githooks
```

### Backend (from `backend/` directory)

```bash
# Install dependencies
uv sync

# Process unread emails from Gmail (queues notifications if ENABLE_NOTIFICATIONS=true)
uv run python -m cli.process_emails

# Scrape all sources with newsletter_archive_url set
uv run python -m cli.process_scraped_newsletters

# Scrape specific source (source_id, archive_url, optional limit)
uv run python -m cli.process_scraped_newsletters 1 "https://..." 10

# Process newsletters with LLM (add/update metadata)
uv run python -m cli.process_llm_metadata --latest 10
uv run python -m cli.process_llm_metadata --source-id 5
uv run python -m cli.process_llm_metadata --dry-run --latest 10
uv run python -m cli.process_llm_metadata --missing-metadata --latest 50
uv run python -m cli.process_llm_metadata --latest 10 --queue-notifications

# Reapply privacy sanitization to existing newsletters
uv run python -m cli.reprocess_newsletters_privacy <newsletter_id> --update
uv run python -m cli.reprocess_newsletters_privacy --all --update --quiet

# Replay emails from senders mapped after arrival (dry run; --apply marks them unread for next ingestion)
uv run python -m cli.replay_unprocessed_emails [--source-id 28] [--since 2026-09-01] [--apply]

# Test notification rule matching (dry run)
uv run python -m cli.try_rule_matcher

# Test matching and queue notifications
uv run python -m cli.try_rule_matcher --queue

# Send daily digest emails (dry run)
uv run python -m cli.process_notification_queue --daily-digest --dry-run

# Send yesterday's digest (default behavior)
uv run python -m cli.process_notification_queue --daily-digest

# Send specific date's digest
uv run python -m cli.process_notification_queue --daily-digest --batch-id 2026-01-21

# Weekly Reports
uv run python -m cli.process_weekly_reports            # Generate reports (previous week)
uv run python -m cli.process_weekly_reports --current-week  # Generate for current week (manual Sunday runs)
uv run python -m cli.weekly_notification_queue # Queue notifications
uv run python -m cli.process_notification_queue --weekly-digest # Send emails

# Test/iterate on weekly summary prompt (without full pipeline)
uv run python -m cli.try_weekly_summary --sample                     # Test with sample data

# LLM Token Cost Analysis
uv run python -m cli.calculate_token_costs --list-models              # List available models
uv run python -m cli.calculate_token_costs --latest 10 --model gpt-5,claude-sonnet-4.5,gemini-2.5-pro  --include-weekly

# Analytics dashboard data (writes committed JSON to frontend/public/analytics-data/ for /analytics)
uv run python -m cli.compute_analytics                  # Fetch only new newsletters into the local snapshot, then compute
uv run python -m cli.compute_analytics --offline        # Compute from the snapshot; no database access
uv run python -m cli.compute_analytics --full-refresh   # Rebuild the snapshot from every newsletter (heavy; rarely)
uv run python -m cli.compute_analytics --min-term-newsletters 30 --output-dir <dir>

# Run all tests
uv run python -m unittest discover -s tests

# Run tests with performance timing
uv run python -m tools.time_test_suite

# Mutation testing (dev-only, not in CI; minutes per module; targets in the tool)
uv run --group mutation python -m tools.run_mutation_tests [rule_matcher ...]

# Tests with coverage (floor in pyproject.toml)
uv run coverage run -m unittest discover -s tests -p "test_*.py" && uv run coverage report

# Code quality checks (run before committing Python changes)
uv run ruff check --fix
uv run ruff format
uv run mypy .
PYTHONUTF8=1 uv run lint-imports                              # Import contracts (.importlinter)
uv run python -m tools.lint.check_docstrings [--report]       # Docstring budget; --report lists every site
uv run python -m tools.lint.check_module_size [--report]      # Module size ratchet; --update re-records the baseline
uv run python -m tools.lint.check_symbol_reachability [--report]  # Unreachable symbols
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

# E2E without the database: /analytics on fixture data and axe WCAG A/AA scans (e2e/a11y.spec.ts)
# Own dev server on port 4358, placeholder Supabase env; Frontend CI runs it
npm run test:e2e:analytics

# Run tests with coverage (floors in vitest.config.ts)
npm run test:coverage

# Type check (astro check; expects 0 errors)
npm run typecheck

# Run tests in watch mode
npm run test:watch

# Mutation testing with StrykerJS (dev-only, not in CI; narrow with -- --mutate src/lib/wards.ts)
npm run test:mutation

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

- Backend CI (`.github/workflows/backend_tests.yml`) - Runs the backend gates of `scripts/check.sh` on backend changes
- Frontend CI (`.github/workflows/frontend_tests.yml`) - Runs the frontend gates of `scripts/check.sh` (lint, typecheck, unit tests with coverage, build, analytics E2E) on frontend changes
- Email ingestion (`.github/workflows/email_ingestion.yml`) - Polls Gmail, stores newsletters, generates summaries and topics (`ENABLE_LLM` and `LLM_MODEL` repository secrets), queues notifications
- Notification sending (`.github/workflows/send_notifications.yml`) - Sends daily digest emails

All workflows support manual triggering via Actions tab. See workflow files for schedules and configuration details.

**LLM Processing:** Email ingestion in GitHub Actions summarizes each newsletter as it is stored, so new newsletters have their summary and topics from the start. Run `process_llm_metadata` locally only to backfill or reprocess (e.g. newsletters stored without metadata, prompt changes):

```bash
uv run python -m cli.process_llm_metadata --missing-metadata --latest 50
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
├── cli/              # Command-line entry points, each run as `uv run python -m cli.<module>`
├── ingest/           # Email parsing with privacy sanitization; web scraping strategies
├── processing/       # LLM client (Ollama/OpenAI dispatch), topic extraction, weekly reports
├── notifications/    # Rule matching, digest content and rendering, Resend sending
├── analytics/        # Pure metric logic for the analytics dashboard (no I/O)
│   └── io/           # Its snapshot store, snapshot refresh and JSON output
├── llm_costs/        # Token counting and LLM cost estimates
├── models/           # Pydantic models and shared types
├── prompts/          # LLM prompt templates
├── config/           # Privacy patterns (URLs, text, CSS selectors)
├── shared/           # Supabase client singleton, Chicago date helpers
├── tools/            # Dev tooling: lint checks, test timing
├── tests/            # unit/, integration/, fixtures/
└── migrations/       # SQL migrations
```

### Frontend Structure

```
frontend/
├── e2e/                      # Playwright E2E tests
├── public/analytics-data/    # Generated analytics JSON, fetched by the browser
└── src/
    ├── pages/                # Routes; api/ holds server endpoints (auth, notifications, search timeline)
    ├── layouts/              # Layout.astro: <head>/SEO tags, site header, single <main>, footer
    ├── components/           # Astro components; analytics/, preferences/, reports/ by feature
    ├── client/               # Browser-side page wiring; analytics/ is the /analytics dashboard
    ├── lib/                  # Shared helpers: search filters, wards, site, dates, Supabase client and types
    │   ├── analytics/        # Pure dashboard logic; charts/ holds the Observable Plot builders and PNG export
    │   └── server/           # Server-only: service-key client, server env, caches, Supabase queries, sitemap
    ├── generated/            # Generated JSON bundled server-side (ward summaries, monthly reports)
    ├── tests/                # Vitest: unit/, api/, mocks/, helpers
    └── middleware.ts         # Per-request Supabase client, page cache, preview-host noindex
```

### Database Schema

**Core Tables:** `sources` (aldermen/officials), `email_source_mappings` (pattern matching), `newsletters` (content with full-text search)

**Notification Tables:** `user_profiles`, `notification_rules`, `notification_queue`, `notification_history`, `weekly_topic_reports`

**Full schema and RLS policies:** See [backend/SCHEMA.md](backend/SCHEMA.md)

### Key Design Patterns

**Email Source Matching** (`email_parser.py:lookup_source_by_email()`): Each pattern must match the whole sender address, case-insensitively; `%` is a wildcard anywhere in the pattern (e.g., `%@40thward.org`), and `_` is a literal character. See `email_parser.py:email_matches_pattern()`.

**Web Scraping Strategy Pattern** (`scraper_strategies.py`): Strategy pattern for different archive formats. `get_strategy_for_url()` selects between `MailChimpArchiveStrategy` (most common) and `GenericListStrategy` fallback.

**LLM Processing** (`llm_processor.py` + `llm_client.py`): Two sequential LLM calls per newsletter for topic extraction and summarization using Pydantic models for structured output validation. Provider-agnostic: supports Ollama (local) and OpenAI (cloud) via provider-prefixed model strings (e.g., `openai:gpt-5`, `ollama:gpt-oss:20b`). Bare model names default to Ollama for backward compatibility. Filters extracted topics against predefined list to prevent hallucinations. See `backend/processing/llm_client.py` for provider dispatch logic.

**Search Filters** (`frontend/src/lib/search-filters.ts`): The search page parses URL params into a validated `SearchFilters` object (invalid values are dropped, never thrown), then `applySearchFilters()` is applied to both the count and data queries so they always filter identically. `buildSearchBaseUrl()` serializes filters back for pagination. The form shows one search box; the other filters sit in a collapsed "Filters" panel, and `listActiveSearchFilters()` lists applied ones as removable chips. Its single ward dropdown is labelled with aldermen's names; `source` and `source_type` still work from URLs but have no dropdown. Date filters are inclusive Chicago calendar days (`chicago-dates.ts`). Topic options come from `lib/topics.ts`, not from the database; show topics to users with its `formatTopicLabel()`, never the raw id. Digest emails use the matching labels in `backend/notifications/digest_data.py:TOPIC_LABELS`.

**Search Timeline** (`lib/search-timeline.ts`, `components/SearchTimeline.astro`): a month strip of matching newsletters above `/search` results. Counts come from the `search_term_timeline` RPC (`backend/migrations/007_search_term_timeline.sql`, same matching as search) via `/api/search-timeline`, edge-cached per query; ward, source and topic filters don't apply, and date ranges are applied in the browser so they stay out of the cache key. If the RPC fails, the card is removed.

**Page Cache** (`lib/server/page-cache.ts`, wired in `middleware.ts`): anonymous GETs of allowlisted SSR pages are cached with the Workers Cache API (Pages Functions skip the CDN cache, so `Cache-Control` alone does nothing), checked before any session or database work. Signed-in visitors bypass it. The allowlist and lifetimes are `PAGE_CACHE_RULES`; a page keeps a failed load out with `UNCACHEABLE_PAGE_CACHE_CONTROL`. The key includes the build id, so each deploy starts empty: privacy fixes and deletions stay visible on cached pages until the next deploy or the lifetime expires.

**Site Layout** (`frontend/src/layouts/Layout.astro`): Pages render only their own content; the layout supplies the shared header, nav, and footer and wraps the page in the single `<main>`. Each page owns exactly one `<h1>` (the site name in the header is a link, not a heading). Add nav sections in `lib/site.ts`, not in page markup. Page-specific `<head>` tags (e.g. JSON-LD on ward pages, built by `lib/seo.ts`) go in the layout's `head` slot.

**Newsletter Deduplication**: Both ingest paths check for existing `email_uid` (email) or URL+subject combination (scraping) before inserting.

**Ward Pages** (`frontend/src/pages/ward/[ward].astro`, `lib/wards.ts`): URLs are keyed by ward number (stable) rather than alderman (changes). Invalid wards respond 404; a ward with several `alderman` sources shows all of them and merges their newsletters. Ward pages are server-rendered, so they are listed in the sitemap by `pages/sitemap-wards.xml.ts`.

**Notification System** (`notifications/`):

- `rule_matcher.py` - Matches newsletters against user rules (topics, search terms, wards). All filters AND-ed, within categories OR-ed. **Ward filters only apply to daily digest notifications.**
- `email_sender.py` - Sends daily and weekly digests via Resend API; `digest_data.py` prepares their content and `digest_html.py`/`digest_text.py` render it
- `cli/process_notification_queue.py` - Orchestrates digest sending, groups by user, updates queue status, records in history
- `cli/weekly_notification_queue.py` - Queues weekly topic report notifications (topic-based only, no ward filtering)
- Integration: Email ingestion queues notifications when `ENABLE_NOTIFICATIONS=true`. Web scraping does NOT trigger notifications (intentional). Failures don't break ingestion.

**Notification Types:**

- **Daily Digest**: Real-time alerts when newsletters match user criteria (topics, keywords, wards). Supports ward filtering.
- **Weekly Summary**: Citywide topic reports delivered every Monday. Always covers all wards - ward filters are not supported for weekly summaries.

**Analytics Dashboard** (`/analytics`, public): `cli/compute_analytics.py` computes metrics from a local newsletter snapshot (gitignored `backend/data/analytics_snapshot/`; modes in its docstring) with the pure functions in `backend/analytics/`, and writes JSON to the committed `frontend/public/analytics-data/` and `frontend/src/generated/`. **Refresh workflow:** run it, commit both folders, push. **Production DB:** full-table reads have exhausted its disk IO budget before, so analysis and agents use `--offline`; `--full-refresh` only on a fresh checkout or after old rows' text changes. Tuning constants and switches live at the top of `compute_analytics.py`. The page renders no data on the server: its browser script fetches the JSON at runtime (`lib/analytics/data.ts`; register new files in `AnalyticsDataFiles`) and aggregates client-side in `lib/analytics/`.

Subjects come from **keyword lenses** (reviewed phrase lists in `analytics/lenses.py`, matched by `analytics/lens_matching.py`), not LLM topics; analytics deliberately ignores LLM topics and the relevance score. The page calls lenses "topics": keep "lens" out of user-facing copy. The headline metric is **ward reach**: wards mentioning a topic out of wards with readable newsletters that month.

**Framing rules** (dashboard, ward summaries, reports): show ward counts with their denominator, compare a ward only with its own history and the average of active wards, never rank aldermen or list wards missing from a month.

**Views and sharing:** the view lives in the query string (`lib/analytics/url-state.ts`, `lib/analytics/views.ts`). PNG exports (`lib/analytics/charts/export.ts`) carry the window, data date, caveat and production URL. `npm run test:e2e:analytics` runs the dashboard on fixture data with off-origin requests aborted; Frontend CI runs it.

**Ward Summaries and Monthly Reports** (public, indexed): built by `analytics/ward_glance.py` and `monthly_reports.py` into `frontend/src/generated/`. `ward-glance.json` is bundled into the worker (`components/WardGlance.astro`), so keep it small. `pages/reports/` are prerendered from `monthly-reports.json` (no DB) and excluded from the worker in `astro.config.mjs`. Reports cover only complete months. Distinctive and rising terms stay on the dashboard: they surface personal names and filler words.

**Privacy Sanitization** (`email_parser.py:sanitize_content()`): Config-driven filtering using `backend/config/privacy_patterns.py` (URL patterns, text patterns, CSS selectors defined as Python constants). Pure function receives patterns as parameter for testability. Links with images unwrapped; text-only privacy links removed. URLs are matched as a browser follows them (tabs, newlines and percent-escapes removed). `PRIVACY_STRIP_PHRASES` are redacted in text and attribute values (never markup), including phrases split across tags or wrapped across lines; a letter touching a phrase makes it part of a longer word ("Ted" spares "started"), digits and underscores don't (`_Jane Doe_`, `+1312...`). Sanitizing already sanitized content changes nothing, since `reprocess_newsletters_privacy` reapplies it to stored rows. See `backend/tests/unit/test_sanitization*.py`, including Hypothesis properties.

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

**Backend**: Tests in `backend/tests/` organized into `unit/` and `integration/` subdirectories. Run all tests with `uv run python -m unittest discover -s tests` or target specific modules (see Common Commands section). Property-based tests (`test_*_properties.py`) use Hypothesis with the shared settings in `tests/fixtures/property_settings.py`.

**Frontend**: Tests in `frontend/src/tests/` using Vitest. Run with `npm run test` (see Common Commands section). Accessibility: `e2e/a11y.spec.ts` runs axe on each page that renders without the database, at desktop and phone widths; add new pages to its `SCANNED_PAGES`.

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
