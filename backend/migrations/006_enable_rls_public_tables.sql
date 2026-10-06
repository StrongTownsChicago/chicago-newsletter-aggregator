-- Migration: Enable RLS on all public tables and codify production policies
-- Description: Brings the published schema in line with the Row Level Security
--              policies running in production, so a fresh deployment is secure.
-- Date: 2026-10-05
--
-- Idempotent: every policy is dropped (IF EXISTS) before being recreated, and
-- ENABLE ROW LEVEL SECURITY is a no-op on tables that already have it. Running
-- this against production changes only the items called out below.
--
-- ============================================================================
-- HOW TO READ THESE POLICIES (do not "fix" them into grants)
-- ============================================================================
-- * Default deny: with RLS enabled, any command that has no permissive policy
--   is denied for anon/authenticated. The public surface is read-only because
--   there are no INSERT/UPDATE/DELETE grants on newsletters, sources, or
--   email_source_mappings.
-- * service_role bypasses RLS entirely (BYPASSRLS), so backend ingestion and
--   notification jobs using SUPABASE_SERVICE_KEY are unaffected by any of this.
-- * "Block non-service inserts/updates" on newsletters use literal FALSE.
--   They are deny-all gates, not grants: every insert fails WITH CHECK and
--   every update matches zero rows. They are redundant with default deny and
--   kept as explicit belt-and-braces.
-- * TO public is the Postgres pseudo-role meaning "every role". Policies whose
--   expression is auth.uid() = <owner column> evaluate to NULL (not true) for
--   anonymous requests, so anon is denied.
--
-- Changes relative to production (all others are no-ops):
--   (a) email_source_mappings: drop "Allow public read access". Only the
--       backend (service key) reads this table; the policy exposed the sender
--       pattern list and notes to anyone holding the anon key. RLS stays on
--       with no policies, making the table service-role only.
--   (b) newsletters: rename "Service role insert newsletters" /
--       "Service role update newsletters" to "Block non-service inserts" /
--       "Block non-service updates". Behavior is unchanged.
--   (c) weekly_topic_reports: drop "All authenticated users can view weekly
--       reports" if present. Older copies of sql/schema.sql declared it, but
--       production never had it and no frontend code reads this table. If
--       weekly reports are ever rendered in the UI, add a read policy
--       deliberately in a new migration.

BEGIN;

-- ============================================================================
-- 1. ENABLE RLS ON ALL PUBLIC TABLES
-- ============================================================================

ALTER TABLE public.sources ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.newsletters ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.email_source_mappings ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.user_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_rules ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_queue ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.notification_history ENABLE ROW LEVEL SECURITY;
ALTER TABLE public.weekly_topic_reports ENABLE ROW LEVEL SECURITY;

-- ============================================================================
-- 2. SOURCES: public read-only
-- ============================================================================

DROP POLICY IF EXISTS "Public read sources" ON public.sources;
CREATE POLICY "Public read sources" ON public.sources
    FOR SELECT TO public USING (true);

-- ============================================================================
-- 3. NEWSLETTERS: public read-only, explicit deny-all write gates
-- ============================================================================

DROP POLICY IF EXISTS "Public read newsletters" ON public.newsletters;
CREATE POLICY "Public read newsletters" ON public.newsletters
    FOR SELECT TO public USING (true);

-- (b) Old misleading names
DROP POLICY IF EXISTS "Service role insert newsletters" ON public.newsletters;
DROP POLICY IF EXISTS "Service role update newsletters" ON public.newsletters;

DROP POLICY IF EXISTS "Block non-service inserts" ON public.newsletters;
CREATE POLICY "Block non-service inserts" ON public.newsletters
    FOR INSERT TO public WITH CHECK (false);

DROP POLICY IF EXISTS "Block non-service updates" ON public.newsletters;
CREATE POLICY "Block non-service updates" ON public.newsletters
    FOR UPDATE TO public USING (false);

-- ============================================================================
-- 4. EMAIL_SOURCE_MAPPINGS: service role only (no policies)
-- ============================================================================

-- (a)
DROP POLICY IF EXISTS "Allow public read access" ON public.email_source_mappings;

-- ============================================================================
-- 5. USER_PROFILES: owner read/update
-- ============================================================================

DROP POLICY IF EXISTS "Users can view own profile" ON public.user_profiles;
CREATE POLICY "Users can view own profile" ON public.user_profiles
    FOR SELECT TO public USING (auth.uid() = id);

DROP POLICY IF EXISTS "Users can update own profile" ON public.user_profiles;
CREATE POLICY "Users can update own profile" ON public.user_profiles
    FOR UPDATE TO public USING (auth.uid() = id);

-- ============================================================================
-- 6. NOTIFICATION_RULES: owner CRUD
-- ============================================================================

DROP POLICY IF EXISTS "Users can view own rules" ON public.notification_rules;
CREATE POLICY "Users can view own rules" ON public.notification_rules
    FOR SELECT TO public USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can create own rules" ON public.notification_rules;
CREATE POLICY "Users can create own rules" ON public.notification_rules
    FOR INSERT TO public WITH CHECK (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can update own rules" ON public.notification_rules;
CREATE POLICY "Users can update own rules" ON public.notification_rules
    FOR UPDATE TO public USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can delete own rules" ON public.notification_rules;
CREATE POLICY "Users can delete own rules" ON public.notification_rules
    FOR DELETE TO public USING (auth.uid() = user_id);

-- ============================================================================
-- 7. NOTIFICATION_QUEUE / NOTIFICATION_HISTORY: owner read-only
-- ============================================================================
-- Writes are performed by backend jobs with the service key.

DROP POLICY IF EXISTS "Users can view own queued notifications" ON public.notification_queue;
CREATE POLICY "Users can view own queued notifications" ON public.notification_queue
    FOR SELECT TO public USING (auth.uid() = user_id);

DROP POLICY IF EXISTS "Users can view own notification history" ON public.notification_history;
CREATE POLICY "Users can view own notification history" ON public.notification_history
    FOR SELECT TO public USING (auth.uid() = user_id);

-- ============================================================================
-- 8. WEEKLY_TOPIC_REPORTS: service role only
-- ============================================================================

-- (c)
DROP POLICY IF EXISTS "All authenticated users can view weekly reports" ON public.weekly_topic_reports;

DROP POLICY IF EXISTS "Service role can manage weekly topic reports" ON public.weekly_topic_reports;
CREATE POLICY "Service role can manage weekly topic reports" ON public.weekly_topic_reports
    FOR ALL TO service_role USING (true) WITH CHECK (true);

COMMIT;
