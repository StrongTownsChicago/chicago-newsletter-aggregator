import { defineMiddleware } from "astro:middleware";
import type { APIContext, MiddlewareNext } from "astro";
import { createRequestClient } from "./lib/supabase";
import { isNonProductionHost } from "./lib/seo";
import { getDefaultEdgeCache } from "./lib/server/edge-cache";
import { respondWithPageCache, resolvePageCacheVersion } from "./lib/server/page-cache";

// Inlined at build time (astro.config.mjs), so each deploy has its own page cache.
const pageCacheVersion = resolvePageCacheVersion(import.meta.env.BUILD_ID);

/** Restores the visitor's session into locals, then renders the page. */
async function renderWithSession(context: APIContext, next: MiddlewareNext): Promise<Response> {
  const supabase = createRequestClient();

  // Try to restore session from cookies. Prerendered pages are built without a
  // visitor's request, so there are no cookies to read.
  const accessToken = context.isPrerendered
    ? undefined
    : context.cookies.get("sb-access-token")?.value;
  const refreshToken = context.isPrerendered
    ? undefined
    : context.cookies.get("sb-refresh-token")?.value;

  if (accessToken && refreshToken) {
    await supabase.auth.setSession({
      access_token: accessToken,
      refresh_token: refreshToken,
    });
  }

  // Inject authenticated Supabase client into context
  context.locals.supabase = supabase;

  // Get current user session
  const {
    data: { session },
  } = await supabase.auth.getSession();

  context.locals.session = session;
  context.locals.user = session?.user ?? null;

  return next();
}

export const onRequest = defineMiddleware(async (context, next) => {
  // Anonymous views of public pages are served from the edge cache before any session work.
  const executionContext = context.locals.runtime?.ctx;
  const response = await respondWithPageCache(
    {
      method: context.request.method,
      url: context.url,
      isPrerendered: context.isPrerendered,
      readCookie: (name) => context.cookies.get(name)?.value,
    },
    {
      cache: getDefaultEdgeCache(),
      version: pageCacheVersion,
      waitUntil: executionContext && ((promise) => executionContext.waitUntil(promise)),
      setsCookies: () => !context.cookies.headers().next().done,
    },
    () => renderWithSession(context, next),
  );

  // Cloudflare Pages also serves *.pages.dev and preview hosts; keep them out of search indexes.
  if (isNonProductionHost(context.url.host, context.site)) {
    response.headers.set("X-Robots-Tag", "noindex");
  }

  return response;
});
