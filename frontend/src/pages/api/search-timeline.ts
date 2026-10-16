export const prerender = false;
import type { APIRoute } from "astro";
import { supabase } from "../../lib/supabase";
import { getDefaultEdgeCache } from "../../lib/server/edge-cache";
import { respondWithSearchTimeline } from "../../lib/server/search-timeline-endpoint";

/**
 * Monthly match counts for a search query, loaded by the /search page timeline.
 * Uses the shared anon client (never the visitor's session) so responses are
 * identical for everyone and safe to cache at the edge.
 */
export const GET: APIRoute = ({ url }) =>
  respondWithSearchTimeline(url, {
    supabase,
    cache: getDefaultEdgeCache(),
    now: new Date(),
  });
