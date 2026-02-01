-- Migration: Remove ward filters from weekly notification rules
-- Weekly summaries are citywide by design and should not have ward filters
-- Created: 2026-01-31

-- Clear ward_numbers from existing weekly rules
UPDATE notification_rules
SET ward_numbers = NULL
WHERE delivery_frequency = 'weekly'
  AND ward_numbers IS NOT NULL
  AND array_length(ward_numbers, 1) > 0;

-- Add check constraint to prevent ward filters on weekly rules
-- This ensures data integrity at the database level
ALTER TABLE notification_rules
ADD CONSTRAINT weekly_rules_no_ward_filter
CHECK (
  delivery_frequency != 'weekly'
  OR ward_numbers IS NULL
  OR array_length(ward_numbers, 1) IS NULL
);

-- Add comment explaining the constraint
COMMENT ON CONSTRAINT weekly_rules_no_ward_filter ON notification_rules IS
'Weekly summaries cover citywide activity and cannot be filtered by ward. Only daily digest notifications support ward filtering.';
