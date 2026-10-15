import type { SupabaseClient } from "@supabase/supabase-js";
import { matchEdgeCache, putEdgeCache, type EdgeCache } from "./edge-cache";
import {
  SEARCH_TIMELINE_QUERY_PARAM,
  buildTimelineApiUrl,
  fetchSearchTimeline,
  normalizeTimelineQuery,
  type SearchTimelineResponseBody,
} from "./search-timeline";

/**
 * Request handling for `GET /api/search-timeline?q=...`, kept separate from
 * the route file so it can be tested with an injected client and cache.
 *
 * Responses are shared by everyone (anon client, no cookies), so successful
 * and "not deployed" responses are cached at the edge per normalized query.
 * That keeps database load to one call per distinct query per cache lifetime.
 */

const SECONDS_PER_MINUTE = 60;

/** Browser cache lifetime for a timeline. */
const TIMELINE_BROWSER_MAX_AGE_SECONDS = 10 * SECONDS_PER_MINUTE;
/** Edge cache lifetime for a timeline; new newsletters arrive about daily. */
const TIMELINE_EDGE_MAX_AGE_SECONDS = 60 * SECONDS_PER_MINUTE;
/**
 * Cache lifetime while the database function is missing, so the timeline
 * appears soon after the migration is applied.
 */
const UNAVAILABLE_MAX_AGE_SECONDS = 5 * SECONDS_PER_MINUTE;

export const SEARCH_TIMELINE_CACHE_CONTROL = {
  ok: `public, max-age=${TIMELINE_BROWSER_MAX_AGE_SECONDS}, s-maxage=${TIMELINE_EDGE_MAX_AGE_SECONDS}`,
  unavailable: `public, max-age=${UNAVAILABLE_MAX_AGE_SECONDS}, s-maxage=${UNAVAILABLE_MAX_AGE_SECONDS}`,
  noStore: "no-store",
} as const;

export const SEARCH_TIMELINE_ERRORS = {
  invalidQuery: "invalid_query",
  unavailable: "timeline_unavailable",
  failed: "timeline_failed",
} as const;

const HTTP_STATUS = {
  ok: 200,
  badRequest: 400,
  notFound: 404,
  serviceUnavailable: 503,
} as const;

export interface SearchTimelineRequestDependencies {
  supabase: Pick<SupabaseClient, "rpc">;
  cache: EdgeCache | null;
  now: Date;
}

const jsonResponse = (
  body: SearchTimelineResponseBody | { error: string },
  status: number,
  cacheControl: string,
): Response =>
  new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json",
      "Cache-Control": cacheControl,
    },
  });

/** Cache key for a normalized query, independent of other URL parameters. */
export function buildTimelineCacheKey(requestUrl: URL, query: string): Request {
  return new Request(new URL(buildTimelineApiUrl(query), requestUrl.origin));
}

/** Builds the timeline response for a fresh (uncached) request. */
async function buildTimelineResponse(
  query: string,
  { supabase, now }: SearchTimelineRequestDependencies,
): Promise<Response> {
  const result = await fetchSearchTimeline(supabase, query, now);
  return result.status === "ok"
    ? jsonResponse(
        { months: result.months },
        HTTP_STATUS.ok,
        SEARCH_TIMELINE_CACHE_CONTROL.ok,
      )
    : jsonResponse(
        { error: SEARCH_TIMELINE_ERRORS.unavailable },
        HTTP_STATUS.notFound,
        SEARCH_TIMELINE_CACHE_CONTROL.unavailable,
      );
}

/**
 * Responds to a timeline request: validates the query, serves from the edge
 * cache when possible, and otherwise queries the database and caches the
 * result. Database errors return 503 and are never cached.
 */
export async function respondWithSearchTimeline(
  requestUrl: URL,
  dependencies: SearchTimelineRequestDependencies,
): Promise<Response> {
  const query = normalizeTimelineQuery(
    requestUrl.searchParams.get(SEARCH_TIMELINE_QUERY_PARAM),
  );
  if (query === null) {
    return jsonResponse(
      { error: SEARCH_TIMELINE_ERRORS.invalidQuery },
      HTTP_STATUS.badRequest,
      SEARCH_TIMELINE_CACHE_CONTROL.noStore,
    );
  }

  const cacheKey = buildTimelineCacheKey(requestUrl, query);
  const cachedResponse = await matchEdgeCache(dependencies.cache, cacheKey);
  if (cachedResponse) return cachedResponse;

  let response: Response;
  try {
    response = await buildTimelineResponse(query, dependencies);
  } catch (error) {
    console.error("Search timeline query failed:", error);
    return jsonResponse(
      { error: SEARCH_TIMELINE_ERRORS.failed },
      HTTP_STATUS.serviceUnavailable,
      SEARCH_TIMELINE_CACHE_CONTROL.noStore,
    );
  }

  await putEdgeCache(dependencies.cache, cacheKey, response.clone());
  return response;
}
