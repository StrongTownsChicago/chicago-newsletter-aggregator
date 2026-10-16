import { describe, expect, it } from "vitest";
import { EMPTY_FILTERS, type TermIndex } from "../../lib/analytics";
import {
  expandTermPostings,
  normalizeTermQuery,
  resolveIndexedTerm,
  suggestTerms,
  termMentionsByMonth,
  termMentionsByWard,
} from "../../lib/analytics-terms";
import { fact, filters } from "../analytics-fixtures";

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

  it("resolves queries to indexed terms and reports misses as null", () => {
    expect(resolveIndexedTerm(index, "Bike Lanes")).toBe("bike lanes");
    expect(resolveIndexedTerm(index, "streetcar")).toBeNull();
    expect(resolveIndexedTerm(index, "  ")).toBeNull();
  });

  it("finds a term under its indexed written form whichever plural form is typed", () => {
    // The backend merges "bike lane" and "bike lanes" and names the group by its commoner form.
    expect(resolveIndexedTerm(index, "bike lane")).toBe("bike lanes");
    expect(resolveIndexedTerm(index, "Bikes")).toBe("bike");
    expect(resolveIndexedTerm(index, "bike shares")).toBe("bike share");
  });

  it("does not fold words the backend keeps whole", () => {
    const newsIndex: TermIndex = { ...index, terms: { new: [0, 1] } };
    expect(resolveIndexedTerm(newsIndex, "news")).toBeNull();
  });

  it("ignores inherited object keys instead of returning prototype members", () => {
    for (const query of ["constructor", "toString", "__proto__", "hasOwnProperty"]) {
      expect(resolveIndexedTerm(index, query)).toBeNull();
    }
  });

  it("suggests longer indexed terms by prefix, shortest first", () => {
    expect(suggestTerms(index, "bike", 5)).toEqual(["bike lanes", "bike share"]);
    expect(suggestTerms(index, "", 5)).toEqual([]);
  });

  it("leaves the queried term out of suggestions even when typed in another form", () => {
    expect(suggestTerms(index, "bike lane", 5)).toEqual([]);
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
