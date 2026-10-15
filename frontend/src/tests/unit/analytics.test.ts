import { describe, expect, it } from "vitest";
import {
  BROAD_COVERAGE_PEAK_FRACTION,
  buildCoverageGrid,
  buildSearchUrl,
  classifyDateWindow,
  compareWards,
  computeTopicTrends,
  countActiveWardsByMonth,
  countBroadlyCoveredMonths,
  countNewslettersByWardMonth,
  daysBetween,
  describeDataAsOf,
  EMPTY_FILTERS,
  expandTermPostings,
  filterFacts,
  findBroadCoverageWindow,
  findLongestGaps,
  formatMonth,
  isTopicLabeledInMonth,
  listMonths,
  listMonthsWithShares,
  listSourceWards,
  listTopics,
  listWards,
  listWindowMonths,
  lookupTermPostings,
  MIN_MONTH_LABEL_WIDTH,
  monthDateRange,
  monthTickLabeler,
  normalizeTermQuery,
  searchScopeForFilters,
  shareOrNull,
  STREET_SAFETY_LABELING_START_MONTH,
  summarizeWardCounts,
  summarizeWardCoverage,
  wardsInScope,
  trimSparseEdges,
  suggestTerms,
  summarizeFacts,
  termMentionsByMonth,
  termMentionsByWard,
  type AnalyticsFilters,
  type AnalyticsMetadata,
  type NewsletterFact,
  type SourceCoverage,
  type TermIndex,
} from "../../lib/analytics";

let nextId = 0;
function fact(overrides: Partial<NewsletterFact> = {}): NewsletterFact {
  nextId += 1;
  return {
    id: `n${nextId}`,
    date: "2026-01-15",
    source_id: 1,
    ward: "1",
    alder: "Ada Alder",
    topics: [],
    words: 100,
    ...overrides,
  };
}

function filters(overrides: Partial<AnalyticsFilters> = {}): AnalyticsFilters {
  return { ...EMPTY_FILTERS, ...overrides };
}

function source(overrides: Partial<SourceCoverage> = {}): SourceCoverage {
  return {
    id: 1,
    name: "A",
    ward: "1",
    source_type: "alderman",
    first_date: "2024-01-01",
    last_date: "2026-01-01",
    newsletters: 10,
    ...overrides,
  };
}

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

  it("lists distinct wards and topics", () => {
    const facts = [
      fact({ ward: "10", topics: ["bike_lanes"] }),
      fact({ ward: "2", topics: ["city_budget", "bike_lanes"] }),
      fact({ ward: null, topics: null }),
    ];
    expect(listWards(facts)).toEqual(["2", "10"]);
    expect(listTopics(facts)).toEqual(["bike_lanes", "city_budget"]);
  });
});

describe("filterFacts", () => {
  const facts = [
    fact({ ward: "1", date: "2026-01-10", topics: ["bike_lanes"] }),
    fact({ ward: "2", date: "2026-02-10", topics: ["city_budget"] }),
    fact({ ward: "2", date: "2026-03-10", topics: null }),
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

  it("filters by topic unless told to ignore it", () => {
    const topicFilters = filters({ topic: "bike_lanes" });
    expect(filterFacts(facts, topicFilters)).toHaveLength(1);
    expect(filterFacts(facts, topicFilters, { ignoreTopic: true })).toHaveLength(4);
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

describe("listMonthsWithShares", () => {
  it("spans every series' shares so small multiples share one axis", () => {
    const points = [
      { month: "2026-01", share: 0.2 },
      { month: "2026-01", share: null },
      { month: "2026-02", share: null },
      { month: "2026-03", share: null },
      { month: "2026-03", share: 0.1 },
      { month: "2026-04", share: null },
    ];
    expect(listMonthsWithShares(points)).toEqual(["2026-01", "2026-02", "2026-03"]);
    expect(listMonthsWithShares([{ month: "2026-01", share: null }])).toEqual([]);
  });

  it("keeps a late-added topic on the same axis as the others, blank before it was labeled", () => {
    const topic = "street_safety_or_traffic_calming";
    const points = computeTopicTrends(
      [
        fact({ date: "2026-01-02", topics: ["bike_lanes"] }),
        fact({ date: "2026-02-02", topics: [topic] }),
      ],
      [topic, "bike_lanes"],
      1,
    );
    expect(listMonthsWithShares(points)).toEqual(["2026-01", "2026-02"]);
    expect(points.find((point) => point.topic === topic && point.month === "2026-01")?.share).toBeNull();
  });
});

describe("summarizeFacts", () => {
  it("summarizes the newsletter count and date span", () => {
    const summary = summarizeFacts([
      fact({ date: "2026-02-01" }),
      fact({ date: "2026-01-01" }),
      fact({ date: "2026-03-01" }),
    ]);
    expect(summary).toEqual({ newsletters: 3, firstDate: "2026-01-01", lastDate: "2026-03-01" });
  });

  it("handles no newsletters", () => {
    expect(summarizeFacts([])).toEqual({ newsletters: 0, firstDate: null, lastDate: null });
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
      minActiveWardsBefore: 0,
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

  it("counts broadly covered months within a window", () => {
    const activity = countActiveWardsByMonth(coverageFacts);
    expect(countBroadlyCoveredMonths(["2025-11", "2025-12", "2026-01", "2026-02", "2026-03"], activity, 9)).toBe(2);
    expect(countBroadlyCoveredMonths(["2026-04"], activity, 9)).toBe(0);
  });

  it("classifies the date filters as the broad window, the full archive, or custom", () => {
    const window = findBroadCoverageWindow(coverageFacts, 0.9);
    expect(classifyDateWindow(filters({ fromMonth: "2026-02" }), window)).toBe("broad");
    expect(classifyDateWindow(EMPTY_FILTERS, window)).toBe("full");
    expect(classifyDateWindow(filters({ fromMonth: "2026-02", toMonth: "2026-02" }), window)).toBe("custom");
    expect(classifyDateWindow(filters({ fromMonth: "2026-01" }), null)).toBe("custom");
  });
});

describe("term explorer", () => {
  const index: TermIndex = {
    min_newsletters: 2,
    months: ["2026-01", "2026-02"],
    buckets: [
      [1, 0],
      [2, 0],
      [2, 1],
    ],
    terms: { "bike lanes": [0, 2, 2, 1], bike: [0, 3], "bike share": [1, 1] },
  };
  const wardBySource = new Map<number, string | null>([
    [1, "1"],
    [2, "2"],
  ]);
  const scopeFacts = [
    fact({ ward: "1", date: "2026-01-05" }),
    fact({ ward: "1", date: "2026-01-06" }),
    fact({ ward: "1", date: "2026-01-07" }),
    fact({ ward: "1", date: "2026-01-08" }),
    fact({ ward: "2", date: "2026-02-05", source_id: 2 }),
    fact({ ward: "2", date: "2026-02-06", source_id: 2 }),
  ];

  it("normalizes queries like the backend tokenizer", () => {
    expect(normalizeTermQuery("  Bike   LANES ")).toBe("bike lanes");
    expect(normalizeTermQuery("Ward’s")).toBe("ward's");
  });

  it("looks up postings and reports misses as null", () => {
    expect(lookupTermPostings(index, "Bike Lanes")).toEqual([0, 2, 2, 1]);
    expect(lookupTermPostings(index, "streetcar")).toBeNull();
  });

  it("ignores inherited object keys instead of returning prototype members", () => {
    for (const query of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
      expect(lookupTermPostings(index, query)).toBeNull();
    }
  });

  it("suggests longer indexed terms by prefix, shortest first", () => {
    expect(suggestTerms(index, "bike", 5)).toEqual(["bike lanes", "bike share"]);
    expect(suggestTerms(index, "", 5)).toEqual([]);
  });

  it("expands postings and applies ward and date filters", () => {
    const postings = index.terms["bike lanes"];
    expect(expandTermPostings(index, postings, wardBySource, EMPTY_FILTERS)).toEqual([
      { sourceId: 1, ward: "1", month: "2026-01", newsletters: 2 },
      { sourceId: 2, ward: "2", month: "2026-02", newsletters: 1 },
    ]);
    expect(expandTermPostings(index, postings, wardBySource, filters({ wards: ["2"] }))).toHaveLength(1);
    expect(
      expandTermPostings(index, postings, wardBySource, filters({ fromMonth: "2026-02" })),
    ).toEqual([{ sourceId: 2, ward: "2", month: "2026-02", newsletters: 1 }]);
  });

  it("computes monthly mention shares against all newsletters that month", () => {
    const buckets = expandTermPostings(index, index.terms["bike lanes"], wardBySource, EMPTY_FILTERS);
    expect(termMentionsByMonth(buckets, scopeFacts, 1)).toEqual([
      { month: "2026-01", mentions: 2, newsletters: 4, share: 0.5 },
      { month: "2026-02", mentions: 1, newsletters: 2, share: 0.5 },
    ]);
  });

  it("leaves shares of sparse months empty", () => {
    const buckets = expandTermPostings(index, index.terms["bike lanes"], wardBySource, EMPTY_FILTERS);
    expect(termMentionsByMonth(buckets, scopeFacts, 3).map((point) => point.share)).toEqual([0.5, null]);
  });

  it("zero-fills months without newsletters", () => {
    const points = termMentionsByMonth([], [fact({ date: "2026-01-01" }), fact({ date: "2026-03-01" })]);
    expect(points.map((point) => [point.month, point.newsletters])).toEqual([
      ["2026-01", 1],
      ["2026-02", 0],
      ["2026-03", 1],
    ]);
  });

  it("ranks wards by mentions with each ward's share", () => {
    const buckets = expandTermPostings(index, index.terms["bike lanes"], wardBySource, EMPTY_FILTERS);
    expect(termMentionsByWard(buckets, scopeFacts)).toEqual([
      { ward: "1", mentions: 2, newsletters: 4, share: 0.5 },
      { ward: "2", mentions: 1, newsletters: 2, share: 0.5 },
    ]);
  });
});

describe("computeTopicTrends", () => {
  it("computes zero-filled monthly topic shares over processed newsletters", () => {
    const points = computeTopicTrends(
      [
        fact({ date: "2026-01-02", topics: ["bike_lanes"] }),
        fact({ date: "2026-01-03", topics: [] }),
        fact({ date: "2026-01-04", topics: null }),
        fact({ date: "2026-03-02", topics: ["bike_lanes"] }),
      ],
      ["bike_lanes"],
      2,
    );
    expect(points).toEqual([
      { month: "2026-01", topic: "bike_lanes", newsletters: 1, monthNewsletters: 2, share: 0.5 },
      { month: "2026-02", topic: "bike_lanes", newsletters: 0, monthNewsletters: 0, share: null },
      { month: "2026-03", topic: "bike_lanes", newsletters: 1, monthNewsletters: 1, share: null },
    ]);
  });

  it("leaves months before a late-added topic entered the taxonomy blank instead of 0%", () => {
    const topic = "street_safety_or_traffic_calming";
    const points = computeTopicTrends(
      [
        fact({ date: "2026-01-02", topics: [] }),
        fact({ date: "2026-02-02", topics: [topic] }),
        fact({ date: "2026-02-03", topics: [] }),
      ],
      [topic, "bike_lanes"],
      1,
    );
    expect(points.filter((point) => point.topic === topic).map((point) => [point.month, point.share])).toEqual([
      ["2026-01", null],
      ["2026-02", 0.5],
    ]);
    expect(points.find((point) => point.topic === "bike_lanes" && point.month === "2026-01")?.share).toBe(0);
  });

  it("knows when each topic could have been labeled", () => {
    expect(STREET_SAFETY_LABELING_START_MONTH).toBe("2026-02");
    expect(isTopicLabeledInMonth("street_safety_or_traffic_calming", "2026-01")).toBe(false);
    expect(isTopicLabeledInMonth("street_safety_or_traffic_calming", "2026-02")).toBe(true);
    expect(isTopicLabeledInMonth("bike_lanes", "2023-11")).toBe(true);
    expect(isTopicLabeledInMonth("constructor", "2023-11")).toBe(true);
  });
});

describe("cadence", () => {
  it("counts newsletters per ward per month", () => {
    const counts = countNewslettersByWardMonth([
      fact({ ward: "10", date: "2026-01-01" }),
      fact({ ward: "2", date: "2026-01-05" }),
      fact({ ward: "2", date: "2026-01-20" }),
      fact({ ward: null }),
    ]);
    expect(counts).toEqual([
      { ward: "2", month: "2026-01", newsletters: 2 },
      { ward: "10", month: "2026-01", newsletters: 1 },
    ]);
  });

  it("finds the longest gaps between consecutive newsletters per source", () => {
    const gaps = findLongestGaps(
      [
        fact({ source_id: 1, date: "2026-01-01" }),
        fact({ source_id: 1, date: "2026-03-01" }),
        fact({ source_id: 1, date: "2026-03-05" }),
        fact({ source_id: 2, date: "2026-01-01", ward: "2", alder: "Bo" }),
        fact({ source_id: 2, date: "2026-01-11", ward: "2", alder: "Bo" }),
      ],
      2,
    );
    expect(gaps).toEqual([
      { sourceId: 1, alder: "Ada Alder", ward: "1", from: "2026-01-01", to: "2026-03-01", days: 59 },
      { sourceId: 2, alder: "Bo", ward: "2", from: "2026-01-01", to: "2026-01-11", days: 10 },
    ]);
  });
});

describe("coverage", () => {
  it("marks months before a ward's first newsletter untracked and later empty months silent", () => {
    const archive = [
      fact({ ward: "1", date: "2026-02-10" }),
      fact({ ward: "1", date: "2026-02-20" }),
      fact({ ward: "1", date: "2026-04-01" }),
    ];
    const cells = buildCoverageGrid(archive, ["1", "4"], ["2026-01", "2026-02", "2026-03", "2026-04"]);
    expect(cells.map((cell) => [cell.ward, cell.month, cell.status, cell.newsletters])).toEqual([
      ["1", "2026-01", "untracked", 0],
      ["1", "2026-02", "received", 2],
      ["1", "2026-03", "silent", 0],
      ["1", "2026-04", "received", 1],
      ["4", "2026-01", "untracked", 0],
      ["4", "2026-02", "untracked", 0],
      ["4", "2026-03", "untracked", 0],
      ["4", "2026-04", "untracked", 0],
    ]);
  });

  it("keeps a ward tracked in a window that starts after its first newsletter", () => {
    const archive = [fact({ ward: "1", date: "2025-06-01" })];
    expect(buildCoverageGrid(archive, ["1"], ["2026-01"])[0].status).toBe("silent");
  });

  it("summarizes archive coverage per ward, merging sources and keeping wards with none", () => {
    const sources = [
      source({ id: 1, name: "Former", ward: "1", first_date: "2025-01-01", last_date: "2025-06-01", newsletters: 4 }),
      source({ id: 2, name: "Current", ward: "1", first_date: "2025-07-01", last_date: "2026-01-01", newsletters: 6 }),
      source({ id: 3, name: "Quiet", ward: "4", first_date: null, last_date: null, newsletters: 0 }),
    ];
    expect(summarizeWardCoverage(sources, ["1", "4", "7"])).toEqual([
      { ward: "1", aldermen: ["Former", "Current"], firstDate: "2025-01-01", lastDate: "2026-01-01", newsletters: 10 },
      { ward: "4", aldermen: ["Quiet"], firstDate: null, lastDate: null, newsletters: 0 },
      { ward: "7", aldermen: [], firstDate: null, lastDate: null, newsletters: 0 },
    ]);
  });
});

describe("buildSearchUrl", () => {
  it("builds search links and quotes phrases", () => {
    expect(buildSearchUrl({ ward: "3", topic: "bike_lanes" })).toBe("/search?ward=3&topic=bike_lanes");
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
    topic: "bike_lanes",
    fromMonth: "2025-11",
    toMonth: "2026-02",
  };

  it("carries the date range and topic into search links", () => {
    const scope = searchScopeForFilters(filters, { includeTopic: true });
    expect(scope).toEqual({ fromDate: "2025-11-01", toDate: "2026-02-28", topic: "bike_lanes" });
    expect(buildSearchUrl({ ...scope, ward: "3" })).toBe(
      "/search?ward=3&topic=bike_lanes&from=2025-11-01&to=2026-02-28",
    );
  });

  it("omits filters the panel ignores and unset filters", () => {
    expect(searchScopeForFilters(filters, { includeTopic: false })).toEqual({
      fromDate: "2025-11-01",
      toDate: "2026-02-28",
    });
    expect(searchScopeForFilters(EMPTY_FILTERS, { includeTopic: true })).toEqual({});
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
