# Chicago Newsletter Aggregator

Searchable archive of newsletters from Chicago aldermen, city agencies, and elected officials. Built for [Strong Towns Chicago](https://www.strongtownschicago.org/).

## Tech Stack

- **Frontend**: Astro v5 + Tailwind CSS v4 + Cloudflare Pages
- **Backend**: Python 3.x + uv package manager
- **Database**: Supabase PostgreSQL
- **Email**: Gmail IMAP polling
- **LLM**: Ollama for summarization/categorization

## Features

- Email ingestion via IMAP with source auto-matching
- LLM processing: topic extraction, summarization, relevance scoring (0-10)
- Full-text search with filters (ward, source type, topic)
- Real-time updates (no rebuild needed)

## Database Schema

```sql
-- Sources: aldermen, agencies, elected officials
CREATE TABLE public.sources (
  id SERIAL PRIMARY KEY,
  source_type TEXT NOT NULL,
  name TEXT NOT NULL,
  email_address TEXT,
  website TEXT,
  signup_url TEXT,
  ward_number TEXT,
  phone TEXT,
  UNIQUE(source_type, name)
);

CREATE INDEX idx_sources_ward_number ON sources(ward_number);
CREATE INDEX idx_sources_phone ON sources(phone);

-- Email pattern matching for source identification
CREATE TABLE public.email_source_mappings (
  id SERIAL PRIMARY KEY,
  email_pattern TEXT NOT NULL,
  source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  notes TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_email_source_mappings_pattern ON email_source_mappings(email_pattern);

-- Newsletters
CREATE TABLE public.newsletters (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  created_at TIMESTAMPTZ DEFAULT NOW(),
  email_uid TEXT NOT NULL UNIQUE,
  received_date TIMESTAMPTZ NOT NULL,
  subject TEXT NOT NULL,
  from_email TEXT NOT NULL,
  to_email TEXT,
  raw_html TEXT,
  plain_text TEXT,
  summary TEXT,
  topics TEXT[],
  entities JSONB,
  source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE SET NULL,
  relevance_score INTEGER CHECK (relevance_score >= 0 AND relevance_score <= 10),
  search_vector TSVECTOR GENERATED ALWAYS AS (
    to_tsvector('english', COALESCE(subject, '') || ' ' || COALESCE(plain_text, ''))
  ) STORED
);

CREATE INDEX newsletters_received_date_idx ON newsletters(received_date DESC);
CREATE INDEX newsletters_topics_idx ON newsletters USING GIN(topics);
CREATE INDEX idx_newsletters_source_id ON newsletters(source_id);
CREATE INDEX idx_newsletters_search ON newsletters USING GIN(search_vector);
CREATE INDEX idx_newsletters_relevance ON newsletters(relevance_score);

-- Row Level Security (for public read access)
ALTER TABLE sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE newsletters ENABLE ROW LEVEL SECURITY;
ALTER TABLE email_source_mappings ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read sources" ON sources FOR SELECT USING (true);
CREATE POLICY "Public read newsletters" ON newsletters FOR SELECT USING (true);
CREATE POLICY "Public read mappings" ON email_source_mappings FOR SELECT USING (true);
```

## Quick Start

### Backend Setup

```bash
cd backend
uv add imap-tools supabase python-dotenv html2text ollama pydantic

# Create .env with:
# GMAIL_ADDRESS, GMAIL_APP_PASSWORD
# SUPABASE_URL, SUPABASE_SERVICE_KEY
# ENABLE_LLM=true, OLLAMA_MODEL=gpt-oss:20b

uv run python main.py
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
  ├── main.py              # Email ingestion
  ├── email_parser.py      # Email → database
  └── llm_processor.py     # Topic/summary/scoring

frontend/
  ├── src/pages/
  │   ├── index.astro           # Homepage
  │   ├── search.astro          # Search
  │   └── newsletter/[id].astro # Detail
  └── lib/supabase.ts
```

## LLM Processing

Three separate Ollama queries per newsletter:

1. **Topic extraction**: Classifies into 23 predefined topics, filters hallucinations
2. **Summarization**: Generates 2-3 sentence summary
3. **Relevance scoring**: Scores 0-10 for Strong Towns Chicago priorities

## Deployment

- **Backend**: Cron job locally running `main.py` every 15 minutes
- **Frontend**: Auto-deploy via Cloudflare Pages

## Environment Variables

**Backend (.env)**:

```
GMAIL_ADDRESS=
GMAIL_APP_PASSWORD=
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
ENABLE_LLM=true
OLLAMA_MODEL=gpt-oss:20b
```

**Frontend (.env)**:

```
PUBLIC_SUPABASE_URL=
PUBLIC_SUPABASE_ANON_KEY=
```
