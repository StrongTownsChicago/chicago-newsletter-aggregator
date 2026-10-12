import { describe, expect, it } from "vitest";
import {
  buildSearchUrl,
  compareWards,
  computeRelevanceByWard,
  computeTopicTrends,
  computeWardTopicCells,
  countNewslettersByWardMonth,
  daysBetween,
  EMPTY_FILTERS,
  expandTermPostings,
  filterFacts,
  findLongestGaps,
  listMonths,
  listTopics,
  listWards,
  lookupTermPostings,
  monthDateRange,
  normalizeTermQuery,
  searchScopeForFilters,
  selectCoverage,
  shareOrNull,
  trimSparseEdges,
  suggestTerms,
  summarizeFacts,
  termMentionsByMonth,
  termMentionsByWard,
  type AnalyticsFilters,
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
    relevance: 5,
    words: 100,
    ...overrides,
  };
}

function filters(overrides: Partial<AnalyticsFilters> = {}): AnalyticsFilters {
  return { ...EMPTY_FILTERS, ...overrides };
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
    fact({ ward: "1", date: "2026-01-10", topics: ["bike_lanes"], relevance: 8 }),
    fact({ ward: "2", date: "2026-02-10", topics: ["city_budget"], relevance: 3 }),
    fact({ ward: "2", date: "2026-03-10", topics: null, relevance: null }),
    fact({ ward: null, date: "2026-03-10", relevance: 1 }),
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

  it("filters by minimum relevance and drops unscored newsletters", () => {
    expect(filterFacts(facts, filters({ minRelevance: 5 }))).toHaveLength(1);
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

describe("summarizeFacts", () => {
  it("summarizes counts, span, and average relevance of scored newsletters", () => {
    const summary = summarizeFacts([
      fact({ date: "2026-02-01", source_id: 1, relevance: 4 }),
      fact({ date: "2026-01-01", source_id: 2, relevance: 8 }),
      fact({ date: "2026-03-01", source_id: 2, relevance: null }),
    ]);
    expect(summary).toEqual({
      newsletters: 3,
      activeSources: 2,
      firstDate: "2026-01-01",
      lastDate: "2026-03-01",
      averageRelevance: 6,
      scoredNewsletters: 2,
    });
  });

  it("handles no newsletters", () => {
    const summary = summarizeFacts([]);
    expect(summary.averageRelevance).toBeNull();
    expect(summary.firstDate).toBeNull();
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

describe("computeWardTopicCells", () => {
  const facts = [
    ...Array.from({ length: 5 }, () => fact({ ward: "1", topics: ["bike_lanes"] })),
    ...Array.from({ length: 5 }, () => fact({ ward: "2", topics: [] })),
    fact({ ward: "3", topics: ["bike_lanes"] }),
    fact({ ward: "2", topics: null }),
  ];

  it("compares ward topic share to the city share", () => {
    const cells = computeWardTopicCells(facts, facts, ["bike_lanes"], 5);
    expect(cells.map((cell) => cell.ward)).toEqual(["1", "2"]);
    const [wardOne, wardTwo] = cells;
    expect(wardOne.wardShare).toBe(1);
    expect(wardOne.cityShare).toBeCloseTo(6 / 11);
    expect(wardOne.logRatio).toBeGreaterThan(0);
    expect(wardTwo.wardTopicNewsletters).toBe(0);
    expect(wardTwo.logRatio).toBeLessThan(0);
    expect(Number.isFinite(wardTwo.logRatio)).toBe(true);
  });

  it("ignores unprocessed newsletters and returns nothing without data", () => {
    const cells = computeWardTopicCells(facts, facts, ["bike_lanes"], 5);
    expect(cells.find((cell) => cell.ward === "2")?.wardNewsletters).toBe(5);
    const unprocessed = [fact({ topics: null })];
    expect(computeWardTopicCells(unprocessed, unprocessed, ["bike_lanes"])).toEqual([]);
  });

  it("keeps the city baseline when only some wards are shown", () => {
    const wardOneFacts = facts.filter((item) => item.ward === "1");
    const [cell] = computeWardTopicCells(wardOneFacts, facts, ["bike_lanes"], 5);
    expect(cell.ward).toBe("1");
    expect(cell.cityShare).toBeCloseTo(6 / 11);
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
});

describe("cadence and relevance", () => {
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

  it("averages relevance per ward over scored newsletters, highest first", () => {
    const rows = computeRelevanceByWard([
      fact({ ward: "1", relevance: 2 }),
      fact({ ward: "1", relevance: 4 }),
      fact({ ward: "2", relevance: 9 }),
      fact({ ward: "2", relevance: null }),
    ]);
    expect(rows).toEqual([
      { ward: "2", averageRelevance: 9, scoredNewsletters: 1 },
      { ward: "1", averageRelevance: 3, scoredNewsletters: 2 },
    ]);
  });
});

describe("selectCoverage", () => {
  const source = (overrides: Partial<SourceCoverage>): SourceCoverage => ({
    id: 1,
    name: "A",
    ward: "1",
    source_type: "alderman",
    first_date: "2024-01-01",
    last_date: "2026-01-01",
    newsletters: 10,
    ...overrides,
  });

  it("keeps sources with newsletters in the selected wards, earliest first", () => {
    const sources = [
      source({ id: 1, name: "Late", first_date: "2025-05-01" }),
      source({ id: 2, name: "Early", first_date: "2023-01-01" }),
      source({ id: 3, name: "Empty", newsletters: 0, first_date: null }),
      source({ id: 4, name: "Other ward", ward: "9" }),
    ];
    expect(selectCoverage(sources, filters({ wards: ["1"] })).map((item) => item.name)).toEqual([
      "Early",
      "Late",
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
    minRelevance: 7,
  };

  it("carries the date range, topic, and relevance into search links", () => {
    const scope = searchScopeForFilters(filters, { includeTopic: true, includeRelevance: true });
    expect(scope).toEqual({ fromDate: "2025-11-01", toDate: "2026-02-28", topic: "bike_lanes", minRelevance: 7 });
    expect(buildSearchUrl({ ...scope, ward: "3" })).toBe(
      "/search?ward=3&topic=bike_lanes&from=2025-11-01&to=2026-02-28&min_relevance=7",
    );
  });

  it("omits filters the panel ignores and unset filters", () => {
    expect(searchScopeForFilters(filters, { includeTopic: false, includeRelevance: false })).toEqual({
      fromDate: "2025-11-01",
      toDate: "2026-02-28",
    });
    expect(searchScopeForFilters(EMPTY_FILTERS, { includeTopic: true, includeRelevance: true })).toEqual({});
  });
});
