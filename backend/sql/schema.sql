-- CHICAGO ALDERMAN NEWSLETTER TRACKER - PRODUCTION SCHEMA SNAPSHOT
--
-- The public schema exactly as it runs in production: a schema-only dump
-- (`supabase db dump`, no data) taken 2026-10-24. Reference only; to build a
-- database, apply backend/migrations/ in order instead.
--
-- Production is migrations 000-005 and 007. Migration 006 has not been applied
-- there yet, so this snapshot still has the email_source_mappings public read
-- policy and the old newsletters policy names that 006 changes.
--
-- To refresh without touching production, apply the migrations production has
-- to an empty local Supabase database and dump that the same way; see
-- backend/SCHEMA.md "Keeping the schema accurate". Applying 000-005 and 007
-- reproduces this file except for a comment inside create_user_profile().

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

COMMENT ON SCHEMA "public" IS 'standard public schema';

CREATE EXTENSION IF NOT EXISTS "pg_stat_statements" WITH SCHEMA "extensions";

CREATE EXTENSION IF NOT EXISTS "pgcrypto" WITH SCHEMA "extensions";

CREATE EXTENSION IF NOT EXISTS "supabase_vault" WITH SCHEMA "vault";

CREATE EXTENSION IF NOT EXISTS "uuid-ossp" WITH SCHEMA "extensions";

CREATE OR REPLACE FUNCTION "public"."count_user_rules"("user_uuid" "uuid") RETURNS integer
    LANGUAGE "sql" STABLE
    AS $$
    SELECT COUNT(*)::INTEGER
    FROM notification_rules
    WHERE user_id = user_uuid;
$$;

ALTER FUNCTION "public"."count_user_rules"("user_uuid" "uuid") OWNER TO "postgres";

CREATE OR REPLACE FUNCTION "public"."create_user_profile"() RETURNS "trigger"
    LANGUAGE "plpgsql" SECURITY DEFINER
    SET "search_path" TO 'public'
    AS $$
BEGIN
    INSERT INTO public.user_profiles (id, email)  -- Add "public." here
    VALUES (NEW.id, NEW.email);
    RETURN NEW;
END;
$$;

ALTER FUNCTION "public"."create_user_profile"() OWNER TO "postgres";

CREATE OR REPLACE FUNCTION "public"."get_active_weekly_topics"() RETURNS TABLE("topic" "text")
    LANGUAGE "sql" STABLE
    AS $$
    SELECT DISTINCT unnest(topics) AS topic
    FROM notification_rules
    WHERE is_active = true
      AND delivery_frequency = 'weekly';
$$;

ALTER FUNCTION "public"."get_active_weekly_topics"() OWNER TO "postgres";

CREATE OR REPLACE FUNCTION "public"."get_week_date_range"("week_id_param" "text") RETURNS TABLE("week_start" "date", "week_end" "date")
    LANGUAGE "plpgsql" STABLE
    AS $$
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
$$;

ALTER FUNCTION "public"."get_week_date_range"("week_id_param" "text") OWNER TO "postgres";

CREATE OR REPLACE FUNCTION "public"."search_term_timeline"("search_query" "text") RETURNS TABLE("month" "date", "newsletter_count" integer, "ward_count" integer)
    LANGUAGE "plpgsql" STABLE
    SET "search_path" TO ''
    SET "statement_timeout" TO '3s'
    AS $$
#variable_conflict use_column
DECLARE
    max_query_length CONSTANT INTEGER := 200;
    trimmed_query TEXT := btrim(search_query);
    matching_query tsquery;
BEGIN
    IF trimmed_query IS NULL
        OR trimmed_query = ''
        OR char_length(trimmed_query) > max_query_length THEN
        RAISE EXCEPTION 'search_query must be 1 to % characters', max_query_length
            USING ERRCODE = 'invalid_parameter_value';
    END IF;

    matching_query := websearch_to_tsquery('english', trimmed_query);

    RETURN QUERY
    SELECT
        date_trunc('month', n.received_date AT TIME ZONE 'America/Chicago')::DATE,
        count(*)::INTEGER,
        count(DISTINCT s.ward_number)::INTEGER
    FROM public.newsletters AS n
    LEFT JOIN public.sources AS s ON s.id = n.source_id
    WHERE n.search_vector @@ matching_query
    GROUP BY 1
    ORDER BY 1;
END;
$$;

ALTER FUNCTION "public"."search_term_timeline"("search_query" "text") OWNER TO "postgres";

COMMENT ON FUNCTION "public"."search_term_timeline"("search_query" "text") IS 'Newsletters matching a /search query (websearch_to_tsquery, english) per America/Chicago month, with distinct ward count. Read-only; RLS applies (SECURITY INVOKER).';

CREATE OR REPLACE FUNCTION "public"."update_updated_at_column"() RETURNS "trigger"
    LANGUAGE "plpgsql"
    AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

ALTER FUNCTION "public"."update_updated_at_column"() OWNER TO "postgres";

SET default_tablespace = '';

SET default_table_access_method = "heap";

CREATE TABLE IF NOT EXISTS "public"."email_source_mappings" (
    "id" integer NOT NULL,
    "email_pattern" "text" NOT NULL,
    "source_id" integer NOT NULL,
    "notes" "text",
    "created_at" timestamp with time zone DEFAULT "now"()
);

ALTER TABLE "public"."email_source_mappings" OWNER TO "postgres";

CREATE SEQUENCE IF NOT EXISTS "public"."email_source_mappings_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "public"."email_source_mappings_id_seq" OWNER TO "postgres";

ALTER SEQUENCE "public"."email_source_mappings_id_seq" OWNED BY "public"."email_source_mappings"."id";

CREATE TABLE IF NOT EXISTS "public"."newsletters" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"(),
    "email_uid" "text",
    "received_date" timestamp with time zone NOT NULL,
    "subject" "text" NOT NULL,
    "from_email" "text",
    "to_email" "text",
    "raw_html" "text",
    "plain_text" "text",
    "summary" "text",
    "topics" "text"[],
    "entities" "jsonb",
    "source_id" integer NOT NULL,
    "search_vector" "tsvector" GENERATED ALWAYS AS ("to_tsvector"('"english"'::"regconfig", ((COALESCE("subject", ''::"text") || ' '::"text") || COALESCE("plain_text", ''::"text")))) STORED,
    "relevance_score" integer,
    CONSTRAINT "newsletters_relevance_score_check" CHECK ((("relevance_score" >= 0) AND ("relevance_score" <= 10)))
);

ALTER TABLE "public"."newsletters" OWNER TO "postgres";

CREATE TABLE IF NOT EXISTS "public"."notification_history" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "newsletter_ids" "uuid"[] NOT NULL,
    "rule_ids" "uuid"[] NOT NULL,
    "digest_batch_id" "text",
    "delivery_type" "text" NOT NULL,
    "sent_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "success" boolean NOT NULL,
    "error_message" "text",
    "resend_email_id" "text",
    CONSTRAINT "notification_history_delivery_type_check" CHECK (("delivery_type" = ANY (ARRAY['immediate'::"text", 'daily_digest'::"text", 'weekly_digest'::"text"])))
);

ALTER TABLE "public"."notification_history" OWNER TO "postgres";

CREATE TABLE IF NOT EXISTS "public"."notification_queue" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "newsletter_id" "uuid",
    "rule_id" "uuid" NOT NULL,
    "status" "text" DEFAULT 'pending'::"text" NOT NULL,
    "digest_batch_id" "text",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "sent_at" timestamp with time zone,
    "error_message" "text",
    "notification_type" "text" DEFAULT 'daily'::"text",
    "report_id" "uuid",
    CONSTRAINT "check_one_content_id" CHECK (((("newsletter_id" IS NOT NULL) AND ("report_id" IS NULL)) OR (("newsletter_id" IS NULL) AND ("report_id" IS NOT NULL)))),
    CONSTRAINT "notification_queue_notification_type_check" CHECK (("notification_type" = ANY (ARRAY['daily'::"text", 'weekly'::"text"]))),
    CONSTRAINT "notification_queue_status_check" CHECK (("status" = ANY (ARRAY['pending'::"text", 'sent'::"text", 'failed'::"text"])))
);

ALTER TABLE "public"."notification_queue" OWNER TO "postgres";

CREATE TABLE IF NOT EXISTS "public"."notification_rules" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "user_id" "uuid" NOT NULL,
    "name" "text" NOT NULL,
    "is_active" boolean DEFAULT true NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "topics" "text"[] DEFAULT '{}'::"text"[] NOT NULL,
    "min_relevance_score" integer,
    "source_ids" integer[],
    "ward_numbers" "text"[],
    "search_term" "text",
    "delivery_frequency" "text" DEFAULT 'daily'::"text",
    CONSTRAINT "notification_rules_delivery_frequency_check" CHECK (("delivery_frequency" = ANY (ARRAY['daily'::"text", 'weekly'::"text"]))),
    CONSTRAINT "notification_rules_search_term_check" CHECK (("length"("search_term") <= 100)),
    CONSTRAINT "weekly_rules_no_ward_filter" CHECK ((("delivery_frequency" <> 'weekly'::"text") OR ("ward_numbers" IS NULL) OR ("array_length"("ward_numbers", 1) IS NULL)))
);

ALTER TABLE "public"."notification_rules" OWNER TO "postgres";

COMMENT ON CONSTRAINT "weekly_rules_no_ward_filter" ON "public"."notification_rules" IS 'Weekly summaries cover citywide activity and cannot be filtered by ward. Only daily digest notifications support ward filtering.';

CREATE TABLE IF NOT EXISTS "public"."sources" (
    "id" integer NOT NULL,
    "source_type" "text" NOT NULL,
    "name" "text" NOT NULL,
    "email_address" "text",
    "website" "text",
    "signup_url" "text",
    "ward_number" "text",
    "phone" "text",
    "newsletter_archive_url" "text"
);

ALTER TABLE "public"."sources" OWNER TO "postgres";

CREATE SEQUENCE IF NOT EXISTS "public"."sources_id_seq"
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;

ALTER SEQUENCE "public"."sources_id_seq" OWNER TO "postgres";

ALTER SEQUENCE "public"."sources_id_seq" OWNED BY "public"."sources"."id";

CREATE TABLE IF NOT EXISTS "public"."user_profiles" (
    "id" "uuid" NOT NULL,
    "email" "text" NOT NULL,
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "updated_at" timestamp with time zone DEFAULT "now"() NOT NULL,
    "notification_preferences" "jsonb" DEFAULT '{"enabled": true, "delivery_frequency": "daily"}'::"jsonb" NOT NULL
);

ALTER TABLE "public"."user_profiles" OWNER TO "postgres";

CREATE TABLE IF NOT EXISTS "public"."weekly_topic_reports" (
    "id" "uuid" DEFAULT "gen_random_uuid"() NOT NULL,
    "topic" "text" NOT NULL,
    "week_id" "text" NOT NULL,
    "report_summary" "text" NOT NULL,
    "newsletter_ids" "uuid"[] NOT NULL,
    "key_developments" "jsonb",
    "created_at" timestamp with time zone DEFAULT "now"() NOT NULL
);

ALTER TABLE "public"."weekly_topic_reports" OWNER TO "postgres";

ALTER TABLE ONLY "public"."email_source_mappings" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."email_source_mappings_id_seq"'::"regclass");

ALTER TABLE ONLY "public"."sources" ALTER COLUMN "id" SET DEFAULT "nextval"('"public"."sources_id_seq"'::"regclass");

ALTER TABLE ONLY "public"."email_source_mappings"
    ADD CONSTRAINT "email_source_mappings_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."newsletters"
    ADD CONSTRAINT "newsletters_email_uid_key" UNIQUE ("email_uid");

ALTER TABLE ONLY "public"."newsletters"
    ADD CONSTRAINT "newsletters_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."notification_history"
    ADD CONSTRAINT "notification_history_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."notification_queue"
    ADD CONSTRAINT "notification_queue_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."notification_rules"
    ADD CONSTRAINT "notification_rules_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."sources"
    ADD CONSTRAINT "sources_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."sources"
    ADD CONSTRAINT "sources_source_type_name_key" UNIQUE ("source_type", "name");

ALTER TABLE ONLY "public"."weekly_topic_reports"
    ADD CONSTRAINT "unique_topic_week" UNIQUE ("topic", "week_id");

ALTER TABLE ONLY "public"."user_profiles"
    ADD CONSTRAINT "user_profiles_pkey" PRIMARY KEY ("id");

ALTER TABLE ONLY "public"."weekly_topic_reports"
    ADD CONSTRAINT "weekly_topic_reports_pkey" PRIMARY KEY ("id");

CREATE INDEX "idx_email_source_mappings_pattern" ON "public"."email_source_mappings" USING "btree" ("email_pattern");

CREATE INDEX "idx_newsletters_relevance" ON "public"."newsletters" USING "btree" ("relevance_score");

CREATE INDEX "idx_newsletters_search" ON "public"."newsletters" USING "gin" ("search_vector");

CREATE INDEX "idx_newsletters_source_id" ON "public"."newsletters" USING "btree" ("source_id");

CREATE INDEX "idx_notification_history_batch" ON "public"."notification_history" USING "btree" ("digest_batch_id");

CREATE INDEX "idx_notification_history_success" ON "public"."notification_history" USING "btree" ("success", "sent_at" DESC);

CREATE INDEX "idx_notification_history_user" ON "public"."notification_history" USING "btree" ("user_id", "sent_at" DESC);

CREATE INDEX "idx_notification_queue_digest" ON "public"."notification_queue" USING "btree" ("digest_batch_id", "status");

CREATE INDEX "idx_notification_queue_report" ON "public"."notification_queue" USING "btree" ("report_id") WHERE ("report_id" IS NOT NULL);

CREATE INDEX "idx_notification_queue_status" ON "public"."notification_queue" USING "btree" ("status", "created_at");

CREATE INDEX "idx_notification_queue_type_status" ON "public"."notification_queue" USING "btree" ("notification_type", "status", "created_at");

CREATE INDEX "idx_notification_queue_user" ON "public"."notification_queue" USING "btree" ("user_id", "status");

CREATE INDEX "idx_notification_rules_active" ON "public"."notification_rules" USING "btree" ("user_id", "is_active");

CREATE INDEX "idx_notification_rules_frequency" ON "public"."notification_rules" USING "btree" ("delivery_frequency", "is_active");

CREATE INDEX "idx_notification_rules_user_id" ON "public"."notification_rules" USING "btree" ("user_id");

CREATE INDEX "idx_sources_phone" ON "public"."sources" USING "btree" ("phone");

CREATE INDEX "idx_sources_ward_number" ON "public"."sources" USING "btree" ("ward_number");

CREATE UNIQUE INDEX "idx_unique_newsletter_notif" ON "public"."notification_queue" USING "btree" ("user_id", "newsletter_id", "rule_id") WHERE ("newsletter_id" IS NOT NULL);

CREATE UNIQUE INDEX "idx_unique_report_notif" ON "public"."notification_queue" USING "btree" ("user_id", "report_id", "rule_id") WHERE ("report_id" IS NOT NULL);

CREATE INDEX "idx_user_profiles_email" ON "public"."user_profiles" USING "btree" ("email");

CREATE INDEX "idx_weekly_topic_reports_topic" ON "public"."weekly_topic_reports" USING "btree" ("topic");

CREATE INDEX "idx_weekly_topic_reports_topic_week" ON "public"."weekly_topic_reports" USING "btree" ("topic", "week_id");

CREATE INDEX "idx_weekly_topic_reports_week" ON "public"."weekly_topic_reports" USING "btree" ("week_id");

CREATE INDEX "newsletters_received_date_idx" ON "public"."newsletters" USING "btree" ("received_date" DESC);

CREATE INDEX "newsletters_topics_idx" ON "public"."newsletters" USING "gin" ("topics");

CREATE OR REPLACE TRIGGER "update_notification_rules_updated_at" BEFORE UPDATE ON "public"."notification_rules" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();

CREATE OR REPLACE TRIGGER "update_user_profiles_updated_at" BEFORE UPDATE ON "public"."user_profiles" FOR EACH ROW EXECUTE FUNCTION "public"."update_updated_at_column"();

ALTER TABLE ONLY "public"."email_source_mappings"
    ADD CONSTRAINT "email_source_mappings_source_id_fkey" FOREIGN KEY ("source_id") REFERENCES "public"."sources"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."newsletters"
    ADD CONSTRAINT "newsletters_source_id_fkey" FOREIGN KEY ("source_id") REFERENCES "public"."sources"("id") ON DELETE SET NULL;

ALTER TABLE ONLY "public"."notification_history"
    ADD CONSTRAINT "notification_history_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."notification_queue"
    ADD CONSTRAINT "notification_queue_newsletter_id_fkey" FOREIGN KEY ("newsletter_id") REFERENCES "public"."newsletters"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."notification_queue"
    ADD CONSTRAINT "notification_queue_report_id_fkey" FOREIGN KEY ("report_id") REFERENCES "public"."weekly_topic_reports"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."notification_queue"
    ADD CONSTRAINT "notification_queue_rule_id_fkey" FOREIGN KEY ("rule_id") REFERENCES "public"."notification_rules"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."notification_queue"
    ADD CONSTRAINT "notification_queue_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."notification_rules"
    ADD CONSTRAINT "notification_rules_user_id_fkey" FOREIGN KEY ("user_id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;

ALTER TABLE ONLY "public"."user_profiles"
    ADD CONSTRAINT "user_profiles_id_fkey" FOREIGN KEY ("id") REFERENCES "auth"."users"("id") ON DELETE CASCADE;

CREATE POLICY "Allow public read access" ON "public"."email_source_mappings" FOR SELECT USING (true);

CREATE POLICY "Public read newsletters" ON "public"."newsletters" FOR SELECT USING (true);

CREATE POLICY "Public read sources" ON "public"."sources" FOR SELECT USING (true);

CREATE POLICY "Service role can manage weekly topic reports" ON "public"."weekly_topic_reports" TO "service_role" USING (true) WITH CHECK (true);

CREATE POLICY "Service role insert newsletters" ON "public"."newsletters" FOR INSERT WITH CHECK (false);

CREATE POLICY "Service role update newsletters" ON "public"."newsletters" FOR UPDATE USING (false);

CREATE POLICY "Users can create own rules" ON "public"."notification_rules" FOR INSERT WITH CHECK (("auth"."uid"() = "user_id"));

CREATE POLICY "Users can delete own rules" ON "public"."notification_rules" FOR DELETE USING (("auth"."uid"() = "user_id"));

CREATE POLICY "Users can update own profile" ON "public"."user_profiles" FOR UPDATE USING (("auth"."uid"() = "id"));

CREATE POLICY "Users can update own rules" ON "public"."notification_rules" FOR UPDATE USING (("auth"."uid"() = "user_id"));

CREATE POLICY "Users can view own notification history" ON "public"."notification_history" FOR SELECT USING (("auth"."uid"() = "user_id"));

CREATE POLICY "Users can view own profile" ON "public"."user_profiles" FOR SELECT USING (("auth"."uid"() = "id"));

CREATE POLICY "Users can view own queued notifications" ON "public"."notification_queue" FOR SELECT USING (("auth"."uid"() = "user_id"));

CREATE POLICY "Users can view own rules" ON "public"."notification_rules" FOR SELECT USING (("auth"."uid"() = "user_id"));

ALTER TABLE "public"."email_source_mappings" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."newsletters" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."notification_history" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."notification_queue" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."notification_rules" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."sources" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."user_profiles" ENABLE ROW LEVEL SECURITY;

ALTER TABLE "public"."weekly_topic_reports" ENABLE ROW LEVEL SECURITY;

ALTER PUBLICATION "supabase_realtime" OWNER TO "postgres";

GRANT USAGE ON SCHEMA "public" TO "postgres";
GRANT USAGE ON SCHEMA "public" TO "anon";
GRANT USAGE ON SCHEMA "public" TO "authenticated";
GRANT USAGE ON SCHEMA "public" TO "service_role";

GRANT ALL ON FUNCTION "public"."count_user_rules"("user_uuid" "uuid") TO "anon";
GRANT ALL ON FUNCTION "public"."count_user_rules"("user_uuid" "uuid") TO "authenticated";
GRANT ALL ON FUNCTION "public"."count_user_rules"("user_uuid" "uuid") TO "service_role";

GRANT ALL ON FUNCTION "public"."create_user_profile"() TO "anon";
GRANT ALL ON FUNCTION "public"."create_user_profile"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."create_user_profile"() TO "service_role";

GRANT ALL ON FUNCTION "public"."get_active_weekly_topics"() TO "anon";
GRANT ALL ON FUNCTION "public"."get_active_weekly_topics"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_active_weekly_topics"() TO "service_role";

GRANT ALL ON FUNCTION "public"."get_week_date_range"("week_id_param" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."get_week_date_range"("week_id_param" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."get_week_date_range"("week_id_param" "text") TO "service_role";

REVOKE ALL ON FUNCTION "public"."search_term_timeline"("search_query" "text") FROM PUBLIC;
GRANT ALL ON FUNCTION "public"."search_term_timeline"("search_query" "text") TO "anon";
GRANT ALL ON FUNCTION "public"."search_term_timeline"("search_query" "text") TO "authenticated";
GRANT ALL ON FUNCTION "public"."search_term_timeline"("search_query" "text") TO "service_role";

GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "anon";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "authenticated";
GRANT ALL ON FUNCTION "public"."update_updated_at_column"() TO "service_role";

GRANT ALL ON TABLE "public"."email_source_mappings" TO "anon";
GRANT ALL ON TABLE "public"."email_source_mappings" TO "authenticated";
GRANT ALL ON TABLE "public"."email_source_mappings" TO "service_role";

GRANT ALL ON SEQUENCE "public"."email_source_mappings_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."email_source_mappings_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."email_source_mappings_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."newsletters" TO "anon";
GRANT ALL ON TABLE "public"."newsletters" TO "authenticated";
GRANT ALL ON TABLE "public"."newsletters" TO "service_role";

GRANT ALL ON TABLE "public"."notification_history" TO "anon";
GRANT ALL ON TABLE "public"."notification_history" TO "authenticated";
GRANT ALL ON TABLE "public"."notification_history" TO "service_role";

GRANT ALL ON TABLE "public"."notification_queue" TO "anon";
GRANT ALL ON TABLE "public"."notification_queue" TO "authenticated";
GRANT ALL ON TABLE "public"."notification_queue" TO "service_role";

GRANT ALL ON TABLE "public"."notification_rules" TO "anon";
GRANT ALL ON TABLE "public"."notification_rules" TO "authenticated";
GRANT ALL ON TABLE "public"."notification_rules" TO "service_role";

GRANT ALL ON TABLE "public"."sources" TO "anon";
GRANT ALL ON TABLE "public"."sources" TO "authenticated";
GRANT ALL ON TABLE "public"."sources" TO "service_role";

GRANT ALL ON SEQUENCE "public"."sources_id_seq" TO "anon";
GRANT ALL ON SEQUENCE "public"."sources_id_seq" TO "authenticated";
GRANT ALL ON SEQUENCE "public"."sources_id_seq" TO "service_role";

GRANT ALL ON TABLE "public"."user_profiles" TO "anon";
GRANT ALL ON TABLE "public"."user_profiles" TO "authenticated";
GRANT ALL ON TABLE "public"."user_profiles" TO "service_role";

GRANT ALL ON TABLE "public"."weekly_topic_reports" TO "anon";
GRANT ALL ON TABLE "public"."weekly_topic_reports" TO "authenticated";
GRANT ALL ON TABLE "public"."weekly_topic_reports" TO "service_role";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON SEQUENCES TO "service_role";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON FUNCTIONS TO "service_role";

ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "postgres";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "anon";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "authenticated";
ALTER DEFAULT PRIVILEGES FOR ROLE "postgres" IN SCHEMA "public" GRANT ALL ON TABLES TO "service_role";
