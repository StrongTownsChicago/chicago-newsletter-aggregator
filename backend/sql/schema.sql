-- CHICAGO ALDERMAN NEWSLETTER TRACKER - DATABASE SCHEMA
-- Schema definition for Supabase (PostgreSQL)
-- Updated: 2026-02-01

-- ============================================================================
-- 1. EXTENSIONS & FUNCTIONS
-- ============================================================================

-- Enable necessary extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Auto-update updated_at timestamp
CREATE OR REPLACE FUNCTION public.update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Auto-create user profile on signup
CREATE OR REPLACE FUNCTION public.create_user_profile()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_profiles (id, email)
    VALUES (NEW.id, NEW.email);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER;

-- Helper function: count user rules
CREATE OR REPLACE FUNCTION public.count_user_rules(user_uuid UUID)
RETURNS INTEGER AS $$
    SELECT COUNT(*)::INTEGER
    FROM public.notification_rules
    WHERE user_id = user_uuid;
$$ LANGUAGE SQL STABLE;

-- Helper function: get active weekly topics
CREATE OR REPLACE FUNCTION public.get_active_weekly_topics()
RETURNS TABLE(topic TEXT) AS $$
    SELECT DISTINCT unnest(topics) AS topic
    FROM notification_rules
    WHERE is_active = true
      AND delivery_frequency = 'weekly';
$$ LANGUAGE SQL STABLE;

-- Helper function: get week date range (ISO-8601)
CREATE OR REPLACE FUNCTION public.get_week_date_range(week_id_param TEXT)
RETURNS TABLE(week_start DATE, week_end DATE) AS $$
DECLARE
    year_val INTEGER;
    week_val INTEGER;
    jan_4 DATE;
    week_1_monday DATE;
BEGIN
    -- Parse YYYY-WXX format
    year_val := CAST(SUBSTRING(week_id_param FROM 1 FOR 4) AS INTEGER);
    week_val := CAST(SUBSTRING(week_id_param FROM 7) AS INTEGER);

    -- ISO week 1 is the first week containing a Thursday
    -- January 4th is always in week 1
    jan_4 := MAKE_DATE(year_val, 1, 4);

    -- Find the Monday of week 1
    week_1_monday := jan_4 - CAST(EXTRACT(ISODOW FROM jan_4) - 1 AS INTEGER);

    -- Calculate start and end of target week
    week_start := week_1_monday + CAST((week_val - 1) * 7 AS INTEGER);
    week_end := week_start + 6;

    RETURN NEXT;
END;
$$ LANGUAGE plpgsql STABLE;

-- ============================================================================
-- 2. CORE TABLES
-- ============================================================================

-- SOURCES: Aldermen and other newsletter sources
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
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_sources_ward_number ON public.sources(ward_number);
CREATE INDEX IF NOT EXISTS idx_sources_phone ON public.sources(phone);

-- NEWSLETTERS: Ingested newsletter content
CREATE TABLE public.newsletters (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    created_at TIMESTAMPTZ DEFAULT NOW(),
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
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE SET NULL,
    search_vector TSVECTOR GENERATED ALWAYS AS (
        to_tsvector('english', COALESCE(subject, '') || ' ' || COALESCE(plain_text, ''))
    ) STORED,
    relevance_score INTEGER CHECK (relevance_score >= 0 AND relevance_score <= 10)
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS newsletters_received_date_idx ON public.newsletters(received_date DESC);
CREATE INDEX IF NOT EXISTS newsletters_topics_idx ON public.newsletters USING GIN (topics);
CREATE INDEX IF NOT EXISTS idx_newsletters_source_id ON public.newsletters(source_id);
CREATE INDEX IF NOT EXISTS idx_newsletters_search ON public.newsletters USING GIN (search_vector);
CREATE INDEX IF NOT EXISTS idx_newsletters_relevance ON public.newsletters(relevance_score);

-- EMAIL_SOURCE_MAPPINGS: Pattern matching for incoming emails
CREATE TABLE public.email_source_mappings (
    id SERIAL PRIMARY KEY,
    email_pattern TEXT NOT NULL,
    source_id INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
    notes TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW()
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_email_source_mappings_pattern ON public.email_source_mappings(email_pattern);

-- ============================================================================
-- 3. NOTIFICATION SYSTEM TABLES
-- ============================================================================

-- USER_PROFILES: Extends Supabase Auth users
CREATE TABLE public.user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notification_preferences JSONB NOT NULL DEFAULT '{"enabled": true, "delivery_frequency": "daily"}'::JSONB
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON public.user_profiles(email);

-- WEEKLY_TOPIC_REPORTS: AI-generated summaries for topics
CREATE TABLE public.weekly_topic_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic TEXT NOT NULL,
    week_id TEXT NOT NULL,
    report_summary TEXT NOT NULL,
    newsletter_ids UUID[] NOT NULL,
    key_developments JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT unique_topic_week UNIQUE (topic, week_id)
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_weekly_topic_reports_week ON public.weekly_topic_reports(week_id);
CREATE INDEX IF NOT EXISTS idx_weekly_topic_reports_topic ON public.weekly_topic_reports(topic);
CREATE INDEX IF NOT EXISTS idx_weekly_topic_reports_topic_week ON public.weekly_topic_reports(topic, week_id);

-- NOTIFICATION_RULES: User-defined filters
CREATE TABLE public.notification_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    topics TEXT[] NOT NULL DEFAULT '{}'::TEXT[],
    search_term TEXT,
    min_relevance_score INTEGER,
    source_ids INTEGER[],
    ward_numbers TEXT[],
    delivery_frequency TEXT DEFAULT 'daily' CHECK (delivery_frequency IN ('daily', 'weekly')),
    CONSTRAINT notification_rules_search_term_check CHECK (char_length(search_term) <= 100),
    CONSTRAINT weekly_rules_no_ward_filter CHECK (
        delivery_frequency != 'weekly' OR ward_numbers IS NULL OR array_length(ward_numbers, 1) IS NULL
    )
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_notification_rules_user_id ON public.notification_rules(user_id);
CREATE INDEX IF NOT EXISTS idx_notification_rules_active ON public.notification_rules(user_id, is_active);
CREATE INDEX IF NOT EXISTS idx_notification_rules_frequency ON public.notification_rules(delivery_frequency, is_active);

COMMENT ON CONSTRAINT weekly_rules_no_ward_filter ON public.notification_rules IS
'Weekly summaries cover citywide activity and cannot be filtered by ward. Only daily digest notifications support ward filtering.';

-- NOTIFICATION_QUEUE: Pending notifications
CREATE TABLE public.notification_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    newsletter_id UUID REFERENCES newsletters(id) ON DELETE CASCADE,
    report_id UUID REFERENCES weekly_topic_reports(id) ON DELETE CASCADE,
    rule_id UUID NOT NULL REFERENCES notification_rules(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
    digest_batch_id TEXT,
    notification_type TEXT DEFAULT 'daily' CHECK (notification_type IN ('daily', 'weekly')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    error_message TEXT,
    CONSTRAINT check_one_content_id CHECK (
        (newsletter_id IS NOT NULL AND report_id IS NULL) OR
        (newsletter_id IS NULL AND report_id IS NOT NULL)
    )
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_notification_queue_status ON public.notification_queue(status, created_at);
CREATE INDEX IF NOT EXISTS idx_notification_queue_user ON public.notification_queue(user_id, status);
CREATE INDEX IF NOT EXISTS idx_notification_queue_digest ON public.notification_queue(digest_batch_id, status);
CREATE INDEX IF NOT EXISTS idx_notification_queue_type_status ON public.notification_queue(notification_type, status, created_at);
CREATE INDEX IF NOT EXISTS idx_notification_queue_report ON public.notification_queue(report_id) WHERE report_id IS NOT NULL;

CREATE UNIQUE INDEX idx_unique_newsletter_notif ON public.notification_queue (user_id, newsletter_id, rule_id) WHERE newsletter_id IS NOT NULL;
CREATE UNIQUE INDEX idx_unique_report_notif ON public.notification_queue (user_id, report_id, rule_id) WHERE report_id IS NOT NULL;

-- NOTIFICATION_HISTORY: Audit log of sent notifications
CREATE TABLE public.notification_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    newsletter_ids UUID[] NOT NULL,
    rule_ids UUID[] NOT NULL,
    digest_batch_id TEXT,
    delivery_type TEXT NOT NULL CHECK (delivery_type IN ('immediate', 'daily_digest', 'weekly_digest')),
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    success BOOLEAN NOT NULL,
    error_message TEXT,
    resend_email_id TEXT
) TABLESPACE pg_default;

CREATE INDEX IF NOT EXISTS idx_notification_history_user ON public.notification_history(user_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_history_batch ON public.notification_history(digest_batch_id);
CREATE INDEX IF NOT EXISTS idx_notification_history_success ON public.notification_history(success, sent_at DESC);

-- ============================================================================
-- 4. TRIGGERS
-- ============================================================================

-- Create user profile on auth signup
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW EXECUTE FUNCTION public.create_user_profile();

-- Auto-update timestamps
DROP TRIGGER IF EXISTS update_user_profiles_updated_at ON public.user_profiles;
CREATE TRIGGER update_user_profiles_updated_at
    BEFORE UPDATE ON public.user_profiles
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

DROP TRIGGER IF EXISTS update_notification_rules_updated_at ON public.notification_rules;
CREATE TRIGGER update_notification_rules_updated_at
    BEFORE UPDATE ON public.notification_rules
    FOR EACH ROW EXECUTE FUNCTION public.update_updated_at_column();

-- ============================================================================
-- 5. ROW-LEVEL SECURITY (RLS)
-- ============================================================================

-- USER_PROFILES
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own profile" ON public.user_profiles FOR SELECT USING (auth.uid() = id);
CREATE POLICY "Users can update own profile" ON public.user_profiles FOR UPDATE USING (auth.uid() = id);

-- NOTIFICATION_RULES
ALTER TABLE public.notification_rules ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own rules" ON public.notification_rules FOR SELECT USING (auth.uid() = user_id);
CREATE POLICY "Users can create own rules" ON public.notification_rules FOR INSERT WITH CHECK (auth.uid() = user_id);
CREATE POLICY "Users can update own rules" ON public.notification_rules FOR UPDATE USING (auth.uid() = user_id);
CREATE POLICY "Users can delete own rules" ON public.notification_rules FOR DELETE USING (auth.uid() = user_id);

-- NOTIFICATION_QUEUE
ALTER TABLE public.notification_queue ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own queued notifications" ON public.notification_queue FOR SELECT USING (auth.uid() = user_id);

-- NOTIFICATION_HISTORY
ALTER TABLE public.notification_history ENABLE ROW LEVEL SECURITY;
CREATE POLICY "Users can view own notification history" ON public.notification_history FOR SELECT USING (auth.uid() = user_id);

-- WEEKLY_TOPIC_REPORTS
ALTER TABLE public.weekly_topic_reports ENABLE ROW LEVEL SECURITY;
CREATE POLICY "All authenticated users can view weekly reports" ON public.weekly_topic_reports FOR SELECT TO authenticated USING (true);
CREATE POLICY "Service role can manage weekly topic reports" ON public.weekly_topic_reports FOR ALL TO service_role USING (true) WITH CHECK (true);

-- ============================================================================
-- 6. PERMISSIONS
-- ============================================================================

GRANT EXECUTE ON FUNCTION public.count_user_rules TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_active_weekly_topics TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_active_weekly_topics TO service_role;
GRANT EXECUTE ON FUNCTION public.get_week_date_range TO authenticated;
GRANT EXECUTE ON FUNCTION public.get_week_date_range TO service_role;
