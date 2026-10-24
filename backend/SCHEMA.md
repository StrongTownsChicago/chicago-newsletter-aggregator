# Database Schema Documentation

Complete reference for the Chicago Alderman Newsletter Tracker database schema.

> **Source of truth**: `migrations/` builds the schema; apply them in order to an empty Supabase database. `sql/schema.sql` is a schema-only snapshot of production (2026-10-24) for reference.

## Production status

Production is migrations `000`–`005` and `007`. **`006` has not been applied**, so production differs from a database built from every migration in two ways:

- `email_source_mappings` still has the `"Allow public read access"` policy, so anyone with the anon key can read the sender patterns and notes. `006` drops it; nothing outside the backend (service key) reads this table.
- The `newsletters` write gates still have their old names, `"Service role insert newsletters"` / `"Service role update newsletters"`. `006` renames them; behaviour is the same.

After applying `006` in production, refresh `sql/schema.sql` and this section (see "Keeping the schema accurate").

## Row-Level Security

RLS is enabled on every public table. See `migrations/006_enable_rls_public_tables.sql` for the intended policy set and "Production status" above for where production still differs.

- **RLS is the only barrier**: `anon` and `authenticated` hold Supabase's default `GRANT ALL` on every public table, so a table without RLS (or with a permissive policy) is writable or readable through the public API.
- **Default deny**: any command without a permissive policy is denied to `anon`/`authenticated`. `sources` and `newsletters` are public read-only; `weekly_topic_reports` has no public policies (backend only), and `email_source_mappings` has none once `006` is applied.
- **`service_role` bypasses RLS**, so backend jobs using `SUPABASE_SERVICE_KEY` are unaffected.
- **The `newsletters` insert/update policies** use literal `false`: deny-all gates, not grants. Do not turn them into grants.
- Owner-scoped tables (`user_profiles`, `notification_*`) check `auth.uid()`, which is null for anonymous requests.

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
| search_vector   | tsvector    | GENERATED, STORED          | Full-text search index             |
| relevance_score | integer     | CHECK (0-10)               | LLM relevance score (deprecated)   |

**Full-text search**: `search_vector` is `to_tsvector('english', coalesce(subject, '') || ' ' || coalesce(plain_text, ''))`, so search covers the subject and plain text, unweighted, with English stemming.

**Foreign Keys**:

- `source_id` → `sources(id)` ON DELETE SET NULL. Because `source_id` is also `NOT NULL`, deleting a source that still has newsletters fails; reassign or delete its newsletters first.

**Indexes**:

- `newsletters_received_date_idx` on `received_date DESC`
- `newsletters_topics_idx` (GIN) on `topics`
- `idx_newsletters_source_id` on `source_id`
- `idx_newsletters_search` (GIN) on `search_vector`
- `idx_newsletters_relevance` on `relevance_score`

**Deprecated columns**: `entities` and `relevance_score` are no longer written or read by the app. Existing values are kept; there is no migration to drop them.

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

**Row-Level Security**: backend only once `006` is applied; publicly readable in production until then (see "Production status").

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

**Auto-Created**: the `on_auth_user_created` trigger on `auth.users` (migration `001`) calls `create_user_profile()` when a user signs up. The trigger lives in the `auth` schema, so the public-schema snapshot doesn't show it; production's profile and user counts match.

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
| min_relevance_score | integer     |                                        | Unused (deprecated)              |
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

- ✅ Service role has full access for backend operations
- ❌ No `anon`/`authenticated` access (no frontend reads this table)

**Indexes**:

- `idx_weekly_topic_reports_week` on `week_id`
- `idx_weekly_topic_reports_topic` on `topic`
- `idx_weekly_topic_reports_topic_week` on `(topic, week_id)`

---

## Database Functions

- `create_user_profile()`: trigger function that inserts a `user_profiles` row (id, email) for a new auth user. `SECURITY DEFINER` with `search_path = public`.
- `update_updated_at_column()`: trigger function behind the `update_user_profiles_updated_at` and `update_notification_rules_updated_at` triggers, which set `updated_at` on every update.
- `count_user_rules(user_uuid)`: returns the number of rules a user has.
- `get_active_weekly_topics()`: returns the distinct topics of active weekly rules.

Functions are executable by `anon`, `authenticated` and `service_role` (Supabase defaults), except as noted below.

### `get_week_date_range(week_id TEXT)`

Converts ISO week identifier to date range.

**Purpose:** Enables efficient filtering of newsletters by ISO week in PostgreSQL queries.

**Parameters:**

- `week_id`: ISO week identifier in format YYYY-WXX (e.g., "2026-W05")

**Returns:** Table with columns:

- `week_start`: Monday of the ISO week (DATE)
- `week_end`: Sunday of the ISO week (DATE)

### `search_term_timeline(search_query TEXT)`

Counts the newsletters matching a `/search` query per month. Powers the search page timeline via `/api/search-timeline`.

**Matching:** `search_vector @@ websearch_to_tsquery('english', search_query)`, the same filter the search page applies, so it uses the `idx_newsletters_search` GIN index and the monthly counts sum to the search page total when no other filters are set.

**Returns:** One row per America/Chicago calendar month that has at least one match, oldest first:

- `month`: first day of the month (DATE)
- `newsletter_count`: matching newsletters (INTEGER)
- `ward_count`: distinct `sources.ward_number` values among them (INTEGER; sources without a ward are not counted)

**Safety:** `STABLE`, `SECURITY INVOKER` (newsletter and source RLS applies), `search_path = ''`, `statement_timeout = 3s`. Raises `invalid_parameter_value` unless the trimmed query is 1–200 characters. Executable by `anon`, `authenticated` and `service_role` only.

---

## Migration History

| Version | File                                  | Description                                                     |
| ------- | ------------------------------------- | --------------------------------------------------------------- |
| 000     | `000_baseline_schema.sql`             | Core tables (sources, email mappings, newsletters), from production; already applied there |
| 001     | `001_notification_system.sql`         | Added notification system (4 tables, triggers, RLS)             |
| 002     | `002_add_search_term.sql`             | Replaced keywords array with single search_term column          |
| 003     | `003_weekly_topic_reports.sql`        | Added weekly topic reports (table, delivery_frequency, helpers) |
| 004     | `004_polymorphic_notifications.sql`   | Polymorphic notification_queue (dedicated report_id column)     |
| 005     | `005_weekly_rules_no_ward_filter.sql` | Constraint to prevent ward filters on weekly rules              |
| 006     | `006_enable_rls_public_tables.sql`    | RLS on all public tables; **not yet applied in production**     |
| 007     | `007_search_term_timeline.sql`        | `search_term_timeline` RPC for the search page timeline         |

## Keeping the schema accurate

- **Every schema change is a migration** in `migrations/`, applied to production after review. Never change the schema only in the Supabase dashboard: that is how the core tables and the migration list drifted apart before `000` existed.
- **Checking the repo against a database** needs no production access. Start a throwaway Supabase Postgres (`docker run -d -e POSTGRES_PASSWORD=<local> -p 127.0.0.1:<port>:5432 public.ecr.aws/supabase/postgres:<production version>`), apply the migrations production has with `psql -v ON_ERROR_STOP=1 -f`, dump it with `npx supabase db dump --db-url <local url>`, and diff against `sql/schema.sql`. On 2026-10-24, `000`–`005` + `007` matched production apart from a comment inside `create_user_profile()`.
- **Refreshing `sql/schema.sql` from production** reads only the catalog (`npx supabase db dump`, schema-only by default), but it connects to the live database. Do it rarely, at a quiet time, and never with `--data-only`.
