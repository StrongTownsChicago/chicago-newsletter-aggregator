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

| Column              | Type        | Constraints                            | Description                    |
| ------------------- | ----------- | -------------------------------------- | ------------------------------ |
| id                  | uuid        | PRIMARY KEY, DEFAULT gen_random_uuid() | Rule ID                        |
| user_id             | uuid        | NOT NULL, FK → auth.users(id)          | Rule owner                     |
| name                | text        | NOT NULL                               | User-friendly rule name        |
| is_active           | boolean     | NOT NULL, DEFAULT true                 | Whether rule is enabled        |
| created_at          | timestamptz | NOT NULL, DEFAULT now()                | Rule creation time             |
| updated_at          | timestamptz | NOT NULL, DEFAULT now()                | Last update time               |
| topics              | text[]      | NOT NULL, DEFAULT '{}'                 | Topics to match (MVP)          |
| search_term         | text        |                                        | Search word or phrase to match |
| min_relevance_score | integer     |                                        | Minimum relevance score        |
| source_ids          | integer[]   |                                        | Specific sources to match      |
| ward_numbers        | text[]      |                                        | Specific wards to match        |

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

---

### `notification_queue`

Pending notifications waiting to be sent.

| Column          | Type        | Constraints                            | Description                        |
| --------------- | ----------- | -------------------------------------- | ---------------------------------- |
| id              | uuid        | PRIMARY KEY, DEFAULT gen_random_uuid() | Queue entry ID                     |
| user_id         | uuid        | NOT NULL, FK → auth.users(id)          | Recipient user                     |
| newsletter_id   | uuid        | NOT NULL, FK → newsletters(id)         | Matched newsletter                 |
| rule_id         | uuid        | NOT NULL, FK → notification_rules(id)  | Rule that matched                  |
| status          | text        | NOT NULL, DEFAULT 'pending'            | Status: pending/sent/failed        |
| digest_batch_id | text        |                                        | Batch ID for grouping (YYYY-MM-DD) |
| created_at      | timestamptz | NOT NULL, DEFAULT now()                | When queued                        |
| sent_at         | timestamptz |                                        | When sent/failed                   |
| error_message   | text        |                                        | Error details if failed            |

**Foreign Keys**:

- `user_id` → `auth.users(id)` ON DELETE CASCADE
- `newsletter_id` → `newsletters(id)` ON DELETE CASCADE
- `rule_id` → `notification_rules(id)` ON DELETE CASCADE

**Unique Constraint**: `(user_id, newsletter_id, rule_id)` - prevents duplicate notifications

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

- `daily_digest` - Daily aggregated email

**Row-Level Security**:

- ✅ Users can view their own notification history
- ❌ Users cannot modify history (backend only)

**Indexes**:

- `idx_notification_history_user` on `(user_id, sent_at DESC)`
- `idx_notification_history_batch` on `digest_batch_id`
- `idx_notification_history_success` on `(success, sent_at DESC)`

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

## Data Flow

### Newsletter Ingestion

1. Email arrives → `ingest.email.process_emails`
2. Parse and match source → `email_source_mappings`
3. Process with LLM → extract topics, summary, relevance
4. Insert into `newsletters` table
5. **NEW**: Match against `notification_rules` → queue in `notification_queue`

### Notification Delivery

1. Daily cron/GitHub Action runs `process_notification_queue.py`
2. Group pending notifications by `user_id` and `digest_batch_id`
3. Send ONE email per user via Resend API
4. Update `notification_queue` status to 'sent'
5. Record delivery in `notification_history`

---

## Migration History

| Version | File                          | Description                                            | Date       |
| ------- | ----------------------------- | ------------------------------------------------------ | ---------- |
| 001     | `001_notification_system.sql` | Added notification system (4 tables, triggers, RLS)    | 2026-01-21 |
| 002     | `002_add_search_term.sql`     | Replaced keywords array with single search_term column | 2026-01-23 |

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

---

## Schema Maintenance

**Backup Before Changes**: Always backup database before running migrations.

**Apply Migrations**: Use Supabase SQL Editor or `psql` to run migration files.

**Verify RLS**: Test row-level security policies in Supabase dashboard with test users.

**Index Monitoring**: Check index usage and performance in Supabase Dashboard → Database → Index Advisor.
