-- Migration: Weekly Topic Reports
-- Description: Add weekly topic reports table and update notification_rules for delivery frequency
-- Date: 2026-01-31

-- ============================================================================
-- 1. WEEKLY TOPIC REPORTS TABLE
-- ============================================================================
-- Stores AI-generated weekly summaries for specific topics
-- One report per topic per week, generated when at least one user subscribes

CREATE TABLE IF NOT EXISTS weekly_topic_reports (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    topic TEXT NOT NULL,
    week_id TEXT NOT NULL, -- Format: YYYY-WXX (ISO week number, e.g., "2026-W05")
    report_summary TEXT NOT NULL, -- AI-generated 2-4 paragraph synthesis
    newsletter_ids UUID[] NOT NULL, -- Newsletters analyzed for this report
    key_developments JSONB, -- Optional structured facts from Phase 1 extraction
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Prevent duplicate reports for same topic/week (idempotency)
    CONSTRAINT unique_topic_week UNIQUE (topic, week_id)
);

-- Indexes for efficient querying
CREATE INDEX IF NOT EXISTS idx_weekly_topic_reports_week ON weekly_topic_reports(week_id);
CREATE INDEX IF NOT EXISTS idx_weekly_topic_reports_topic ON weekly_topic_reports(topic);
CREATE INDEX IF NOT EXISTS idx_weekly_topic_reports_topic_week ON weekly_topic_reports(topic, week_id);

-- ============================================================================
-- 2. UPDATE NOTIFICATION_RULES TABLE
-- ============================================================================
-- Add delivery_frequency column to support daily vs weekly digests
-- Defaults to 'daily' for backward compatibility with existing rules

ALTER TABLE notification_rules
ADD COLUMN IF NOT EXISTS delivery_frequency TEXT DEFAULT 'daily'
CHECK (delivery_frequency IN ('daily', 'weekly'));

-- Index for efficient filtering by frequency
CREATE INDEX IF NOT EXISTS idx_notification_rules_frequency
ON notification_rules(delivery_frequency, is_active);

-- ============================================================================
-- 3. UPDATE NOTIFICATION_QUEUE TABLE
-- ============================================================================
-- Make newsletter_id nullable to support weekly report notifications
-- Weekly notifications will store report_id in this field

ALTER TABLE notification_queue
ALTER COLUMN newsletter_id DROP NOT NULL;

-- Add notification_type column to distinguish daily vs weekly notifications
ALTER TABLE notification_queue
ADD COLUMN IF NOT EXISTS notification_type TEXT DEFAULT 'daily'
CHECK (notification_type IN ('daily', 'weekly'));

-- Update index to include notification_type
CREATE INDEX IF NOT EXISTS idx_notification_queue_type_status
ON notification_queue(notification_type, status, created_at);

-- ============================================================================
-- 4. HELPER FUNCTION: GET ACTIVE WEEKLY TOPICS
-- ============================================================================
-- Returns list of topics that have active weekly subscribers
-- Used to optimize report generation (only process topics with subscribers)

CREATE OR REPLACE FUNCTION get_active_weekly_topics()
RETURNS TABLE(topic TEXT) AS $$
    SELECT DISTINCT unnest(topics) AS topic
    FROM notification_rules
    WHERE is_active = true
      AND delivery_frequency = 'weekly';
$$ LANGUAGE SQL STABLE;

-- Grant execute permission to authenticated users and service role
GRANT EXECUTE ON FUNCTION get_active_weekly_topics TO authenticated;
GRANT EXECUTE ON FUNCTION get_active_weekly_topics TO service_role;

-- ============================================================================
-- 5. HELPER FUNCTION: GET WEEK DATE RANGE
-- ============================================================================
-- Converts ISO week ID (YYYY-WXX) to date range for querying newsletters
-- Returns (start_date, end_date) tuple for the week

CREATE OR REPLACE FUNCTION get_week_date_range(week_id_param TEXT)
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

-- Grant execute permission
GRANT EXECUTE ON FUNCTION get_week_date_range TO authenticated;
GRANT EXECUTE ON FUNCTION get_week_date_range TO service_role;

-- ============================================================================
-- 6. ROW-LEVEL SECURITY (RLS)
-- ============================================================================
-- Weekly reports are backend-only (no frontend access needed)
-- Only service role can access (backend processing and email composition)

ALTER TABLE weekly_topic_reports ENABLE ROW LEVEL SECURITY;

-- Service role has full access for backend operations
CREATE POLICY "Service role can manage weekly topic reports"
    ON weekly_topic_reports FOR ALL
    TO service_role
    USING (true)
    WITH CHECK (true);

-- ============================================================================
-- 7. SAMPLE QUERY: FETCH NEWSLETTERS FOR WEEKLY REPORT
-- ============================================================================
-- Example query for fetching newsletters for a topic within a specific week
-- Used by backend report generation code

-- EXAMPLE USAGE:
-- SELECT
--     n.id,
--     n.subject,
--     n.plain_text,
--     n.received_date,
--     s.name AS source_name,
--     s.ward_number
-- FROM newsletters n
-- JOIN sources s ON n.source_id = s.id
-- CROSS JOIN get_week_date_range('2026-W05') AS week_range
-- WHERE 'bike_lanes' = ANY(n.topics)
--   AND n.received_date::DATE BETWEEN week_range.week_start AND week_range.week_end
-- ORDER BY n.received_date DESC;

-- ============================================================================
-- ROLLBACK INSTRUCTIONS (if needed)
-- ============================================================================
-- To undo this migration, run:
--
-- DROP FUNCTION IF EXISTS get_week_date_range(TEXT);
-- DROP FUNCTION IF EXISTS get_active_weekly_topics();
-- DROP INDEX IF EXISTS idx_notification_queue_type_status;
-- ALTER TABLE notification_queue DROP COLUMN IF EXISTS notification_type;
-- ALTER TABLE notification_queue ALTER COLUMN newsletter_id SET NOT NULL;
-- DROP INDEX IF EXISTS idx_notification_rules_frequency;
-- ALTER TABLE notification_rules DROP COLUMN IF EXISTS delivery_frequency;
-- DROP INDEX IF EXISTS idx_weekly_topic_reports_topic_week;
-- DROP INDEX IF EXISTS idx_weekly_topic_reports_topic;
-- DROP INDEX IF EXISTS idx_weekly_topic_reports_week;
-- DROP TABLE IF EXISTS weekly_topic_reports CASCADE;

-- ============================================================================
-- POST-MIGRATION VALIDATION
-- ============================================================================
-- After running this migration, verify:

-- 1. Check that new table exists
-- SELECT COUNT(*) FROM weekly_topic_reports;
-- (Should return 0 initially)

-- 2. Check that delivery_frequency column exists on notification_rules
-- SELECT delivery_frequency, COUNT(*)
-- FROM notification_rules
-- GROUP BY delivery_frequency;
-- (Should show all existing rules have 'daily')

-- 3. Test helper function
-- SELECT * FROM get_active_weekly_topics();
-- (Should return empty set if no weekly rules yet)

-- 4. Test date range function
-- SELECT * FROM get_week_date_range('2026-W05');
-- (Should return week_start = 2026-01-26, week_end = 2026-02-01)

-- 5. Verify indexes created
-- SELECT indexname FROM pg_indexes
-- WHERE tablename = 'weekly_topic_reports';
-- (Should show 3 indexes)
