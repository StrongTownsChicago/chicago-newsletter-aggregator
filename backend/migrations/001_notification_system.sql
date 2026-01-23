-- Migration: Notification System
-- Description: Add user profiles, notification rules, queue, and history tables
-- Date: 2026-01-21

-- ============================================================================
-- 1. USER PROFILES TABLE
-- ============================================================================
-- Extends Supabase auth.users with app-specific data
-- Auto-created via trigger on user signup

CREATE TABLE IF NOT EXISTS user_profiles (
    id UUID PRIMARY KEY REFERENCES auth.users(id) ON DELETE CASCADE,
    email TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    notification_preferences JSONB NOT NULL DEFAULT '{
        "enabled": true,
        "delivery_frequency": "daily"
    }'::jsonb
);

-- Index for faster lookups
CREATE INDEX IF NOT EXISTS idx_user_profiles_email ON user_profiles(email);

-- RLS Policies
ALTER TABLE user_profiles ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own profile"
    ON user_profiles FOR SELECT
    USING (auth.uid() = id);

CREATE POLICY "Users can update own profile"
    ON user_profiles FOR UPDATE
    USING (auth.uid() = id);

-- Service role has full access (no policy needed, bypasses RLS)

-- ============================================================================
-- 2. NOTIFICATION RULES TABLE
-- ============================================================================
-- User-defined alert criteria (topic-based for MVP)
-- Maximum 5 rules per user (enforced at application level)

CREATE TABLE IF NOT EXISTS notification_rules (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT true,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Filter criteria (MVP: topics only)
    topics TEXT[] NOT NULL DEFAULT '{}', -- At least one required for MVP
    keywords TEXT[] DEFAULT '{}', -- Future: Phase 2
    min_relevance_score INTEGER, -- Future: Phase 2 (0-10)
    source_ids INTEGER[], -- Future: Phase 2 (specific aldermen)
    ward_numbers TEXT[] -- Future: Phase 2 (matches sources.ward_number TEXT type)
);

-- Indexes for faster lookups
CREATE INDEX IF NOT EXISTS idx_notification_rules_user_id ON notification_rules(user_id);
CREATE INDEX IF NOT EXISTS idx_notification_rules_active ON notification_rules(user_id, is_active);

-- RLS Policies
ALTER TABLE notification_rules ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own rules"
    ON notification_rules FOR SELECT
    USING (auth.uid() = user_id);

CREATE POLICY "Users can create own rules"
    ON notification_rules FOR INSERT
    WITH CHECK (auth.uid() = user_id);

CREATE POLICY "Users can update own rules"
    ON notification_rules FOR UPDATE
    USING (auth.uid() = user_id);

CREATE POLICY "Users can delete own rules"
    ON notification_rules FOR DELETE
    USING (auth.uid() = user_id);

-- ============================================================================
-- 3. NOTIFICATION QUEUE TABLE
-- ============================================================================
-- Pending notifications waiting to be sent
-- Unique constraint prevents duplicate notifications

CREATE TABLE IF NOT EXISTS notification_queue (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    newsletter_id UUID NOT NULL REFERENCES newsletters(id) ON DELETE CASCADE,
    rule_id UUID NOT NULL REFERENCES notification_rules(id) ON DELETE CASCADE,
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'sent', 'failed')),
    digest_batch_id TEXT, -- Groups notifications for daily digest (format: YYYY-MM-DD)
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    sent_at TIMESTAMPTZ,
    error_message TEXT,

    -- Prevent duplicate notifications
    CONSTRAINT unique_notification UNIQUE (user_id, newsletter_id, rule_id)
);

-- Indexes for faster processing
CREATE INDEX IF NOT EXISTS idx_notification_queue_status ON notification_queue(status, created_at);
CREATE INDEX IF NOT EXISTS idx_notification_queue_user ON notification_queue(user_id, status);
CREATE INDEX IF NOT EXISTS idx_notification_queue_digest ON notification_queue(digest_batch_id, status);

-- RLS Policies
ALTER TABLE notification_queue ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own queued notifications"
    ON notification_queue FOR SELECT
    USING (auth.uid() = user_id);

-- Service role handles INSERT/UPDATE for processing (no user policy needed)

-- ============================================================================
-- 4. NOTIFICATION HISTORY TABLE
-- ============================================================================
-- Audit log of sent notifications

CREATE TABLE IF NOT EXISTS notification_history (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    newsletter_ids UUID[] NOT NULL, -- Array of newsletter IDs in digest
    rule_ids UUID[] NOT NULL, -- Array of rule IDs that matched
    digest_batch_id TEXT, -- Same format as queue: YYYY-MM-DD
    delivery_type TEXT NOT NULL CHECK (delivery_type IN ('immediate', 'daily_digest', 'weekly_digest')),
    sent_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    success BOOLEAN NOT NULL,
    error_message TEXT,
    resend_email_id TEXT -- Resend API email ID for tracking
);

-- Indexes for analytics and debugging
CREATE INDEX IF NOT EXISTS idx_notification_history_user ON notification_history(user_id, sent_at DESC);
CREATE INDEX IF NOT EXISTS idx_notification_history_batch ON notification_history(digest_batch_id);
CREATE INDEX IF NOT EXISTS idx_notification_history_success ON notification_history(success, sent_at DESC);

-- RLS Policies
ALTER TABLE notification_history ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own notification history"
    ON notification_history FOR SELECT
    USING (auth.uid() = user_id);

-- Service role handles INSERT for processing (no user policy needed)

-- ============================================================================
-- 5. AUTO-CREATE USER PROFILE ON SIGNUP
-- ============================================================================
-- Trigger function to create user_profiles record when user signs up

CREATE OR REPLACE FUNCTION create_user_profile()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO public.user_profiles (id, email)
    VALUES (NEW.id, NEW.email);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql SECURITY DEFINER
SET search_path = public;

-- Trigger on auth.users table
DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
CREATE TRIGGER on_auth_user_created
    AFTER INSERT ON auth.users
    FOR EACH ROW
    EXECUTE FUNCTION create_user_profile();

-- ============================================================================
-- 6. UPDATED_AT TIMESTAMP TRIGGERS
-- ============================================================================
-- Auto-update updated_at column on record changes

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to relevant tables
DROP TRIGGER IF EXISTS update_user_profiles_updated_at ON user_profiles;
CREATE TRIGGER update_user_profiles_updated_at
    BEFORE UPDATE ON user_profiles
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_notification_rules_updated_at ON notification_rules;
CREATE TRIGGER update_notification_rules_updated_at
    BEFORE UPDATE ON notification_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- 7. HELPER FUNCTION: COUNT USER RULES
-- ============================================================================
-- Used to enforce 5 rule limit per user at application level

CREATE OR REPLACE FUNCTION count_user_rules(user_uuid UUID)
RETURNS INTEGER AS $$
    SELECT COUNT(*)::INTEGER
    FROM notification_rules
    WHERE user_id = user_uuid;
$$ LANGUAGE SQL STABLE;

-- Grant execute permission to authenticated users
GRANT EXECUTE ON FUNCTION count_user_rules TO authenticated;

-- ============================================================================
-- ROLLBACK (if needed)
-- ============================================================================
-- To undo this migration, run:
-- DROP TRIGGER IF EXISTS on_auth_user_created ON auth.users;
-- DROP FUNCTION IF EXISTS create_user_profile();
-- DROP FUNCTION IF EXISTS update_updated_at_column();
-- DROP FUNCTION IF EXISTS count_user_rules(UUID);
-- DROP TABLE IF EXISTS notification_history CASCADE;
-- DROP TABLE IF EXISTS notification_queue CASCADE;
-- DROP TABLE IF EXISTS notification_rules CASCADE;
-- DROP TABLE IF EXISTS user_profiles CASCADE;
