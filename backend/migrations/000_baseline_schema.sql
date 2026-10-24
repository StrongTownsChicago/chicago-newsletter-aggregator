-- Migration: Baseline schema for the core tables
-- Description: sources, email_source_mappings and newsletters, which were
--              created in the Supabase dashboard before 001 and never written
--              as a migration. Taken from a schema-only dump of production
--              (2026-10-24), so applying 000 through 007 to an empty Supabase
--              database reproduces production's public schema, plus 006,
--              which production hasn't applied yet (backend/SCHEMA.md,
--              "Production status").
--
-- Already applied in production: do not run it there. It is for building a
-- fresh database (local development, tests).
--
-- The policies below are the ones these tables had before 006, which renames
-- the newsletters write gates and drops the email_source_mappings read policy.

BEGIN;

-- ============================================================================
-- 1. SOURCES
-- ============================================================================

CREATE TABLE public.sources (
    id SERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,
    name TEXT NOT NULL,
    email_address TEXT,
    website TEXT,
    signup_url TEXT,
    ward_number TEXT,
    phone TEXT,
    newsletter_archive_url TEXT,
    CONSTRAINT sources_source_type_name_key UNIQUE (source_type, name)
);

CREATE INDEX idx_sources_ward_number ON public.sources (ward_number);
CREATE INDEX idx_sources_phone ON public.sources (phone);

-- ============================================================================
-- 2. EMAIL_SOURCE_MAPPINGS
-- ============================================================================
-- email_pattern matches a whole sender address; % is a wildcard
-- (backend/ingest/email/email_parser.py:email_matches_pattern).

CREATE TABLE public.email_source_mappings (
    id SERIAL PRIMARY KEY,
    email_pattern TEXT NOT NULL,
    source_id INTEGER NOT NULL REFERENCES public.sources (id) ON DELETE CASCADE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_email_source_mappings_pattern ON public.email_source_mappings (email_pattern);

-- ============================================================================
-- 3. NEWSLETTERS
-- ============================================================================
-- source_id is NOT NULL but its foreign key says ON DELETE SET NULL, so
-- deleting a source that still has newsletters fails. That is production's
-- definition, kept as is.

CREATE TABLE public.newsletters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT now(),
    email_uid TEXT UNIQUE,
    received_date TIMESTAMPTZ NOT NULL,
    subject TEXT NOT NULL,
    from_email TEXT,
    to_email TEXT,
    raw_html TEXT,
    plain_text TEXT,
    summary TEXT,
    topics TEXT[],
    entities JSONB,
    source_id INTEGER NOT NULL REFERENCES public.sources (id) ON DELETE SET NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english'::regconfig, COALESCE(subject, '') || ' ' || COALESCE(plain_text, ''))
    ) STORED,
    relevance_score INTEGER CHECK (relevance_score >= 0 AND relevance_score <= 10)
);

CREATE INDEX newsletters_received_date_idx ON public.newsletters (received_date DESC);
CREATE INDEX newsletters_topics_idx ON public.newsletters USING GIN (topics);
CREATE INDEX idx_newsletters_source_id ON public.newsletters (source_id);
CREATE INDEX idx_newsletters_search ON public.newsletters USING GIN (search_vector);
CREATE INDEX idx_newsletters_relevance ON public.newsletters (relevance_score);

-- ============================================================================
-- 4. ROW LEVEL SECURITY (as before 006)
-- ============================================================================

ALTER TABLE public.sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_source_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.newsletters ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Public read sources" ON public.sources
    FOR SELECT USING (true);

CREATE POLICY "Allow public read access" ON public.email_source_mappings
    FOR SELECT USING (true);

CREATE POLICY "Public read newsletters" ON public.newsletters
    FOR SELECT USING (true);

CREATE POLICY "Service role insert newsletters" ON public.newsletters
    FOR INSERT WITH CHECK (false);

CREATE POLICY "Service role update newsletters" ON public.newsletters
    FOR UPDATE USING (false);

COMMIT;
