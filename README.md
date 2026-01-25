# Chicago Alderman Newsletter Tracker

Searchable archive of newsletters from Chicago aldermen. Built for [Strong Towns Chicago](https://www.strongtownschicago.org/).

## Tech Stack

- **Frontend**: Astro v5 + Tailwind CSS v4 + Cloudflare Pages
- **Backend**: Python 3.x + uv package manager
- **Database**: Supabase PostgreSQL
- **Email**: Gmail IMAP polling
- **LLM**: Ollama for summarization/categorization

## Features

- **Email Ingestion**: Gmail IMAP polling with automatic source matching
- **Web Scraping**: MailChimp archive scraping for historical newsletters
- **LLM Processing**: Topic extraction, summarization, relevance scoring
- **Full-Text Search**: Search with filters (ward, topic, relevance score)
- **User Notifications**: Daily digest emails for newsletters matching user-defined rules (topics, search phrases, wards)
- **Privacy Protection**: Automatic removal of tracking links, unsubscribe URLs, and sensitive content
- **Testing Suite**: Backend unit/integration tests, frontend unit tests

## Database Schema

**Core Tables:**

- `sources` - Aldermen and officials (name, ward, email, archive URLs)
- `email_source_mappings` - Pattern matching for email → source identification
- `newsletters` - Full newsletter content with LLM-extracted metadata (topics, summary, relevance)

**Notification Tables:**

- `user_profiles` - User settings and notification preferences
- `notification_rules` - User-defined alert criteria (topics, search terms, wards)
- `notification_queue` - Pending notifications awaiting delivery
- `notification_history` - Audit log of sent emails

**Full schema details:** See [backend/SCHEMA.md](backend/SCHEMA.md)

## Content Storage

Newsletters are stored in dual formats in the `newsletters` table:

- **`plain_text`** - Primary format used for search indexing, LLM processing (topics, summaries, scoring), and notification keyword matching
- **`raw_html`** - Preserves formatting for frontend display

Both formats are independently sanitized during ingestion to remove tracking links and privacy-sensitive content.

## Quick Start

### Backend Setup

```bash
cd backend
uv sync

# Create .env with:
# GMAIL_ADDRESS, GMAIL_APP_PASSWORD
# SUPABASE_URL, SUPABASE_SERVICE_KEY
# ENABLE_LLM=true, OLLAMA_MODEL=gpt-oss:20b
```

### Backend Scripts

#### Email Ingestion

```bash
# Process unread Gmail newsletters (queues notifications if ENABLE_NOTIFICATIONS=true)
uv run python -m ingest.email.process_emails
```

#### Web Scraping

```bash
# Scrape all aldermen with newsletter_archive_url set
uv run python -m ingest.scraper.process_scraped_newsletters

# Scrape specific source (source_id, archive_url, optional limit)
uv run python -m ingest.scraper.process_scraped_newsletters 1 "https://..." 10
```

#### Utilities

```bash
# Reprocess newsletters with current LLM prompts
uv run python utils/reprocess_newsletters.py --latest 10

# Reapply privacy sanitization to existing newsletters
uv run python utils/reprocess_newsletters_privacy.py --all --update --quiet
```

#### Notifications

```bash
# Test rule matching against recent newsletters (dry run)
uv run python -m notifications.test_matcher

# Test and queue notifications
uv run python -m notifications.test_matcher --queue

# Send daily digest (dry run)
uv run python -m notifications.process_notification_queue --daily-digest --dry-run

# Send today's digest
uv run python -m notifications.process_notification_queue --daily-digest

# Send specific date's digest
uv run python -m notifications.process_notification_queue --daily-digest --batch-id 2026-01-21
```

#### Testing

```bash
# Backend tests
uv run python -m unittest discover -s tests

# Frontend tests
cd ../frontend
npm run test
npm run lint
```

### Frontend Setup

```bash
cd frontend
npm install
npm run dev

# Deploy: push to GitHub, connect to Cloudflare Pages
```

### LLM Setup

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gpt-oss:20b
```

## Project Structure

```
backend/
  ├── ingest/           # Email and web scraping ingestion
  ├── processing/       # LLM topic extraction, summarization, scoring
  ├── notifications/    # User alerts and daily digest delivery
  ├── utils/            # Maintenance scripts (reprocess, migrate, privacy reapply)
  ├── tests/            # Test suite
  │   ├── unit/         # Unit tests
  │   ├── integration/  # Integration tests
  │   └── fixtures/     # Test data and fixtures
  ├── config/           # Privacy patterns configuration
  ├── shared/           # Shared database client and utilities
  └── migrations/       # Database migration SQL files

frontend/
  ├── src/pages/        # Astro pages (index, search, preferences, newsletter detail)
  ├── src/pages/api/    # API routes for notification management
  ├── src/lib/          # Supabase client
  └── tests/            # Frontend unit tests
```

## LLM Processing

Three separate Ollama queries per newsletter for topic extraction, summarization, and relevance scoring. See `backend/processing/llm_processor.py` for implementation details and topic definitions.

## Notification System

Users create alert rules to receive daily digest emails for matching newsletters. Rules support topic-based matching, search phrase matching, and ward filtering.

Email ingestion automatically queues matching notifications when `ENABLE_NOTIFICATIONS=true`. Daily digest sending is handled by `backend/notifications/process_notification_queue.py`.

**Key files:**

- `backend/notifications/rule_matcher.py` - Matching logic
- `backend/notifications/email_sender.py` - Email delivery via Resend
- `frontend/src/pages/preferences.astro` - User preference management

## Privacy & Content Sanitization

Newsletter content is automatically sanitized to remove tracking links, unsubscribe URLs, and sensitive content. Privacy rules are defined as Python constants in `backend/config/privacy_patterns.py` with URL patterns, text patterns, and CSS selectors.

**Implementation:** `backend/ingest/email/email_parser.py:sanitize_content()`
**Tests:** `backend/tests/test_sanitization*.py` and `test_user_cases.py`

## Deployment

- **Email Ingestion**: Automated via GitHub Actions (see `.github/workflows/email_ingestion.yml`)
- **Notification Sending**: Automated via GitHub Actions (see `.github/workflows/send_notifications.yml`)
- **LLM Processing**: Manual local execution with Ollama (see `backend/docs/LOCAL_LLM_PROCESSING.md`)
- **Frontend**: Auto-deploy via Cloudflare Pages on push to main

**GitHub Actions**: Both workflows support manual triggering and require secrets configured in repository Settings → Secrets (see workflow files for details).

## Environment Variables

**Backend (.env)**:

```
# Gmail IMAP
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=

# Supabase
SUPABASE_URL=
SUPABASE_SERVICE_KEY=

# LLM Processing (optional)
ENABLE_LLM=true
OLLAMA_MODEL=gpt-oss:20b

# Notifications (optional)
ENABLE_NOTIFICATIONS=true
RESEND_API_KEY=re_xxxxx
NOTIFICATION_FROM_EMAIL=noreply@yourdomain.com
FRONTEND_BASE_URL=yourbaseurl  # Optional

# Privacy (optional)
PRIVACY_STRIP_PHRASES=  # Comma-separated phrases to redact
```

**Frontend (.env)**:

```
PUBLIC_SUPABASE_URL=
PUBLIC_SUPABASE_ANON_KEY=
PUBLIC_ENABLE_NOTIFICATIONS=
```
