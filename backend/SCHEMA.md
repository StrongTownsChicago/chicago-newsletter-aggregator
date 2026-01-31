# Database Schema Documentation

Complete reference for the Chicago Alderman Newsletter Tracker database schema.

> **Authoritative Schema**: See `sql/schema.sql` for the exact SQL definitions.

## Core Tables

### `sources`

Aldermen and other newsletter sources.

| Column                 | Type   | Constraints | Description                       |
| ---------------------- | ------ | ----------- | --------------------------------- |
| id                     | serial | PRIMARY KEY | Auto-incrementing ID              |
| source_type            | text   | NOT NULL    | Type of source (e.g., "alderman") |
| name                   | text   | NOT NULL    | Full name                         |
| email_address          | text   |             | Primary email address             |
| website                | text   |             | Official website URL              |
| signup_url             | text   |             | Newsletter signup URL             |
| ward_number            | text   |             | Ward number (stored as text)      |
| phone                  | text   |             | Contact phone number              |
| newsletter_archive_url | text   |             | URL to newsletter archives        |

**Unique Constraint**: `(source_type, name)`

**Indexes**:

- `idx_sources_ward_number` on `ward_number`
- `idx_sources_phone` on `phone`

---

### `newsletters`

Main table for ingested newsletters.

| Column          | Type        | Constraints                | Description                        |
| --------------- | ----------- | -------------------------- | ---------------------------------- |
| id              | uuid        | PRIMARY KEY                | Auto-generated UUID                |
| created_at      | timestamptz | DEFAULT now()              | Record creation time               |
| email_uid       | text        | UNIQUE                     | IMAP email UID (for deduplication) |
| received_date   | timestamptz | NOT NULL                   | When newsletter was received       |
| subject         | text        | NOT NULL                   | Email subject line                 |
| from_email      | text        |                            | Sender email address               |
| to_email        | text        |                            | Recipient email address            |
| raw_html        | text        |                            | Original HTML content              |
| plain_text      | text        |                            | Extracted plain text               |
| summary         | text        |                            | LLM-generated summary              |
| topics          | text[]      |                            | Array of extracted topics          |
| entities        | jsonb       |                            | Extracted entities (deprecated)    |
| source_id       | integer     | NOT NULL, FK → sources(id) | Source reference                   |
| search_vector   | tsvector    | GENERATED                  | Full-text search index             |
| relevance_score | integer     | CHECK (0-10)               | Strong Towns Chicago relevance     |

**Foreign Keys**:

- `source_id` → `sources(id)` ON DELETE SET NULL

**Indexes**:

- `newsletters_received_date_idx` on `received_date DESC`
- `newsletters_topics_idx` (GIN) on `topics`
- `idx_newsletters_source_id` on `source_id`
- `idx_newsletters_search` (GIN) on `search_vector`
- `idx_newsletters_relevance` on `relevance_score`

---

### `email_source_mappings`

Maps email patterns to sources for automatic matching.

| Column        | Type        | Constraints                | Description                                   |
| ------------- | ----------- | -------------------------- | --------------------------------------------- |
| id            | serial      | PRIMARY KEY                | Auto-incrementing ID                          |
| email_pattern | text        | NOT NULL                   | SQL wildcard pattern (e.g., "%@40thward.org") |
| source_id     | integer     | NOT NULL, FK → sources(id) | Target source                                 |
| notes         | text        |                            | Optional description                          |
| created_at    | timestamptz | DEFAULT now()              | Record creation time                          |

**Foreign Keys**:

- `source_id` → `sources(id)` ON DELETE CASCADE

**Indexes**:

- `idx_email_source_mappings_pattern` on `email_pattern`

---

## Notification System Tables

### `user_profiles`

User account data (extends Supabase Auth).

| Column                   | Type        | Constraints                      | Description                |
| ------------------------ | ----------- | -------------------------------- | -------------------------- |
| id                       | uuid        | PRIMARY KEY, FK → auth.users(id) | User ID from Supabase Auth |
| email                    | text        | NOT NULL                         | User email address         |
| created_at               | timestamptz | NOT NULL, DEFAULT now()          | Account creation time      |
| updated_at               | timestamptz | NOT NULL, DEFAULT now()          | Last update time           |
| notification_preferences | jsonb       | NOT NULL                         | Notification settings      |

**Foreign Keys**:

- `id` → `auth.users(id)` ON DELETE CASCADE

**Default Preferences**:

```json
{
  "enabled": true,
  "delivery_frequency": "daily"
}
```

**Row-Level Security**:

- ✅ Users can view their own profile
- ✅ Users can update their own profile
- ❌ Users cannot access other profiles

**Indexes**:

- `idx_user_profiles_email` on `email`

**Auto-Created**: Profile is automatically created via trigger when user signs up in Supabase Auth.

---

### `notification_rules`

User-defined notification rules.

| Column              | Type        | Constraints                            | Description                     |
| ------------------- | ----------- | -------------------------------------- | ------------------------------- |
| id                  | uuid        | PRIMARY KEY, DEFAULT gen_random_uuid() | Rule ID                         |
| user_id             | uuid        | NOT NULL, FK → auth.users(id)          | Rule owner                      |
| name                | text        | NOT NULL                               | User-friendly rule name         |
| is_active           | boolean     | NOT NULL, DEFAULT true                 | Whether rule is enabled         |
| created_at          | timestamptz | NOT NULL, DEFAULT now()                | Rule creation time              |
| updated_at          | timestamptz | NOT NULL, DEFAULT now()                | Last update time                |
| topics              | text[]      | NOT NULL, DEFAULT '{}'                 | Topics to match (MVP)           |
| search_term         | text        |                                        | Search word or phrase to match  |
| min_relevance_score | integer     |                                        | Minimum relevance score         |
| source_ids          | integer[]   |                                        | Specific sources to match       |
| ward_numbers        | text[]      |                                        | Specific wards to match         |
| delivery_frequency  | text        | NOT NULL, DEFAULT 'daily'              | Delivery frequency: daily/weekly |

**Foreign Keys**:

- `user_id` → `auth.users(id)` ON DELETE CASCADE

**Application Constraint**: Maximum 5 rules per user (enforced in API)

**Matching Logic**: All filters are AND-ed together.

- `topics`: Matches if newsletter has ANY of the selected topics.
- `search_term`: Matches if newsletter contains the exact search phrase (case-insensitive substring).
- If both are present, newsletter must match BOTH criteria.

**Row-Level Security**:

- ✅ Users can view their own rules
- ✅ Users can create their own rules
- ✅ Users can update their own rules
- ✅ Users can delete their own rules
- ❌ Users cannot access other users' rules

**Indexes**:

- `idx_notification_rules_user_id` on `user_id`
- `idx_notification_rules_active` on `(user_id, is_active)`
- `idx_notification_rules_frequency` on `(delivery_frequency, is_active)`

---

### `notification_queue`

Pending notifications waiting to be sent. Supports both newsletter and report notifications via polymorphic design.

| Column            | Type        | Constraints                            | Description                                    |
| ----------------- | ----------- | -------------------------------------- | ---------------------------------------------- |
| id                | uuid        | PRIMARY KEY, DEFAULT gen_random_uuid() | Queue entry ID                                 |
| user_id           | uuid        | NOT NULL, FK → auth.users(id)          | Recipient user                                 |
| newsletter_id     | uuid        | FK → newsletters(id)                   | Matched newsletter (NULL for weekly reports)   |
| report_id         | uuid        | FK → weekly_topic_reports(id)          | Matched report (NULL for daily newsletters)    |
| rule_id           | uuid        | NOT NULL, FK → notification_rules(id)  | Rule that matched                              |
| status            | text        | NOT NULL, DEFAULT 'pending'            | Status: pending/sent/failed                    |
| digest_batch_id   | text        |                                        | Batch ID for grouping (YYYY-MM-DD or YYYY-WXX) |
| notification_type | text        | NOT NULL, DEFAULT 'daily'              | Type: daily/weekly                             |
| created_at        | timestamptz | NOT NULL, DEFAULT now()                | When queued                                    |
| sent_at           | timestamptz |                                        | When sent/failed                               |
| error_message     | text        |                                        | Error details if failed                        |

**Foreign Keys**:

- `user_id` → `auth.users(id)` ON DELETE CASCADE
- `newsletter_id` → `newsletters(id)` ON DELETE CASCADE (nullable)
- `report_id` → `weekly_topic_reports(id)` ON DELETE CASCADE (nullable)
- `rule_id` → `notification_rules(id)` ON DELETE CASCADE

**Polymorphic Design**: Exactly one of `newsletter_id` or `report_id` must be set (enforced by CHECK constraint). Daily notifications use `newsletter_id`, weekly notifications use `report_id`.

**Unique Constraints**: Partial unique indexes prevent duplicate notifications:

- `idx_unique_newsletter_notif` on `(user_id, newsletter_id, rule_id)` WHERE `newsletter_id` IS NOT NULL
- `idx_unique_report_notif` on `(user_id, report_id, rule_id)` WHERE `report_id` IS NOT NULL

**Status Values**:

- `pending` - Waiting to be sent
- `sent` - Successfully sent
- `failed` - Delivery failed

**Row-Level Security**:

- ✅ Users can view their own queued notifications
- ❌ Users cannot modify queue (backend only)

**Indexes**:

- `idx_notification_queue_status` on `(status, created_at)`
- `idx_notification_queue_user` on `(user_id, status)`
- `idx_notification_queue_digest` on `(digest_batch_id, status)`
- `idx_notification_queue_type_status` on `(notification_type, status, created_at)`
- `idx_notification_queue_report` on `report_id` (partial index WHERE `report_id` IS NOT NULL)

---

### `notification_history`

Audit log of sent notifications.

| Column          | Type        | Constraints                            | Description                                |
| --------------- | ----------- | -------------------------------------- | ------------------------------------------ |
| id              | uuid        | PRIMARY KEY, DEFAULT gen_random_uuid() | History entry ID                           |
| user_id         | uuid        | NOT NULL, FK → auth.users(id)          | Recipient user                             |
| newsletter_ids  | uuid[]      | NOT NULL                               | Array of newsletter IDs in digest          |
| rule_ids        | uuid[]      | NOT NULL                               | Array of rule IDs that matched             |
| digest_batch_id | text        |                                        | Batch ID (YYYY-MM-DD)                      |
| delivery_type   | text        | NOT NULL                               | Type: immediate/daily_digest/weekly_digest |
| sent_at         | timestamptz | NOT NULL, DEFAULT now()                | When sent                                  |
| success         | boolean     | NOT NULL                               | Whether delivery succeeded                 |
| error_message   | text        |                                        | Error details if failed                    |
| resend_email_id | text        |                                        | Resend API email ID for tracking           |

**Foreign Keys**:

- `user_id` → `auth.users(id)` ON DELETE CASCADE

**Delivery Types**:

- `daily_digest` - Daily aggregated email with matched newsletters
- `weekly_digest` - Weekly aggregated email with AI-generated topic reports

**Row-Level Security**:

- ✅ Users can view their own notification history
- ❌ Users cannot modify history (backend only)

**Indexes**:

- `idx_notification_history_user` on `(user_id, sent_at DESC)`
- `idx_notification_history_batch` on `digest_batch_id`
- `idx_notification_history_success` on `(success, sent_at DESC)`

---

### `weekly_topic_reports`

AI-generated weekly summaries for specific topics.

| Column           | Type        | Constraints                            | Description                                  |
| ---------------- | ----------- | -------------------------------------- | -------------------------------------------- |
| id               | uuid        | PRIMARY KEY, DEFAULT gen_random_uuid() | Report ID                                    |
| topic            | text        | NOT NULL                               | Topic name (from TOPICS constant)            |
| week_id          | text        | NOT NULL                               | ISO week identifier (YYYY-WXX)               |
| report_summary   | text        | NOT NULL                               | AI-generated 2-4 paragraph synthesis         |
| newsletter_ids   | uuid[]      | NOT NULL                               | Array of newsletter IDs analyzed             |
| key_developments | jsonb       |                                        | Optional structured facts from Phase 1 LLM   |
| created_at       | timestamptz | NOT NULL, DEFAULT now()                | When report was generated                    |

**Unique Constraint**: `(topic, week_id)` - Prevents duplicate reports for same topic/week (idempotency)

**Row-Level Security**:

- ✅ All authenticated users can view weekly reports
- ❌ Only service role can create/update (backend processing only)

**Indexes**:

- `idx_weekly_topic_reports_week` on `week_id`
- `idx_weekly_topic_reports_topic` on `topic`
- `idx_weekly_topic_reports_topic_week` on `(topic, week_id)`

**Report Generation**: Reports are generated by `utils.process_weekly_reports` for topics with active weekly subscribers.

---

## Database Functions

### `create_user_profile()`

**Trigger Function** - Automatically creates user profile when user signs up.

**Fires**: AFTER INSERT on `auth.users`

**Action**: Inserts new row in `user_profiles` with default preferences.

---

### `update_updated_at_column()`

**Trigger Function** - Auto-updates `updated_at` timestamp on record changes.

**Fires**: BEFORE UPDATE on `user_profiles` and `notification_rules`

---

### `count_user_rules(user_uuid uuid) → integer`

**Helper Function** - Returns count of notification rules for a user.

**Usage**: Used in API to enforce 5-rule limit per user.

**Permissions**: Granted to `authenticated` role.

---

### `get_active_weekly_topics() → TABLE(topic text)`

**Helper Function** - Returns list of topics that have active weekly subscribers.

**Usage**: Used by `process_weekly_reports.py` to optimize report generation (only process topics with subscribers).

**Returns**: Distinct list of topics from active weekly notification rules.

**Permissions**: Granted to `authenticated` and `service_role`.

---

### `get_week_date_range(week_id_param text) → TABLE(week_start date, week_end date)`

**Helper Function** - Converts ISO week ID (YYYY-WXX) to date range.

**Usage**: Used to query newsletters by week for report generation.

**Example**:
```sql
SELECT * FROM get_week_date_range('2026-W05');
-- Returns: week_start = 2026-01-26, week_end = 2026-02-01
```

**Permissions**: Granted to `authenticated` and `service_role`.

---

## Data Flow

### Newsletter Ingestion

1. Email arrives → `ingest.email.process_emails`
2. Parse and match source → `email_source_mappings`
3. Process with LLM → extract topics, summary, relevance
4. Insert into `newsletters` table
5. **NEW**: Match against `notification_rules` → queue in `notification_queue`

### Daily Notification Delivery

1. Daily cron/GitHub Action runs `process_notification_queue.py --daily-digest`
2. Group pending notifications by `user_id` and `digest_batch_id`
3. Send ONE email per user via Resend API
4. Update `notification_queue` status to 'sent'
5. Record delivery in `notification_history` with `delivery_type='daily_digest'`

### Weekly Report Generation and Delivery

1. Weekly cron runs `utils.process_weekly_reports` (e.g., Monday morning)
2. Query `get_active_weekly_topics()` to find topics with subscribers
3. For each active topic:
   - Fetch newsletters tagged with topic from previous week
   - Extract structured facts via LLM (Phase 1)
   - Synthesize weekly summary via LLM (Phase 2)
   - Store in `weekly_topic_reports` table
4. Run `notifications.weekly_notification_queue` to queue notifications
5. Weekly cron runs `process_notification_queue.py --weekly-digest`
6. Group by user, send ONE email per user with all subscribed topics
7. Record delivery with `delivery_type='weekly_digest'`

---

## Migration History

| Version | File                               | Description                                                     | Date       |
| ------- | ---------------------------------- | --------------------------------------------------------------- | ---------- |
| 001     | `001_notification_system.sql`      | Added notification system (4 tables, triggers, RLS)             | 2026-01-21 |
| 002     | `002_add_search_term.sql`          | Replaced keywords array with single search_term column          | 2026-01-23 |
| 003     | `003_weekly_topic_reports.sql`     | Added weekly topic reports (table, delivery_frequency, helpers) | 2026-01-31 |
| 004     | `004_polymorphic_notifications.sql`| Polymorphic notification_queue (dedicated report_id column)     | 2026-01-31 |

---

## Useful Queries

### Check notification queue status

```sql
SELECT status, COUNT(*)
FROM notification_queue
GROUP BY status;
```

### Find most popular topics in rules

```sql
SELECT topic, COUNT(*) AS usage
FROM notification_rules, unnest(topics) AS topic
WHERE is_active = true
GROUP BY topic
ORDER BY usage DESC;
```

### Daily digest statistics

```sql
SELECT
  digest_batch_id,
  COUNT(DISTINCT user_id) AS users,
  COUNT(*) AS total_notifications
FROM notification_history
WHERE delivery_type = 'daily_digest'
GROUP BY digest_batch_id
ORDER BY digest_batch_id DESC
LIMIT 7;
```

### Newsletter ingestion rate

```sql
SELECT
  DATE(received_date) AS date,
  COUNT(*) AS newsletters
FROM newsletters
WHERE received_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY DATE(received_date)
ORDER BY date DESC;
```

### Weekly report generation status

```sql
SELECT
  week_id,
  topic,
  array_length(newsletter_ids, 1) AS newsletters_analyzed,
  LENGTH(report_summary) AS summary_length,
  created_at
FROM weekly_topic_reports
ORDER BY week_id DESC, topic;
```

### Topics with active weekly subscribers

```sql
SELECT * FROM get_active_weekly_topics()
ORDER BY topic;
```

### Weekly digest delivery statistics

```sql
SELECT
  digest_batch_id AS week_id,
  COUNT(DISTINCT user_id) AS users,
  COUNT(*) AS total_reports_sent
FROM notification_history
WHERE delivery_type = 'weekly_digest'
GROUP BY digest_batch_id
ORDER BY digest_batch_id DESC
LIMIT 10;
```

### Fetch newsletters for weekly report generation

```sql
SELECT
  n.id,
  n.subject,
  n.plain_text,
  n.received_date,
  s.name AS source_name,
  s.ward_number
FROM newsletters n
JOIN sources s ON n.source_id = s.id
CROSS JOIN get_week_date_range('2026-W05') AS week_range
WHERE 'bike_lanes' = ANY(n.topics)
  AND n.received_date::DATE BETWEEN week_range.week_start AND week_range.week_end
ORDER BY n.received_date DESC;
```

---

## Schema Maintenance

**Backup Before Changes**: Always backup database before running migrations.

**Apply Migrations**: Use Supabase SQL Editor or `psql` to run migration files.

**Verify RLS**: Test row-level security policies in Supabase dashboard with test users.

**Index Monitoring**: Check index usage and performance in Supabase Dashboard → Database → Index Advisor.
