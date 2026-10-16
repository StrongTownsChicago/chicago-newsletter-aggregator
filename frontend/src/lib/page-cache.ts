import { matchEdgeCache, putEdgeCache, type EdgeCache } from "./edge-cache";

/**
 * Edge caching of public server-rendered pages for anonymous visitors, so
 * repeat views don't query Supabase. Pages Functions responses bypass
 * Cloudflare's CDN cache, so pages are stored explicitly with the Workers
 * Cache API (see `edge-cache.ts`). The middleware wires this in before any
 * session work, so a hit costs no database call.
 *
 * The cache key carries a per-build id, so each deploy starts with an empty
 * cache (cached HTML references hashed assets that a deploy removes).
 */

const SECONDS_PER_MINUTE = 60;
const SECONDS_PER_DAY = 24 * 60 * SECONDS_PER_MINUTE;

/** Newsletters don't change after ingestion, which also writes their summary. */
const NEWSLETTER_EDGE_MAX_AGE_SECONDS = 30 * SECONDS_PER_DAY;
/** Listings change when ingestion runs, about every two hours. */
const LISTING_EDGE_MAX_AGE_SECONDS = 10 * SECONDS_PER_MINUTE;

interface PageCacheRule {
  pattern: RegExp;
  edgeMaxAgeSeconds: number;
}

/**
 * Cacheable routes. Anything not listed (account and token pages, API
 * routes, sitemaps) is never cached. Paths are matched without a trailing slash.
 */
const PAGE_CACHE_RULES: readonly PageCacheRule[] = [
  { pattern: /^\/newsletter\/[^/]+$/, edgeMaxAgeSeconds: NEWSLETTER_EDGE_MAX_AGE_SECONDS },
  { pattern: /^\/$/, edgeMaxAgeSeconds: LISTING_EDGE_MAX_AGE_SECONDS },
  { pattern: /^\/search$/, edgeMaxAgeSeconds: LISTING_EDGE_MAX_AGE_SECONDS },
  { pattern: /^\/wards$/, edgeMaxAgeSeconds: LISTING_EDGE_MAX_AGE_SECONDS },
  { pattern: /^\/ward\/[^/]+$/, edgeMaxAgeSeconds: LISTING_EDGE_MAX_AGE_SECONDS },
  { pattern: /^\/analytics$/, edgeMaxAgeSeconds: LISTING_EDGE_MAX_AGE_SECONDS },
];

/** Cookies that mark a signed-in visitor, whose pages are never cached. */
export const SESSION_COOKIE_NAMES = ["sb-access-token", "sb-refresh-token"] as const;

export const PAGE_CACHE_HEADER = "X-Page-Cache";
export type PageCacheStatus = "hit" | "miss" | "bypass";

/** Query parameter that carries the build version in cache keys. */
export const PAGE_CACHE_VERSION_PARAM = "__page_cache_version";
/** Version used when no build id was inlined (dev server, tests). */
export const UNVERSIONED_PAGE_CACHE_VERSION = "unversioned";

/**
 * Browsers revalidate every view, so a visitor who just signed in never sees a
 * cached "Sign in" header. Only the edge keeps pages.
 */
export const BROWSER_CACHE_CONTROL = "no-cache";
/** Set by a page on its response to keep it out of the cache (e.g. a failed load). */
export const UNCACHEABLE_PAGE_CACHE_CONTROL = "no-store";

const HTTP_STATUS_OK = 200;
const CACHE_CONTROL_OPT_OUT_PATTERN = /\b(no-store|private)\b/i;
const NO_STORE_PATTERN = /\bno-store\b/i;
/** Link-tracking parameters that don't change a page, dropped from cache keys. */
const TRACKING_PARAM_PATTERN = /^(utm_.+|fbclid|gclid|mc_cid|mc_eid)$/i;

/** Edge lifetime for a path, or null when the route is not cacheable. */
export function findPageCacheMaxAge(pathname: string): number | null {
  const normalizedPath = pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const rule = PAGE_CACHE_RULES.find(({ pattern }) => pattern.test(normalizedPath));
  return rule?.edgeMaxAgeSeconds ?? null;
}

/** The build version for cache keys, falling back when none was inlined. */
export function resolvePageCacheVersion(buildVersion: string | undefined): string {
  return buildVersion?.trim() || UNVERSIONED_PAGE_CACHE_VERSION;
}

/**
 * Cache key for a page: the full request URL (so host and query are part of
 * it) without tracking parameters, plus the build version.
 */
export function buildPageCacheKey(url: URL, version: string): Request {
  const keyUrl = new URL(url);
  for (const name of [...keyUrl.searchParams.keys()]) {
    if (TRACKING_PARAM_PATTERN.test(name)) keyUrl.searchParams.delete(name);
  }
  keyUrl.searchParams.set(PAGE_CACHE_VERSION_PARAM, version);
  return new Request(keyUrl);
}

/**
 * Only plain successful pages are stored: no redirects or errors, nothing
 * that sets cookies, and nothing the page marked `no-store` or `private`.
 */
export function isStorablePageResponse(response: Response, setsCookies: boolean): boolean {
  if (response.status !== HTTP_STATUS_OK) return false;
  if (setsCookies || response.headers.has("Set-Cookie")) return false;
  const cacheControl = response.headers.get("Cache-Control") ?? "";
  return !CACHE_CONTROL_OPT_OUT_PATTERN.test(cacheControl);
}

/** The copy to store at the edge; the Cache API honors its `s-maxage`. */
export function buildStoredPageCopy(response: Response, edgeMaxAgeSeconds: number): Response {
  const storedCopy = new Response(response.clone().body, response);
  storedCopy.headers.set("Cache-Control", `public, s-maxage=${edgeMaxAgeSeconds}`);
  return storedCopy;
}

/**
 * The response for the browser, with mutable headers: browser-facing
 * `Cache-Control` (a page's `no-store` is kept) and the cache status.
 */
export function buildBrowserPageResponse(response: Response, status: PageCacheStatus): Response {
  const browserResponse = new Response(response.body, response);
  const cacheControl = response.headers.get("Cache-Control") ?? "";
  if (!NO_STORE_PATTERN.test(cacheControl)) {
    browserResponse.headers.set("Cache-Control", BROWSER_CACHE_CONTROL);
  }
  browserResponse.headers.set(PAGE_CACHE_HEADER, status);
  return browserResponse;
}

export interface PageCacheRequest {
  method: string;
  url: URL;
  isPrerendered: boolean;
  readCookie: (name: string) => string | undefined;
}

export interface PageCacheDependencies {
  cache: EdgeCache | null;
  version: string;
  /** Keeps the store running after the response is sent; awaited when absent. */
  waitUntil?: (promise: Promise<unknown>) => void;
  /** Whether rendering set cookies (checked after rendering). */
  setsCookies: () => boolean;
}

/**
 * Serves a page from the edge cache when possible. Otherwise renders it with
 * `render` (which does the session and database work) and stores a storable
 * result. Requests outside the rules are rendered untouched.
 */
export async function respondWithPageCache(
  request: PageCacheRequest,
  dependencies: PageCacheDependencies,
  render: () => Promise<Response>,
): Promise<Response> {
  if (request.method !== "GET" || request.isPrerendered) return render();
  const edgeMaxAgeSeconds = findPageCacheMaxAge(request.url.pathname);
  if (edgeMaxAgeSeconds === null) return render();

  const isSignedIn = SESSION_COOKIE_NAMES.some((name) => request.readCookie(name));
  if (isSignedIn) return buildBrowserPageResponse(await render(), "bypass");

  const { cache, version, waitUntil, setsCookies } = dependencies;
  const cacheKey = buildPageCacheKey(request.url, version);
  const cachedResponse = await matchEdgeCache(cache, cacheKey);
  if (cachedResponse) return buildBrowserPageResponse(cachedResponse, "hit");

  const response = await render();
  if (cache && isStorablePageResponse(response, setsCookies())) {
    const store = putEdgeCache(cache, cacheKey, buildStoredPageCopy(response, edgeMaxAgeSeconds));
    if (waitUntil) {
      waitUntil(store);
    } else {
      await store;
    }
  }
  return buildBrowserPageResponse(response, "miss");
}
