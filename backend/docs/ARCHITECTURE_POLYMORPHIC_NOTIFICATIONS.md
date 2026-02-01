# Architectural Decision: Polymorphic Notifications in `notification_queue`

## 1. The Problem Statement

The system is evolving from a single-content notification system (Daily Newsletter Digests) to a multi-content system (adding Weekly Topic Reports). 

Currently, the `notification_queue` table is designed around the `newsletters` table. It has a column `newsletter_id` with a strict **Foreign Key (FK) constraint** pointing to `public.newsletters(id)`.

**The conflict arises because:**
1. Weekly Topic Reports are stored in a separate table: `weekly_topic_reports`.
2. The current implementation attempts to store the `id` from `weekly_topic_reports` into the `notification_queue.newsletter_id` column.
3. This triggers a database error (`23503: foreign key violation`) because the Report ID does not exist in the Newsletter table.
4. Furthermore, Supabase (PostgREST) cannot perform automatic joins to fetch report content because it relies on formal FK relationships to discover join paths.

### References:
- **Table Definition**: `backend/sql/schema.sql` (see `notification_queue`)
- **Failing Script**: `backend/notifications/weekly_notification_queue.py` (insertion logic)
- **Failing Fetcher**: `backend/notifications/process_notification_queue.py` (join logic)

---

## 2. Solution Options

### Option A: Overloaded Column (The "Quick Fix")
Drop the FK constraint on `newsletter_id` and use it as a generic "Content ID".
- **Pros**: Minimal code changes; no new columns.
- **Cons**: Total loss of referential integrity; no `ON DELETE CASCADE`; requires manual "two-step" fetching in Python (cannot join in one DB call).

### Option B: Dedicated Columns (Best Practice for SQL)
Add a dedicated `report_id` column to `notification_queue` with its own FK to `weekly_topic_reports`.
- **Pros**: Full referential integrity; Supabase auto-joins work perfectly; `ON DELETE CASCADE` works; clear and self-documenting.
- **Cons**: Requires migration to add column; requires updating all insert/select logic in the backend.

### Option C: Generic Polymorphic Association (Extensible)
Use two columns: `content_id` (UUID) and `content_type` (TEXT: 'newsletter' or 'report').
- **Pros**: Infinite extensibility (easy to add "Urgent Alerts", "Monthly Summaries" later).
- **Cons**: Lacks formal FK constraints at the DB level (standard SQL limitation); requires complex logic to join.

---

## 3. Best Practice Recommendation

**Option B (Dedicated Columns)** is the recommended best practice for this project.

While it requires more initial refactoring, it aligns with relational database principles and leverages the power of the Supabase/PostgREST engine. 

### Why Option B?
1. **Performance**: You can fetch the queue item, the rule, AND the content (whether it's a newsletter or a report) in a single optimized query using `.select("*, newsletter:newsletters(*), report:weekly_topic_reports(*)")`.
2. **Safety**: The database guarantees that you can't have a notification pointing to a deleted report.
3. **Clarity**: A developer looking at the table immediately understands that a notification can be triggered by one of two distinct types of content.

---

## 4. Implementation Roadmap for Future Agent

If implementing **Option B**, the following steps should be taken:

### Step 1: Migration (`backend/migrations/004_dedicated_notification_columns.sql`)
```sql
-- 1. Add the new column
ALTER TABLE notification_queue 
ADD COLUMN report_id UUID REFERENCES weekly_topic_reports(id) ON DELETE CASCADE;

-- 2. Make the old column nullable (if it wasn't already)
ALTER TABLE notification_queue 
ALTER COLUMN newsletter_id DROP NOT NULL;

-- 3. Update the unique constraint to be smarter
ALTER TABLE notification_queue DROP CONSTRAINT IF EXISTS unique_notification;

-- Ensure a user only gets one notification per specific piece of content/rule
CREATE UNIQUE INDEX idx_unique_newsletter_notif ON notification_queue (user_id, newsletter_id, rule_id) WHERE newsletter_id IS NOT NULL;
CREATE UNIQUE INDEX idx_unique_report_notif ON notification_queue (user_id, report_id, rule_id) WHERE report_id IS NOT NULL;
```

### Step 2: Update Queuing Logic
Update `backend/notifications/weekly_notification_queue.py` to insert into `report_id` instead of `newsletter_id`.

### Step 3: Update Fetching Logic
Update `backend/notifications/process_notification_queue.py`:
- Refactor `_fetch_weekly_notifications` to use a single `.select()` join now that the FK exists.
- Update the grouping logic to check for the presence of `report_id`.

### Step 4: Update History Recording
Ensure `notification_history` (which uses a `UUID[]` array for `newsletter_ids`) is updated to store whichever ID was used, or consider adding a `report_ids` column there as well for parity.
