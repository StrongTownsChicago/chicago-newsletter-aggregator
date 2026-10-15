-- Migration: Search term timeline RPC
-- Description: Adds search_term_timeline(search_query), which counts the
--              newsletters matching a /search query per Chicago calendar month,
--              and how many distinct wards they came from. Powers the "when was
--              this mentioned" timeline on the public search page.
-- Date: 2026-10-14
--
-- Idempotent: CREATE OR REPLACE plus REVOKE/GRANT can be re-run safely.
-- No tables, columns, indexes or policies change.
--
-- ============================================================================
-- DESIGN NOTES
-- ============================================================================
-- * Same matching as /search: the search page filters with
--   search_vector @@ websearch_to_tsquery('english', <query>)
--   (supabase-js textSearch(..., { type: 'websearch', config: 'english' })).
--   With no other filters, the monthly newsletter_count values sum to the
--   search page's "Found N newsletters".
-- * Uses the existing GIN index idx_newsletters_search. The tsquery is held in
--   a PL/pgSQL variable, so the planner sees a parameter it can push into a
--   bitmap index scan. Only received_date, source_id and sources.ward_number are
--   read per match; plain_text and raw_html are never detoasted. The match is
--   the same work as the count query /search already runs on every view, and
--   the frontend caches responses at the edge per query.
-- * SECURITY INVOKER: runs with the caller's privileges, so the existing RLS
--   policies on newsletters and sources ("Public read ...") apply unchanged.
-- * search_path is pinned to '' and every relation is schema-qualified;
--   built-ins resolve through pg_catalog, which is always searched.
-- * statement_timeout in the definition: PostgREST 12+ (Supabase RPC) applies a
--   function's settings to the request transaction before calling it, so this
--   3s replaces the calling role's timeout (anon 3s, authenticated 8s) for the
--   call. Postgres itself does not re-arm the timer for a SET clause, so called
--   from plain SQL (e.g. the SQL editor) the session's own timeout governs.
-- * Input is limited to 1-200 characters after trimming (matches
--   SEARCH_TIMELINE_MAX_QUERY_LENGTH in frontend/src/lib/search-timeline.ts).
--   Anything else raises invalid_parameter_value (SQLSTATE 22023).
-- * Months with no matches are not returned; the frontend fills them with 0.

BEGIN;

CREATE OR REPLACE FUNCTION public.search_term_timeline(search_query TEXT)
RETURNS TABLE (month DATE, newsletter_count INTEGER, ward_count INTEGER)
LANGUAGE plpgsql
STABLE
SECURITY INVOKER
SET search_path = ''
SET statement_timeout = '3s'
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

COMMENT ON FUNCTION public.search_term_timeline(TEXT) IS
'Newsletters matching a /search query (websearch_to_tsquery, english) per America/Chicago month, with distinct ward count. Read-only; RLS applies (SECURITY INVOKER).';

-- New functions are executable by PUBLIC by default; grant explicitly instead.
-- newsletters and sources are public read-only, so the search page's anon
-- client and signed-in users may call it.
REVOKE ALL ON FUNCTION public.search_term_timeline(TEXT) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.search_term_timeline(TEXT) TO anon, authenticated, service_role;

COMMIT;

-- ============================================================================
-- VERIFICATION (run separately after applying; each is a single cheap query)
-- ============================================================================
-- Function exists, is STABLE, SECURITY INVOKER, with its settings:
-- SELECT proname, provolatile, prosecdef, proconfig
-- FROM pg_proc WHERE proname = 'search_term_timeline';
--   expect: provolatile = 's', prosecdef = false,
--           proconfig = {search_path="",statement_timeout=3s}
--
-- Uses the GIN index (look for idx_newsletters_search in the plan):
-- EXPLAIN SELECT count(*) FROM public.newsletters
-- WHERE search_vector @@ websearch_to_tsquery('english', 'snow removal');
--
-- One rare term:
-- SELECT * FROM public.search_term_timeline('snow removal');
--
-- Rollback:
-- DROP FUNCTION IF EXISTS public.search_term_timeline(TEXT);
