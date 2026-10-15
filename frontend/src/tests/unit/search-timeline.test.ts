import { describe, it, expect, vi } from "vitest";
import {
  SEARCH_TIMELINE_MAX_QUERY_LENGTH,
  SEARCH_TIMELINE_RPC,
  barHeightPercent,
  buildTimelineApiUrl,
  fetchSearchTimeline,
  fillTimelineMonths,
  formatTimelineMonth,
  getChicagoMonth,
  isMissingFunctionError,
  normalizeTimelineQuery,
  parseTimelineResponseBody,
  parseTimelineRpcRows,
  summarizeTimeline,
} from "../../lib/search-timeline";

const month = (value: string, newsletterCount: number, wardCount: number) => ({
  month: value,
  newsletterCount,
  wardCount,
});

describe("normalizeTimelineQuery", () => {
  it("trims and collapses whitespace", () => {
    expect(normalizeTimelineQuery("  snow \t  removal\n")).toBe("snow removal");
  });

  it("keeps non-ASCII spaces inside the query, which Postgres may not split on", () => {
    expect(normalizeTimelineQuery(" snow -removal ")).toBe("snow -removal");
  });

  it("keeps websearch syntax and case intact", () => {
    expect(normalizeTimelineQuery('"Speed Hump" or -parking')).toBe(
      '"Speed Hump" or -parking',
    );
  });

  it("rejects empty, whitespace-only and missing queries", () => {
    expect(normalizeTimelineQuery("")).toBeNull();
    expect(normalizeTimelineQuery("   ")).toBeNull();
    expect(normalizeTimelineQuery(null)).toBeNull();
    expect(normalizeTimelineQuery(undefined)).toBeNull();
  });

  it("accepts the maximum length and rejects longer queries", () => {
    const longest = "a".repeat(SEARCH_TIMELINE_MAX_QUERY_LENGTH);
    expect(normalizeTimelineQuery(longest)).toBe(longest);
    expect(normalizeTimelineQuery(`${longest}a`)).toBeNull();
  });

  it("counts characters, not UTF-16 code units, like Postgres char_length", () => {
    const emojiQuery = "🚲".repeat(SEARCH_TIMELINE_MAX_QUERY_LENGTH);
    expect(normalizeTimelineQuery(emojiQuery)).toBe(emojiQuery);
  });
});

describe("parseTimelineRpcRows", () => {
  it("maps database rows to timeline months", () => {
    expect(
      parseTimelineRpcRows([
        { month: "2026-01-01", newsletter_count: 4, ward_count: 3 },
        { month: "2026-03-01", newsletter_count: 1, ward_count: 0 },
      ]),
    ).toEqual([month("2026-01", 4, 3), month("2026-03", 1, 0)]);
  });

  it("drops malformed rows", () => {
    expect(
      parseTimelineRpcRows([
        { month: "2026-01-15", newsletter_count: 1, ward_count: 1 },
        { month: "2026-13-01", newsletter_count: 1, ward_count: 1 },
        { month: "2026-02-01", newsletter_count: -1, ward_count: 1 },
        { month: "2026-02-01", newsletter_count: 1.5, ward_count: 1 },
        { month: "2026-02-01", newsletter_count: "2", ward_count: 1 },
        null,
        { month: "2026-04-01", newsletter_count: 2, ward_count: 1 },
      ]),
    ).toEqual([month("2026-04", 2, 1)]);
  });

  it("returns an empty list for non-array data", () => {
    expect(parseTimelineRpcRows(null)).toEqual([]);
    expect(parseTimelineRpcRows({ month: "2026-01-01" })).toEqual([]);
  });
});

describe("parseTimelineResponseBody", () => {
  it("accepts a well-formed body", () => {
    const months = [month("2026-01", 2, 1), month("2026-02", 0, 0)];
    expect(parseTimelineResponseBody({ months })).toEqual(months);
  });

  it("rejects the whole body if any month is malformed", () => {
    expect(
      parseTimelineResponseBody({
        months: [month("2026-01", 2, 1), { month: "January", newsletterCount: 1, wardCount: 1 }],
      }),
    ).toEqual([]);
  });

  it("rejects error bodies and non-objects", () => {
    expect(parseTimelineResponseBody({ error: "timeline_unavailable" })).toEqual([]);
    expect(parseTimelineResponseBody(null)).toEqual([]);
    expect(parseTimelineResponseBody("months")).toEqual([]);
  });
});

describe("getChicagoMonth", () => {
  it("uses the Chicago calendar month, not UTC", () => {
    // 2026-04-01 03:00 UTC is still March 31 in Chicago (UTC-5).
    expect(getChicagoMonth(new Date("2026-04-01T03:00:00Z"))).toBe("2026-03");
    expect(getChicagoMonth(new Date("2026-04-01T06:00:00Z"))).toBe("2026-04");
  });

  it("handles the January rollover", () => {
    expect(getChicagoMonth(new Date("2027-01-01T05:59:00Z"))).toBe("2026-12");
    expect(getChicagoMonth(new Date("2027-01-01T06:00:00Z"))).toBe("2027-01");
  });
});

describe("fillTimelineMonths", () => {
  it("fills gaps with zero months through the given month", () => {
    expect(
      fillTimelineMonths(
        [month("2025-11", 3, 2), month("2026-02", 1, 1)],
        "2026-04",
      ),
    ).toEqual([
      month("2025-11", 3, 2),
      month("2025-12", 0, 0),
      month("2026-01", 0, 0),
      month("2026-02", 1, 1),
      month("2026-03", 0, 0),
      month("2026-04", 0, 0),
    ]);
  });

  it("starts at the first month with a match", () => {
    const filled = fillTimelineMonths([month("2026-03", 1, 1)], "2026-03");
    expect(filled).toEqual([month("2026-03", 1, 1)]);
  });

  it("extends to the last match when it is after the given month", () => {
    expect(
      fillTimelineMonths([month("2026-01", 1, 1), month("2026-03", 2, 2)], "2026-02"),
    ).toEqual([month("2026-01", 1, 1), month("2026-02", 0, 0), month("2026-03", 2, 2)]);
  });

  it("accepts months in any order", () => {
    expect(
      fillTimelineMonths([month("2026-02", 2, 2), month("2026-01", 1, 1)], "2026-02"),
    ).toEqual([month("2026-01", 1, 1), month("2026-02", 2, 2)]);
  });

  it("returns an empty timeline when nothing matched", () => {
    expect(fillTimelineMonths([], "2026-04")).toEqual([]);
  });
});

describe("isMissingFunctionError", () => {
  it("recognizes PostgREST and Postgres missing-function codes", () => {
    expect(isMissingFunctionError({ code: "PGRST202" })).toBe(true);
    expect(isMissingFunctionError({ code: "42883" })).toBe(true);
  });

  it("treats other errors as real failures", () => {
    expect(isMissingFunctionError({ code: "57014" })).toBe(false); // statement timeout
    expect(isMissingFunctionError({ code: "22023" })).toBe(false);
    expect(isMissingFunctionError({})).toBe(false);
  });
});

describe("fetchSearchTimeline", () => {
  const now = new Date("2026-03-15T12:00:00Z");

  it("calls the RPC with the query and fills months through the current month", async () => {
    const rpc = vi.fn().mockResolvedValue({
      data: [{ month: "2026-01-01", newsletter_count: 2, ward_count: 2 }],
      error: null,
    });

    const result = await fetchSearchTimeline({ rpc } as never, "snow", now);

    expect(rpc).toHaveBeenCalledWith(SEARCH_TIMELINE_RPC, { search_query: "snow" });
    expect(result).toEqual({
      status: "ok",
      months: [month("2026-01", 2, 2), month("2026-02", 0, 0), month("2026-03", 0, 0)],
    });
  });

  it("returns an empty ok timeline when nothing matches", async () => {
    const rpc = vi.fn().mockResolvedValue({ data: [], error: null });
    expect(await fetchSearchTimeline({ rpc } as never, "zzz", now)).toEqual({
      status: "ok",
      months: [],
    });
  });

  it("reports unavailable when the function is not deployed", async () => {
    const rpc = vi.fn().mockResolvedValue({
      data: null,
      error: {
        code: "PGRST202",
        message: "Could not find the function public.search_term_timeline(search_query) in the schema cache",
      },
    });
    expect(await fetchSearchTimeline({ rpc } as never, "snow", now)).toEqual({
      status: "unavailable",
    });
  });

  it("reports timedOut when the query hits the statement timeout", async () => {
    const rpc = vi.fn().mockResolvedValue({
      data: null,
      error: { code: "57014", message: "canceling statement due to statement timeout" },
    });
    expect(await fetchSearchTimeline({ rpc } as never, "snow", now)).toEqual({
      status: "timedOut",
    });
  });

  it("throws on other database errors", async () => {
    const rpc = vi.fn().mockResolvedValue({
      data: null,
      error: { code: "22023", message: "search_query must be 1 to 200 characters" },
    });
    await expect(fetchSearchTimeline({ rpc } as never, "snow", now)).rejects.toThrow(
      "search_query must be",
    );
  });
});

describe("buildTimelineApiUrl", () => {
  it("encodes the query parameter", () => {
    expect(buildTimelineApiUrl('"bike lane" & more')).toBe(
      "/api/search-timeline?q=%22bike+lane%22+%26+more",
    );
  });
});

describe("formatTimelineMonth", () => {
  it("formats year-month as a short label", () => {
    expect(formatTimelineMonth("2026-03")).toBe("Mar 2026");
    expect(formatTimelineMonth("2025-12")).toBe("Dec 2025");
  });
});

describe("barHeightPercent", () => {
  it("scales to the tallest month", () => {
    expect(barHeightPercent(10, 10)).toBe(100);
    expect(barHeightPercent(5, 10)).toBe(50);
  });

  it("keeps zero months at zero", () => {
    expect(barHeightPercent(0, 10)).toBe(0);
    expect(barHeightPercent(0, 0)).toBe(0);
  });

  it("keeps small non-zero months visible", () => {
    expect(barHeightPercent(1, 1000)).toBeGreaterThan(0);
  });
});

describe("summarizeTimeline", () => {
  it("totals newsletters, counts active months and finds the earliest peak", () => {
    expect(
      summarizeTimeline([
        month("2026-01", 3, 2),
        month("2026-02", 0, 0),
        month("2026-03", 5, 4),
        month("2026-04", 5, 1),
      ]),
    ).toEqual({
      totalNewsletters: 13,
      monthsWithMatches: 3,
      peak: month("2026-03", 5, 4),
    });
  });

  it("returns null for an empty timeline", () => {
    expect(summarizeTimeline([])).toBeNull();
  });
});
