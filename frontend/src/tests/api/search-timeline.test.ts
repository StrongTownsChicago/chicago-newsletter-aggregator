import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import type { APIContext } from "astro";
import type { EdgeCache } from "../../lib/edge-cache";
import {
  SEARCH_TIMELINE_CACHE_CONTROL,
  SEARCH_TIMELINE_ERRORS,
  buildTimelineCacheKey,
  respondWithSearchTimeline,
} from "../../lib/search-timeline-endpoint";

const { mockRpc } = vi.hoisted(() => ({ mockRpc: vi.fn() }));

vi.mock("../../lib/supabase", () => ({
  supabase: { rpc: mockRpc },
}));

import { GET } from "../../pages/api/search-timeline";

const NOW = new Date("2026-03-15T12:00:00Z");
const ORIGIN = "https://example.test";

const requestUrl = (query: string | null, extraParams = "") => {
  const url = new URL("/api/search-timeline", ORIGIN);
  if (query !== null) url.searchParams.set("q", query);
  return new URL(`${url.href}${extraParams}`);
};

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

const rpcRows = [{ month: "2026-01-01", newsletter_count: 2, ward_count: 1 }];

describe("respondWithSearchTimeline", () => {
  beforeEach(() => {
    mockRpc.mockReset();
    vi.spyOn(console, "error").mockImplementation(() => {});
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const respond = (url: URL, cache: EdgeCache | null = null) =>
    respondWithSearchTimeline(url, { supabase: { rpc: mockRpc } as never, cache, now: NOW });

  it("returns filled months with edge-cacheable headers", async () => {
    mockRpc.mockResolvedValue({ data: rpcRows, error: null });

    const response = await respond(requestUrl("snow"));

    expect(response.status).toBe(200);
    expect(response.headers.get("Content-Type")).toBe("application/json");
    expect(response.headers.get("Cache-Control")).toBe(SEARCH_TIMELINE_CACHE_CONTROL.ok);
    expect(await response.json()).toEqual({
      months: [
        { month: "2026-01", newsletterCount: 2, wardCount: 1 },
        { month: "2026-02", newsletterCount: 0, wardCount: 0 },
        { month: "2026-03", newsletterCount: 0, wardCount: 0 },
      ],
    });
  });

  it("caches success at the edge and the browser with s-maxage", () => {
    expect(SEARCH_TIMELINE_CACHE_CONTROL.ok).toMatch(/^public, max-age=\d+, s-maxage=\d+$/);
    expect(SEARCH_TIMELINE_CACHE_CONTROL.unavailable).toMatch(/^public, .*s-maxage=\d+/);
  });

  it("passes the normalized query to the database", async () => {
    mockRpc.mockResolvedValue({ data: [], error: null });

    await respond(requestUrl("  speed   hump "));

    expect(mockRpc).toHaveBeenCalledWith("search_term_timeline", { search_query: "speed hump" });
  });

  it.each([
    ["missing", null],
    ["blank", "   "],
    ["too long", "a".repeat(201)],
  ])("rejects a %s query without touching the database", async (_label, query) => {
    const { cache } = createMemoryCache();

    const response = await respond(requestUrl(query), cache);

    expect(response.status).toBe(400);
    expect(response.headers.get("Cache-Control")).toBe(SEARCH_TIMELINE_CACHE_CONTROL.noStore);
    expect(await response.json()).toEqual({ error: SEARCH_TIMELINE_ERRORS.invalidQuery });
    expect(mockRpc).not.toHaveBeenCalled();
    expect(cache.match).not.toHaveBeenCalled();
  });

  it("returns a short-lived 404 when the database function is missing", async () => {
    mockRpc.mockResolvedValue({
      data: null,
      error: { code: "PGRST202", message: "Could not find the function" },
    });

    const response = await respond(requestUrl("snow"));

    expect(response.status).toBe(404);
    expect(response.headers.get("Cache-Control")).toBe(SEARCH_TIMELINE_CACHE_CONTROL.unavailable);
    expect(await response.json()).toEqual({ error: SEARCH_TIMELINE_ERRORS.unavailable });
  });

  it("returns an uncached 503 on other database errors", async () => {
    const { cache } = createMemoryCache();
    mockRpc.mockResolvedValue({
      data: null,
      error: { code: "57014", message: "canceling statement due to statement timeout" },
    });

    const response = await respond(requestUrl("snow"), cache);

    expect(response.status).toBe(503);
    expect(response.headers.get("Cache-Control")).toBe(SEARCH_TIMELINE_CACHE_CONTROL.noStore);
    expect(cache.put).not.toHaveBeenCalled();
  });

  it("returns 503 when the client throws", async () => {
    mockRpc.mockRejectedValue(new Error("network down"));

    const response = await respond(requestUrl("snow"));

    expect(response.status).toBe(503);
  });

  it("serves repeat queries from the edge cache with one database call", async () => {
    const { cache } = createMemoryCache();
    mockRpc.mockResolvedValue({ data: rpcRows, error: null });

    const first = await respond(requestUrl("snow"), cache);
    const second = await respond(requestUrl(" snow ", "&utm_source=x"), cache);

    expect(mockRpc).toHaveBeenCalledTimes(1);
    expect(cache.put).toHaveBeenCalledTimes(1);
    expect(second.status).toBe(200);
    expect(await second.json()).toEqual(await first.json());
  });

  it("caches the missing-function response", async () => {
    const { cache } = createMemoryCache();
    mockRpc.mockResolvedValue({ data: null, error: { code: "PGRST202", message: "missing" } });

    await respond(requestUrl("snow"), cache);
    const second = await respond(requestUrl("snow"), cache);

    expect(mockRpc).toHaveBeenCalledTimes(1);
    expect(second.status).toBe(404);
  });

  it("still answers when the edge cache fails", async () => {
    const cache: EdgeCache = {
      match: vi.fn().mockRejectedValue(new Error("cache down")),
      put: vi.fn().mockRejectedValue(new Error("cache down")),
    };
    mockRpc.mockResolvedValue({ data: rpcRows, error: null });

    const response = await respond(requestUrl("snow"), cache);

    expect(response.status).toBe(200);
  });
});

describe("buildTimelineCacheKey", () => {
  it("keys on the normalized query only", () => {
    const key = buildTimelineCacheKey(requestUrl("ignored", "&page=2"), "bike lanes");
    expect(key.url).toBe(`${ORIGIN}/api/search-timeline?q=bike+lanes`);
    expect(key.method).toBe("GET");
  });
});

describe("GET /api/search-timeline", () => {
  beforeEach(() => {
    mockRpc.mockReset();
  });

  it("uses the shared anon client and works without an edge cache", async () => {
    mockRpc.mockResolvedValue({ data: rpcRows, error: null });

    const response = await GET({ url: requestUrl("snow") } as unknown as APIContext);

    expect(response.status).toBe(200);
    expect(mockRpc).toHaveBeenCalledWith("search_term_timeline", { search_query: "snow" });
  });
});
