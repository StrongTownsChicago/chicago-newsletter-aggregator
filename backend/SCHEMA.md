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

| Column              | Type        | Constraints                            | Description                      |
| ------------------- | ----------- | -------------------------------------- | -------------------------------- |
| id                  | uuid        | PRIMARY KEY, DEFAULT gen_random_uuid() | Rule ID                          |
| user_id             | uuid        | NOT NULL, FK → auth.users(id)          | Rule owner                       |
| name                | text        | NOT NULL                               | User-friendly rule name          |
| is_active           | boolean     | NOT NULL, DEFAULT true                 | Whether rule is enabled          |
| created_at          | timestamptz | NOT NULL, DEFAULT now()                | Rule creation time               |
| updated_at          | timestamptz | NOT NULL, DEFAULT now()                | Last update time                 |
| topics              | text[]      | NOT NULL, DEFAULT '{}'                 | Topics to match                  |
| search_term         | text        | CHECK (length <= 100)                  | Search word or phrase to match   |
| min_relevance_score | integer     |                                        | Minimum relevance score          |
| source_ids          | integer[]   |                                        | Specific sources to match        |
| ward_numbers        | text[]      |                                        | Specific wards to match          |
| delivery_frequency  | text        | DEFAULT 'daily'                        | Delivery frequency: daily/weekly |

**Foreign Keys**:

- `user_id` → `auth.users(id)` ON DELETE CASCADE

**Database Constraints**:

- `notification_rules_search_term_check`: Prevents search terms longer than 100 characters.
- `weekly_rules_no_ward_filter`: Prevents ward_numbers on weekly rules. Weekly summaries cover citywide activity and cannot be filtered by ward.

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
| notification_type | text        | DEFAULT 'daily'                        | Type: daily/weekly                             |
| created_at        | timestamptz | NOT NULL, DEFAULT now()                | When queued                                    |
| sent_at           | timestamptz |                                        | When sent/failed                               |
| error_message     | text        |                                        | Error details if failed                        |

**Foreign Keys**:

- `user_id` → `auth.users(id)` ON DELETE CASCADE
- `newsletter_id` → `newsletters(id)` ON DELETE CASCADE (nullable)
- `report_id` → `weekly_topic_reports(id)` ON DELETE CASCADE (nullable)
- `rule_id` → `notification_rules(id)` ON DELETE CASCADE

**Polymorphic Design**: Exactly one of `newsletter_id` or `report_id` must be set (enforced by `check_one_content_id` constraint).

**Unique Constraints**: Partial unique indexes prevent duplicate notifications:

- `idx_unique_newsletter_notif` on `(user_id, newsletter_id, rule_id)` WHERE `newsletter_id` IS NOT NULL
- `idx_unique_report_notif` on `(user_id, report_id, rule_id)` WHERE `report_id` IS NOT NULL

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

| Column           | Type        | Constraints                            | Description                      |
| ---------------- | ----------- | -------------------------------------- | -------------------------------- |
| id               | uuid        | PRIMARY KEY, DEFAULT gen_random_uuid() | Report ID                        |
| topic            | text        | NOT NULL                               | Topic name                       |
| week_id          | text        | NOT NULL                               | ISO week identifier (YYYY-WXX)   |
| report_summary   | text        | NOT NULL                               | AI-generated synthesis           |
| newsletter_ids   | uuid[]      | NOT NULL                               | Array of newsletter IDs analyzed |
| key_developments | jsonb       |                                        | Optional structured facts        |
| created_at       | timestamptz | NOT NULL, DEFAULT now()                | When report was generated        |

**Unique Constraint**: `(topic, week_id)` - Prevents duplicate reports for same topic/week.

**Row-Level Security**:

- ✅ All authenticated users can view weekly reports
- ✅ Service role has full access for backend operations

**Indexes**:

- `idx_weekly_topic_reports_week` on `week_id`
- `idx_weekly_topic_reports_topic` on `topic`
- `idx_weekly_topic_reports_topic_week` on `(topic, week_id)`

---

## Database Functions

- `create_user_profile()`: Trigger function to create profile on signup.
- `update_updated_at_column()`: Trigger function to update timestamps.
- `count_user_rules(user_uuid)`: Returns count of rules for a user.
- `get_active_weekly_topics()`: Returns list of topics with active weekly subscribers.

### `get_week_date_range(week_id TEXT)`

Converts ISO week identifier to date range.

**Purpose:** Enables efficient filtering of newsletters by ISO week in PostgreSQL queries.

**Parameters:**

- `week_id`: ISO week identifier in format YYYY-WXX (e.g., "2026-W05")

**Returns:** Table with columns:

- `week_start`: Monday of the ISO week (DATE)
- `week_end`: Sunday of the ISO week (DATE)

---

## Migration History

| Version | File                                  | Description                                                     |
| ------- | ------------------------------------- | --------------------------------------------------------------- |
| 001     | `001_notification_system.sql`         | Added notification system (4 tables, triggers, RLS)             |
| 002     | `002_add_search_term.sql`             | Replaced keywords array with single search_term column          |
| 003     | `003_weekly_topic_reports.sql`        | Added weekly topic reports (table, delivery_frequency, helpers) |
| 004     | `004_polymorphic_notifications.sql`   | Polymorphic notification_queue (dedicated report_id column)     |
| 005     | `005_weekly_rules_no_ward_filter.sql` | Constraint to prevent ward filters on weekly rules              |
