// Node, like Workers, keeps Set-Cookie on responses; happy-dom strips it.
// @vitest-environment node
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { EdgeCache } from "../../lib/edge-cache";
import {
  BROWSER_CACHE_CONTROL,
  PAGE_CACHE_HEADER,
  PAGE_CACHE_VERSION_PARAM,
  UNCACHEABLE_PAGE_CACHE_CONTROL,
  UNVERSIONED_PAGE_CACHE_VERSION,
  buildBrowserPageResponse,
  buildPageCacheKey,
  buildStoredPageCopy,
  findPageCacheMaxAge,
  hasTrackingParams,
  isStorablePageResponse,
  resolvePageCacheVersion,
  respondWithPageCache,
  type PageCacheDependencies,
  type PageCacheRequest,
} from "../../lib/page-cache";

const ORIGIN = "https://example.test";
const VERSION = "abc123-1700000000000";
const THIRTY_DAYS_SECONDS = 30 * 24 * 60 * 60;
const TEN_MINUTES_SECONDS = 10 * 60;

/** In-memory stand-in for the Workers Cache API. */
const createMemoryCache = () => {
  const entries = new Map<string, Response>();
  const cache = {
    match: vi.fn(async (request: Request) => entries.get(request.url)?.clone()),
    put: vi.fn(async (request: Request, response: Response) => {
      entries.set(request.url, response);
    }),
  };
  return { cache, entries };
};

const htmlResponse = (body = "<p>page</p>", init: ResponseInit = {}) =>
  new Response(body, { status: 200, headers: { "Content-Type": "text/html" }, ...init });

describe("findPageCacheMaxAge", () => {
  it.each(["/newsletter/123", "/newsletter/123/"])("caches %s for 30 days", (path) => {
    expect(findPageCacheMaxAge(path)).toBe(THIRTY_DAYS_SECONDS);
  });

  it.each(["/", "/search", "/wards", "/ward/1", "/ward/50/", "/analytics"])(
    "caches %s for 10 minutes",
    (path) => {
      expect(findPageCacheMaxAge(path)).toBe(TEN_MINUTES_SECONDS);
    },
  );

  it.each([
    "/preferences",
    "/unsubscribe",
    "/login",
    "/signup",
    "/api/search-timeline",
    "/api/notifications/create-rule",
    "/sitemap-newsletters.xml",
    "/sitemap-wards.xml",
    "/reports",
    "/newsletter",
    "/newsletter/1/extra",
    "/ward/1/extra",
    "/searching",
  ])("does not cache %s", (path) => {
    expect(findPageCacheMaxAge(path)).toBeNull();
  });
});

describe("resolvePageCacheVersion", () => {
  it("uses the build id when present", () => {
    expect(resolvePageCacheVersion(VERSION)).toBe(VERSION);
  });

  it.each([undefined, "", "  "])("falls back when the build id is %j", (buildId) => {
    expect(resolvePageCacheVersion(buildId)).toBe(UNVERSIONED_PAGE_CACHE_VERSION);
  });
});

describe("buildPageCacheKey", () => {
  it("keeps host, path and query and adds the version", () => {
    const key = buildPageCacheKey(new URL(`${ORIGIN}/search?q=snow&page=2`), VERSION);
    const keyUrl = new URL(key.url);

    expect(keyUrl.origin).toBe(ORIGIN);
    expect(keyUrl.pathname).toBe("/search");
    expect(keyUrl.searchParams.get("q")).toBe("snow");
    expect(keyUrl.searchParams.get("page")).toBe("2");
    expect(keyUrl.searchParams.get(PAGE_CACHE_VERSION_PARAM)).toBe(VERSION);
    expect(key.method).toBe("GET");
  });

  it("gives each build its own key", () => {
    const url = new URL(`${ORIGIN}/wards`);
    expect(buildPageCacheKey(url, "build-a").url).not.toBe(buildPageCacheKey(url, "build-b").url);
  });

  it("gives each host its own key", () => {
    const productionKey = buildPageCacheKey(new URL(`${ORIGIN}/wards`), VERSION);
    const previewKey = buildPageCacheKey(new URL("https://preview.pages.dev/wards"), VERSION);
    expect(productionKey.url).not.toBe(previewKey.url);
  });

  it("drops link-tracking parameters", () => {
    const tracked = buildPageCacheKey(
      new URL(`${ORIGIN}/newsletter/7?utm_source=fb&fbclid=xyz&gclid=1&mc_cid=2&mc_eid=3`),
      VERSION,
    );
    expect(tracked.url).toBe(buildPageCacheKey(new URL(`${ORIGIN}/newsletter/7`), VERSION).url);
  });

  it("detects link-tracking parameters", () => {
    expect(hasTrackingParams(new URL(`${ORIGIN}/search?q=x&UTM_Campaign=a`))).toBe(true);
    expect(hasTrackingParams(new URL(`${ORIGIN}/search?q=utm_source`))).toBe(false);
  });

  it("does not change the request URL it was given", () => {
    const url = new URL(`${ORIGIN}/newsletter/7?utm_source=fb`);
    buildPageCacheKey(url, VERSION);
    expect(url.href).toBe(`${ORIGIN}/newsletter/7?utm_source=fb`);
  });
});

describe("isStorablePageResponse", () => {
  it("stores a plain 200 page", () => {
    expect(isStorablePageResponse(htmlResponse(), false)).toBe(true);
  });

  it.each([302, 301, 404, 500])("does not store status %i", (status) => {
    expect(isStorablePageResponse(new Response(null, { status }), false)).toBe(false);
  });

  it("does not store a response with a Set-Cookie header", () => {
    const response = htmlResponse("<p/>", { headers: { "Set-Cookie": "a=b" } });
    expect(isStorablePageResponse(response, false)).toBe(false);
  });

  it("does not store a response whose render set cookies", () => {
    expect(isStorablePageResponse(htmlResponse(), true)).toBe(false);
  });

  it.each([UNCACHEABLE_PAGE_CACHE_CONTROL, "private, max-age=0"])(
    "does not store a page marked %s",
    (cacheControl) => {
      const response = htmlResponse("<p/>", { headers: { "Cache-Control": cacheControl } });
      expect(isStorablePageResponse(response, false)).toBe(false);
    },
  );
});

describe("buildStoredPageCopy", () => {
  it("sets the edge lifetime and keeps the body and headers", async () => {
    const response = htmlResponse("<p>hello</p>");
    const storedCopy = buildStoredPageCopy(response, TEN_MINUTES_SECONDS);

    expect(storedCopy.headers.get("Cache-Control")).toBe(`public, s-maxage=${TEN_MINUTES_SECONDS}`);
    expect(storedCopy.headers.get("Content-Type")).toBe("text/html");
    expect(await storedCopy.text()).toBe("<p>hello</p>");
    expect(await response.text()).toBe("<p>hello</p>");
  });
});

describe("buildBrowserPageResponse", () => {
  it("replaces the edge lifetime with browser revalidation on a hit", () => {
    const cached = htmlResponse("<p/>", { headers: { "Cache-Control": "public, s-maxage=600" } });
    const response = buildBrowserPageResponse(cached, "hit");

    expect(response.headers.get("Cache-Control")).toBe(BROWSER_CACHE_CONTROL);
    expect(response.headers.get(PAGE_CACHE_HEADER)).toBe("hit");
  });

  it("keeps a page's no-store", () => {
    const rendered = htmlResponse("<p/>", {
      headers: { "Cache-Control": UNCACHEABLE_PAGE_CACHE_CONTROL },
    });
    const response = buildBrowserPageResponse(rendered, "miss");

    expect(response.headers.get("Cache-Control")).toBe(UNCACHEABLE_PAGE_CACHE_CONTROL);
  });
});

describe("respondWithPageCache", () => {
  let memory: ReturnType<typeof createMemoryCache>;

  beforeEach(() => {
    memory = createMemoryCache();
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const pageRequest = (
    path: string,
    overrides: Partial<PageCacheRequest> = {},
  ): PageCacheRequest => ({
    method: "GET",
    url: new URL(path, ORIGIN),
    isPrerendered: false,
    readCookie: () => undefined,
    ...overrides,
  });

  const dependencies = (overrides: Partial<PageCacheDependencies> = {}): PageCacheDependencies => ({
    cache: memory.cache as EdgeCache,
    version: VERSION,
    setsCookies: () => false,
    ...overrides,
  });

  it("renders and stores on a miss, then serves the stored page", async () => {
    const render = vi.fn(async () => htmlResponse("<p>ward</p>"));

    const first = await respondWithPageCache(pageRequest("/ward/1"), dependencies(), render);
    expect(first.headers.get(PAGE_CACHE_HEADER)).toBe("miss");
    expect(first.headers.get("Cache-Control")).toBe(BROWSER_CACHE_CONTROL);
    expect(await first.text()).toBe("<p>ward</p>");

    const [[storedKey, storedCopy]] = memory.cache.put.mock.calls;
    expect(new URL(storedKey.url).searchParams.get(PAGE_CACHE_VERSION_PARAM)).toBe(VERSION);
    expect(storedCopy.headers.get("Cache-Control")).toBe(`public, s-maxage=${TEN_MINUTES_SECONDS}`);

    const second = await respondWithPageCache(pageRequest("/ward/1"), dependencies(), render);
    expect(second.headers.get(PAGE_CACHE_HEADER)).toBe("hit");
    expect(second.headers.get("Cache-Control")).toBe(BROWSER_CACHE_CONTROL);
    expect(await second.text()).toBe("<p>ward</p>");
    expect(render).toHaveBeenCalledTimes(1);
  });

  it("stores newsletter pages for 30 days", async () => {
    await respondWithPageCache(pageRequest("/newsletter/9"), dependencies(), async () =>
      htmlResponse(),
    );

    const [[, storedCopy]] = memory.cache.put.mock.calls;
    expect(storedCopy.headers.get("Cache-Control")).toBe(`public, s-maxage=${THIRTY_DAYS_SECONDS}`);
  });

  it("hands the store to waitUntil instead of awaiting it", async () => {
    const waitUntil = vi.fn();

    await respondWithPageCache(pageRequest("/"), dependencies({ waitUntil }), async () =>
      htmlResponse(),
    );

    expect(waitUntil).toHaveBeenCalledWith(expect.any(Promise));
    await waitUntil.mock.calls[0][0];
    expect(memory.cache.put).toHaveBeenCalledTimes(1);
  });

  it.each(["sb-access-token", "sb-refresh-token"])(
    "bypasses the cache when %s is present",
    async (cookieName) => {
      const readCookie = (name: string) => (name === cookieName ? "token" : undefined);
      const render = vi.fn(async () => htmlResponse());

      const response = await respondWithPageCache(
        pageRequest("/", { readCookie }),
        dependencies(),
        render,
      );

      expect(response.headers.get(PAGE_CACHE_HEADER)).toBe("bypass");
      expect(response.headers.get("Cache-Control")).toBe(BROWSER_CACHE_CONTROL);
      expect(memory.cache.match).not.toHaveBeenCalled();
      expect(memory.cache.put).not.toHaveBeenCalled();
      expect(render).toHaveBeenCalledTimes(1);
    },
  );

  it.each([
    ["a POST request", pageRequest("/search", { method: "POST" })],
    ["a prerendered page", pageRequest("/", { isPrerendered: true })],
    ["a route outside the allowlist", pageRequest("/preferences")],
  ])("leaves %s untouched", async (_label, request) => {
    const rendered = htmlResponse();
    const readCookie = vi.fn(() => undefined);

    const response = await respondWithPageCache(
      { ...request, readCookie },
      dependencies(),
      async () => rendered,
    );

    expect(response).toBe(rendered);
    expect(response.headers.get(PAGE_CACHE_HEADER)).toBeNull();
    expect(readCookie).not.toHaveBeenCalled();
    expect(memory.cache.match).not.toHaveBeenCalled();
  });

  it("serves a tracked visit from the cache but never stores its render", async () => {
    const trackedPath = "/search?q=bike&utm_source=newsletter&mc_eid=subscriber42";
    const render = vi.fn(async () => htmlResponse(`<a href="${trackedPath}">All months</a>`));

    const trackedMiss = await respondWithPageCache(pageRequest(trackedPath), dependencies(), render);
    expect(trackedMiss.headers.get(PAGE_CACHE_HEADER)).toBe("miss");
    expect(memory.cache.put).not.toHaveBeenCalled();

    await respondWithPageCache(pageRequest("/search?q=bike"), dependencies(), async () =>
      htmlResponse("<p>clean</p>"),
    );
    const trackedHit = await respondWithPageCache(pageRequest(trackedPath), dependencies(), render);
    expect(trackedHit.headers.get(PAGE_CACHE_HEADER)).toBe("hit");
    expect(await trackedHit.text()).toBe("<p>clean</p>");
    expect(render).toHaveBeenCalledTimes(1);
  });

  it("does not store a redirect", async () => {
    const response = await respondWithPageCache(
      pageRequest("/newsletter/404"),
      dependencies(),
      async () => new Response(null, { status: 302, headers: { Location: "/404" } }),
    );

    expect(response.status).toBe(302);
    expect(response.headers.get(PAGE_CACHE_HEADER)).toBe("miss");
    expect(memory.cache.put).not.toHaveBeenCalled();
  });

  it("does not store a page whose render set cookies", async () => {
    await respondWithPageCache(
      pageRequest("/"),
      dependencies({ setsCookies: () => true }),
      async () => htmlResponse(),
    );

    expect(memory.cache.put).not.toHaveBeenCalled();
  });

  it("does not store a page that failed to load", async () => {
    const response = await respondWithPageCache(pageRequest("/wards"), dependencies(), async () =>
      htmlResponse("<p/>", { headers: { "Cache-Control": UNCACHEABLE_PAGE_CACHE_CONTROL } }),
    );

    expect(response.headers.get("Cache-Control")).toBe(UNCACHEABLE_PAGE_CACHE_CONTROL);
    expect(memory.cache.put).not.toHaveBeenCalled();
  });

  it("does not serve a page cached by a previous build", async () => {
    const render = vi.fn(async () => htmlResponse());
    await respondWithPageCache(pageRequest("/"), dependencies({ version: "old" }), render);

    const response = await respondWithPageCache(
      pageRequest("/"),
      dependencies({ version: "new" }),
      render,
    );

    expect(response.headers.get(PAGE_CACHE_HEADER)).toBe("miss");
    expect(render).toHaveBeenCalledTimes(2);
  });

  it("renders without caching when there is no edge cache", async () => {
    const response = await respondWithPageCache(
      pageRequest("/"),
      dependencies({ cache: null }),
      async () => htmlResponse(),
    );

    expect(response.status).toBe(200);
    expect(response.headers.get(PAGE_CACHE_HEADER)).toBe("miss");
  });

  it("treats a failed lookup as a miss", async () => {
    memory.cache.match.mockRejectedValueOnce(new Error("cache down"));

    const response = await respondWithPageCache(pageRequest("/"), dependencies(), async () =>
      htmlResponse(),
    );

    expect(response.headers.get(PAGE_CACHE_HEADER)).toBe("miss");
    expect(response.status).toBe(200);
  });
});
