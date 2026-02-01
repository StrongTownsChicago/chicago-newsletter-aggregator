-- Migration 004: Polymorphic Notifications
-- Add dedicated report_id column to notification_queue to support both newsletters and weekly reports
-- Implements "Option B (Dedicated Columns)" from backend/docs/ARCHITECTURE_POLYMORPHIC_NOTIFICATIONS.md

-- Step 1: Add the new report_id column
ALTER TABLE notification_queue
ADD COLUMN report_id UUID REFERENCES weekly_topic_reports(id) ON DELETE CASCADE;

-- Step 2: newsletter_id is already nullable from migration 003
-- (Migration 003 made it nullable to support weekly reports)

-- Step 3: Add constraint to ensure exactly one ID is present
ALTER TABLE notification_queue
ADD CONSTRAINT check_one_content_id CHECK (
  (newsletter_id IS NOT NULL AND report_id IS NULL) OR
  (newsletter_id IS NULL AND report_id IS NOT NULL)
);

-- Step 4: Drop old unique constraint
ALTER TABLE notification_queue DROP CONSTRAINT IF EXISTS unique_notification;

-- Step 5: Create partial unique indexes for each content type
-- Ensures a user only gets one notification per newsletter/rule combination
CREATE UNIQUE INDEX idx_unique_newsletter_notif
ON notification_queue (user_id, newsletter_id, rule_id)
WHERE newsletter_id IS NOT NULL;

-- Ensures a user only gets one notification per report/rule combination
CREATE UNIQUE INDEX idx_unique_report_notif
ON notification_queue (user_id, report_id, rule_id)
WHERE report_id IS NOT NULL;

-- Step 6: Add index on report_id for query performance
CREATE INDEX idx_notification_queue_report
ON notification_queue (report_id)
WHERE report_id IS NOT NULL;

-- Step 7: Add notification_type column to schema if not already exists (was added in migration 003)
-- This migration assumes notification_type already exists from migration 003
-- If running migrations out of order, uncomment:
-- ALTER TABLE notification_queue ADD COLUMN IF NOT EXISTS notification_type TEXT NOT NULL DEFAULT 'daily';
