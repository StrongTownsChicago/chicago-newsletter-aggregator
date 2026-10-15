import { describe, expect, it } from "vitest";
import {
  buildCanonicalViewUrl,
  chooseHistoryMode,
  DASHBOARD_URL_PARAMS,
  HISTORY_COALESCE_MS,
  reconcileDateWindow,
  FULL_ARCHIVE_WINDOW,
  MAX_TERM_QUERY_LENGTH,
  parseDashboardUrlState,
  serializeDashboardUrlState,
  type DashboardUrlContext,
  type DashboardViewState,
} from "../../lib/analytics-url-state";

const context: DashboardUrlContext = {
  filterWards: ["1", "2", "10", "36"],
  profileWards: ["1", "2", "4", "10", "36"],
  months: ["2025-11", "2025-12", "2026-01", "2026-02", "2026-03"],
  lensIds: ["public_safety", "budget_taxes"],
  defaultFromMonth: "2026-01",
};

function parse(query: string): DashboardViewState {
  return parseDashboardUrlState(new URLSearchParams(query), context);
}

const defaultView: DashboardViewState = {
  filters: { wards: [], lens: null, fromMonth: "2026-01", toMonth: null },
  profileWard: null,
  term: "",
};

describe("parseDashboardUrlState", () => {
  it("gives the default view for an empty query", () => {
    expect(parse("")).toEqual(defaultView);
  });

  it("reads every parameter", () => {
    expect(parse("wards=2,1&topic=budget_taxes&from=2025-12&to=2026-02&ward=4&term=Bike%20Lanes")).toEqual({
      filters: { wards: ["1", "2"], lens: "budget_taxes", fromMonth: "2025-12", toMonth: "2026-02" },
      profileWard: "4",
      term: "bike lanes",
    });
  });

  it("starts at the beginning of the archive for window=all", () => {
    expect(parse(`${DASHBOARD_URL_PARAMS.window}=${FULL_ARCHIVE_WINDOW}&from=2026-02`).filters.fromMonth).toBeNull();
  });

  it("ignores invalid values instead of throwing", () => {
    expect(
      parse("wards=1,99,abc,,1&topic=lens&from=2024-13&to=nope&ward=50&window=weird"),
    ).toEqual({
      ...defaultView,
      filters: { ...defaultView.filters, wards: ["1"] },
    });
  });

  it("tolerates malformed percent-encoding", () => {
    expect(() => parse("term=%E0%A4%A&wards=%ZZ")).not.toThrow();
  });

  it("drops an end month before the start month", () => {
    expect(parse("from=2026-02&to=2026-01").filters).toMatchObject({ fromMonth: "2026-02", toMonth: null });
  });

  it("ignores over-long terms", () => {
    expect(parse(`term=${"a".repeat(MAX_TERM_QUERY_LENGTH + 1)}`).term).toBe("");
  });

  it("ignores inherited object keys", () => {
    expect(parse("topic=constructor&ward=__proto__").filters.lens).toBeNull();
  });
});

describe("serializeDashboardUrlState", () => {
  it("leaves the default view bare", () => {
    expect(serializeDashboardUrlState(defaultView, context)).toBe("");
  });

  it("writes only what differs from the default, in a fixed order", () => {
    const query = serializeDashboardUrlState(
      {
        filters: { wards: ["10", "2"], lens: "public_safety", fromMonth: "2025-12", toMonth: "2026-02" },
        profileWard: "36",
        term: "  Zoning ",
      },
      context,
    );
    expect(query).toBe("wards=2,10&topic=public_safety&from=2025-12&to=2026-02&ward=36&term=zoning");
  });

  it("marks the full archive explicitly when the default is a narrower window", () => {
    const view = { ...defaultView, filters: { ...defaultView.filters, fromMonth: null } };
    expect(serializeDashboardUrlState(view, context)).toBe(`window=${FULL_ARCHIVE_WINDOW}`);
    expect(serializeDashboardUrlState(view, { ...context, defaultFromMonth: null })).toBe("");
  });

  it("round-trips through parsing", () => {
    const views: DashboardViewState[] = [
      defaultView,
      { ...defaultView, filters: { wards: ["1", "36"], lens: "budget_taxes", fromMonth: null, toMonth: "2026-01" } },
      { filters: { wards: [], lens: null, fromMonth: "2026-03", toMonth: "2026-03" }, profileWard: "10", term: "speed hump" },
    ];
    for (const view of views) {
      const query = serializeDashboardUrlState(view, context);
      expect(parse(query)).toEqual(view);
      expect(serializeDashboardUrlState(parse(query), context)).toBe(query);
    }
  });
});

describe("chooseHistoryMode", () => {
  it("pushes the first change and changes after a pause", () => {
    expect(chooseHistoryMode(5000, null)).toBe("push");
    expect(chooseHistoryMode(5000 + HISTORY_COALESCE_MS, 5000)).toBe("push");
  });

  it("folds a quick burst of changes into one history entry", () => {
    expect(chooseHistoryMode(5000 + HISTORY_COALESCE_MS - 1, 5000)).toBe("replace");
  });
});

describe("reconcileDateWindow", () => {
  const filters = { wards: [], lens: null, fromMonth: "2026-03", toMonth: "2026-01" };

  it("clears the end when the start moves past it", () => {
    expect(reconcileDateWindow(filters, "from")).toEqual({ ...filters, toMonth: null });
  });

  it("moves the start back when the end moves before it", () => {
    expect(reconcileDateWindow(filters, "to")).toEqual({ ...filters, fromMonth: "2026-01" });
  });

  it("leaves a valid or open window alone", () => {
    const valid = { ...filters, fromMonth: "2026-01", toMonth: "2026-03" };
    expect(reconcileDateWindow(valid, "from")).toBe(valid);
    const open = { ...filters, fromMonth: null };
    expect(reconcileDateWindow(open, "to")).toBe(open);
  });

  it("gives a window the URL parser keeps", () => {
    const view = { filters: reconcileDateWindow(filters, "to"), profileWard: null, term: "" };
    expect(parse(serializeDashboardUrlState(view, context))).toEqual(view);
  });
});

describe("buildCanonicalViewUrl", () => {
  it("keeps the view's query on the canonical site, not the current origin", () => {
    expect(buildCanonicalViewUrl("https://example.org/analytics", "wards=1,2&topic=budget_taxes")).toBe(
      "https://example.org/analytics?wards=1,2&topic=budget_taxes",
    );
    expect(buildCanonicalViewUrl("https://example.org/analytics", "")).toBe("https://example.org/analytics");
  });
});
