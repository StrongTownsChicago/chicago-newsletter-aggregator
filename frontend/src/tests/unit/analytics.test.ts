import { describe, expect, it } from "vitest";
import {
  BROAD_COVERAGE_PEAK_FRACTION,
  classifyDateWindow,
  compareWards,
  countActiveWardsByMonth,
  daysBetween,
  describeDataAsOf,
  EMPTY_FILTERS,
  filterFacts,
  findBroadCoverageWindow,
  formatDay,
  formatMonth,
  listMonths,
  listSourceWards,
  listWards,
  listWindowMonths,
  MIN_MONTH_LABEL_WIDTH,
  monthTickLabeler,
  shareOrNull,
  summarizeWardCounts,
  wardsInScope,
  trimSparseEdges,
  type AnalyticsMetadata,
} from "../../lib/analytics";
import { fact, filters, source } from "../analytics-fixtures";

describe("dates and wards", () => {
  it("lists months inclusively across a year boundary", () => {
    expect(listMonths("2025-11", "2026-02")).toEqual(["2025-11", "2025-12", "2026-01", "2026-02"]);
    expect(listMonths("2026-03", "2026-02")).toEqual([]);
  });

  it("counts days between ISO dates", () => {
    expect(daysBetween("2026-01-01", "2026-03-01")).toBe(59);
  });

  it("sorts wards numerically then labels", () => {
    expect(["10", "Citywide", "2"].sort(compareWards)).toEqual(["2", "10", "Citywide"]);
  });

  it("lists distinct wards", () => {
    const facts = [fact({ ward: "10" }), fact({ ward: "2" }), fact({ ward: "10" }), fact({ ward: null })];
    expect(listWards(facts)).toEqual(["2", "10"]);
  });
});

describe("filterFacts", () => {
  const facts = [
    fact({ ward: "1", date: "2026-01-10", lenses: ["transportation"] }),
    fact({ ward: "2", date: "2026-02-10", lenses: ["budget_taxes"] }),
    fact({ ward: "2", date: "2026-03-10", lenses: [] }),
    fact({ ward: null, date: "2026-03-10" }),
  ];

  it("returns everything with empty filters", () => {
    expect(filterFacts(facts, EMPTY_FILTERS)).toHaveLength(4);
  });

  it("filters by wards, excluding sources without a ward", () => {
    expect(filterFacts(facts, filters({ wards: ["2"] }))).toHaveLength(2);
  });

  it("filters by inclusive month range", () => {
    const result = filterFacts(facts, filters({ fromMonth: "2026-02", toMonth: "2026-02" }));
    expect(result.map((item) => item.date)).toEqual(["2026-02-10"]);
  });

  it("filters by lens unless told to ignore it", () => {
    const lensFilters = filters({ lens: "transportation" });
    expect(filterFacts(facts, lensFilters)).toHaveLength(1);
    expect(filterFacts(facts, lensFilters, { ignoreLens: true })).toHaveLength(4);
  });
});

describe("shareOrNull", () => {
  it("returns null below the minimum denominator", () => {
    expect(shareOrNull(1, 4, 5)).toBeNull();
    expect(shareOrNull(1, 4, 4)).toBe(0.25);
    expect(shareOrNull(0, 0, 0)).toBeNull();
  });
});

describe("trimSparseEdges", () => {
  it("drops leading and trailing points without a share but keeps interior gaps", () => {
    const points = [null, 0.1, null, 0.2, null].map((share, index) => ({ index, share }));
    expect(trimSparseEdges(points).map((point) => point.index)).toEqual([1, 2, 3]);
    expect(trimSparseEdges([{ share: null }])).toEqual([]);
  });
});

describe("ward scope and counts", () => {
  it("lists every ward with a source, including wards without newsletters", () => {
    const sources = [
      source({ id: 1, ward: "10" }),
      source({ id: 2, ward: "2", newsletters: 0, first_date: null, last_date: null }),
      source({ id: 3, ward: null, name: "Agency" }),
      source({ id: 4, ward: "2" }),
    ];
    expect(listSourceWards(sources)).toEqual(["2", "10"]);
  });

  it("scopes to the selected wards, or every ward when none are selected", () => {
    expect(wardsInScope(["1", "2", "3"], EMPTY_FILTERS)).toEqual(["1", "2", "3"]);
    expect(wardsInScope(["1", "2", "3"], filters({ wards: ["3", "1"] }))).toEqual(["1", "3"]);
  });

  it("counts wards sending in the window against the wards in scope", () => {
    const archive = [
      fact({ ward: "1", date: "2025-06-01" }),
      fact({ ward: "2", date: "2026-03-01" }),
    ];
    const windowFacts = archive.filter((item) => item.date >= "2026-01-01");
    expect(summarizeWardCounts(["1", "2", "3"], windowFacts, archive)).toEqual({
      scopeWards: 3,
      wardsWithNewsletters: 1,
      wardsNeverArchived: ["3"],
    });
  });
});

describe("date windows", () => {
  it("formats months for display", () => {
    expect(formatMonth("2026-02")).toBe("Feb 2026");
    expect(formatMonth("2025-12")).toBe("Dec 2025");
  });

  it("formats days for display, whatever the reader's time zone", () => {
    expect(formatDay("2026-01-03")).toBe("Jan 3, 2026");
    expect(formatDay("2025-12-31")).toBe("Dec 31, 2025");
  });

  it("lists the months a window spans, defaulting open ends to the data", () => {
    const dataMonths = ["2025-11", "2025-12", "2026-01", "2026-02"];
    expect(listWindowMonths(EMPTY_FILTERS, dataMonths)).toEqual(dataMonths);
    expect(listWindowMonths(filters({ fromMonth: "2026-01" }), dataMonths)).toEqual(["2026-01", "2026-02"]);
    expect(listWindowMonths(filters({ toMonth: "2025-11" }), dataMonths)).toEqual(["2025-11"]);
    expect(listWindowMonths(EMPTY_FILTERS, [])).toEqual([]);
  });

  // Ward 1 sends from 2025-11; wards 2-10 join in 2026-02 (one skips 2026-03).
  const coverageFacts = [
    fact({ ward: "1", date: "2025-11-03" }),
    fact({ ward: "1", date: "2026-01-03" }),
    ...Array.from({ length: 10 }, (_, index) => fact({ ward: String(index + 1), date: "2026-02-03" })),
    ...Array.from({ length: 9 }, (_, index) => fact({ ward: String(index + 1), date: "2026-03-03" })),
    fact({ ward: null, date: "2025-12-01" }),
  ];

  it("counts active wards for every month in the span, zero-filling gaps", () => {
    expect(countActiveWardsByMonth(coverageFacts)).toEqual([
      { month: "2025-11", activeWards: 1 },
      { month: "2025-12", activeWards: 0 },
      { month: "2026-01", activeWards: 1 },
      { month: "2026-02", activeWards: 10 },
      { month: "2026-03", activeWards: 9 },
    ]);
    expect(countActiveWardsByMonth([])).toEqual([]);
  });

  it("starts the broad-coverage window at the first month near the peak", () => {
    expect(BROAD_COVERAGE_PEAK_FRACTION).toBeGreaterThan(0);
    expect(findBroadCoverageWindow(coverageFacts, 0.9)).toEqual({
      startMonth: "2026-02",
      endMonth: "2026-03",
      minActiveWards: 9,
      peakActiveWards: 10,
      maxActiveWardsBefore: 1,
      months: 2,
    });
    expect(findBroadCoverageWindow([])).toBeNull();
  });

  it("offers no narrower window when coverage was broad from the first month", () => {
    expect(findBroadCoverageWindow([fact({ date: "2026-01-02" }), fact({ date: "2026-02-02" })])).toBeNull();
    expect(findBroadCoverageWindow([fact({ date: "2026-01-02" })])).toBeNull();
  });

  it("keeps a peak in the latest, partial month as the window start", () => {
    const window = findBroadCoverageWindow([
      fact({ ward: "1", date: "2026-01-02" }),
      fact({ ward: "1", date: "2026-02-02" }),
      fact({ ward: "2", date: "2026-02-03" }),
    ]);
    expect(window).toMatchObject({ startMonth: "2026-02", endMonth: "2026-02", months: 1, maxActiveWardsBefore: 1 });
  });

  it("labels month names when there is room, with the year at the first month and January", () => {
    const months = ["2025-11", "2025-12", "2026-01", "2026-02"];
    const label = monthTickLabeler(months, months.length * MIN_MONTH_LABEL_WIDTH);
    expect(months.map(label)).toEqual(["Nov\n2025", "Dec", "Jan\n2026", "Feb"]);
  });

  it("labels a Feb–Oct series with its year", () => {
    const months = listMonths("2026-02", "2026-10");
    const label = monthTickLabeler(months, 600);
    expect(label("2026-02")).toBe("Feb\n2026");
    expect(label("2026-03")).toBe("Mar");
  });

  it("falls back to year labels on narrow axes, labeling the first month only when it has room", () => {
    const months = listMonths("2023-03", "2026-10");
    const narrow = monthTickLabeler(months, months.length * (MIN_MONTH_LABEL_WIDTH - 1));
    expect(narrow("2023-03")).toBe("2023");
    expect(narrow("2024-01")).toBe("2024");
    expect(narrow("2024-02")).toBe("");
    const lateStart = listMonths("2023-11", "2026-10");
    const crowded = monthTickLabeler(lateStart, lateStart.length * 10);
    expect(crowded("2023-11")).toBe("");
    expect(crowded("2024-01")).toBe("2024");
  });

  it("classifies the date filters as the broad window, the full archive, or custom", () => {
    const window = findBroadCoverageWindow(coverageFacts, 0.9);
    expect(classifyDateWindow(filters({ fromMonth: "2026-02" }), window)).toBe("broad");
    expect(classifyDateWindow(EMPTY_FILTERS, window)).toBe("full");
    expect(classifyDateWindow(filters({ fromMonth: "2026-02", toMonth: "2026-02" }), window)).toBe("custom");
    expect(classifyDateWindow(filters({ fromMonth: "2026-01" }), null)).toBe("custom");
  });
});

describe("describeDataAsOf", () => {
  const metadata: AnalyticsMetadata = {
    generated_at: "2026-10-14T20:05:00+00:00",
    newsletter_count: 1234,
    source_count: 60,
    first_date: "2024-01-02",
    last_date: "2026-10-13",
    term_count: 5000,
    min_term_newsletters: 20,
  };

  it("shows the generation time in Chicago with the newsletter count and range", () => {
    expect(describeDataAsOf(metadata)).toBe(
      "Data as of Oct 14, 2026, 3:05 PM from 1,234 newsletters (2024-01-02 to 2026-10-13).",
    );
  });

  it("omits the date range for an empty archive", () => {
    expect(describeDataAsOf({ ...metadata, newsletter_count: 0, first_date: null, last_date: null })).toBe(
      "Data as of Oct 14, 2026, 3:05 PM from 0 newsletters.",
    );
  });

  it("does not crash on an unparseable timestamp", () => {
    expect(describeDataAsOf({ ...metadata, generated_at: "not a date" })).toMatch(/^Data as of an unknown date /);
  });
});
