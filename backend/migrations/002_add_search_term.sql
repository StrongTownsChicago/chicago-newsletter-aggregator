-- Migration: Add search_term column for single-phrase matching
-- Description: Replaces the unused 'keywords' array with a single 'search_term' text column.
-- Date: 2026-01-23

-- Add the new column
ALTER TABLE public.notification_rules 
ADD COLUMN search_term text CHECK (length(search_term) <= 100);

-- Remove the old column
ALTER TABLE public.notification_rules 
DROP COLUMN keywords;
