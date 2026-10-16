/**
 * Thin wrapper over the Cloudflare Workers Cache API (`caches.default`).
 *
 * Cloudflare does not cache Pages Function responses from `Cache-Control`
 * alone, so endpoints that should be served from the edge store responses
 * explicitly. The cache honors each stored response's `Cache-Control`
 * (`s-maxage` first) for its lifetime. Outside Workers (dev server, tests)
 * there is no default cache and callers simply skip caching.
 */

/** The subset of the Workers `Cache` interface used here. */
export interface EdgeCache {
  match(request: Request): Promise<Response | undefined>;
  put(request: Request, response: Response): Promise<void>;
}

/** The Workers default cache, or null when not running on Cloudflare. */
export function getDefaultEdgeCache(): EdgeCache | null {
  const cacheStorage = (globalThis as { caches?: { default?: EdgeCache } })
    .caches;
  return cacheStorage?.default ?? null;
}

/** Looks up a cached response; a cache failure is treated as a miss. */
export async function matchEdgeCache(
  cache: EdgeCache | null,
  cacheKey: Request,
): Promise<Response | undefined> {
  if (!cache) return undefined;
  try {
    return await cache.match(cacheKey);
  } catch (error) {
    console.error("Edge cache lookup failed:", error);
    return undefined;
  }
}

/** Stores a response; a cache failure is logged and otherwise ignored. */
export async function putEdgeCache(
  cache: EdgeCache | null,
  cacheKey: Request,
  response: Response,
): Promise<void> {
  if (!cache) return;
  try {
    await cache.put(cacheKey, response);
  } catch (error) {
    console.error("Edge cache store failed:", error);
  }
}
