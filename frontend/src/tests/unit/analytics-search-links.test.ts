import { describe, expect, it } from "vitest";
import { EMPTY_FILTERS, type AnalyticsFilters } from "../../lib/analytics/core";
import { buildSearchUrl, monthDateRange, searchScopeForFilters } from "../../lib/analytics/search-links";

describe("buildSearchUrl", () => {
  it("builds search links and quotes phrases", () => {
    expect(buildSearchUrl({ ward: "3" })).toBe("/search?ward=3");
    expect(buildSearchUrl({ q: "bike lanes" })).toBe("/search?q=%22bike+lanes%22");
    expect(buildSearchUrl({ q: "zoning", ward: "1" })).toBe("/search?q=zoning&ward=1");
    expect(buildSearchUrl({})).toBe("/search");
  });
});

describe("monthDateRange", () => {
  it("returns the first and last day of the month, including leap years", () => {
    expect(monthDateRange("2026-01")).toEqual({ fromDate: "2026-01-01", toDate: "2026-01-31" });
    expect(monthDateRange("2024-02")).toEqual({ fromDate: "2024-02-01", toDate: "2024-02-29" });
    expect(monthDateRange("2026-02")).toEqual({ fromDate: "2026-02-01", toDate: "2026-02-28" });
    expect(monthDateRange("2026-12")).toEqual({ fromDate: "2026-12-01", toDate: "2026-12-31" });
  });
});

describe("searchScopeForFilters", () => {
  const filters: AnalyticsFilters = {
    wards: ["3"],
    lens: "transportation",
    fromMonth: "2025-11",
    toMonth: "2026-02",
  };

  it("carries the date range into search links, never the lens (search cannot filter by it)", () => {
    const scope = searchScopeForFilters(filters);
    expect(scope).toEqual({ fromDate: "2025-11-01", toDate: "2026-02-28" });
    expect(buildSearchUrl({ ...scope, ward: "3" })).toBe("/search?ward=3&from=2025-11-01&to=2026-02-28");
  });

  it("omits unset filters", () => {
    expect(searchScopeForFilters(EMPTY_FILTERS)).toEqual({});
  });
});
