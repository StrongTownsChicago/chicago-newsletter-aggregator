import { describe, expect, it } from "vitest";
import fc from "fast-check";
import { parseIsoDate } from "../../lib/chicago-dates";
import {
  SEARCH_PARAM_NAMES,
  SEARCH_SORTS,
  buildSearchBaseUrl,
  parseSearchParams,
  type SearchState,
} from "../../lib/search-filters";
import { ALL_TOPICS } from "../../lib/topics";

const PARAM_NAMES = Object.values(SEARCH_PARAM_NAMES);
const URL_BASE = "https://example.test";

const paddedWithWhitespace = (value: fc.Arbitrary<string>) =>
  fc.tuple(fc.constantFrom("", " ", "\t", " "), value, fc.constantFrom("", " ", "\n")).map((parts) => parts.join(""));

const isoDateLike = fc
  .tuple(fc.integer({ min: 0, max: 9999 }), fc.integer({ min: 0, max: 13 }), fc.integer({ min: 0, max: 32 }))
  .map(([year, month, day]) =>
    [String(year).padStart(4, "0"), String(month).padStart(2, "0"), String(day).padStart(2, "0")].join("-"),
  );

/** Values a search URL could carry: plausible ones, near misses, and arbitrary text. */
const paramValue = fc.oneof(
  fc.string({ unit: "binary" }),
  paddedWithWhitespace(fc.oneof(
    fc.integer({ min: -5, max: 100 }).map(String),
    fc.bigInt({ min: 0n, max: 10n ** 20n }).map(String),
    fc.constantFrom(...ALL_TOPICS, ...SEARCH_SORTS, "community_meeting", "1.5", "1e3", "0x10"),
    fc.stringMatching(/^[a-z_]{1,12}$/),
    isoDateLike,
  )),
);

const paramName = fc.oneof(fc.constantFrom(...PARAM_NAMES), fc.string({ unit: "binary" }));

const searchParams = fc
  .array(fc.tuple(paramName, paramValue), { maxLength: 12 })
  .map((entries) => new URLSearchParams(entries));

const PROPERTY_RUNS = { numRuns: 300 };

function expectValidIds({ filters, page }: SearchState): void {
  if (filters.ward !== null) expect(filters.ward).toMatch(/^[1-9]\d*$/);
  for (const id of [filters.sourceId, page]) {
    if (id !== null) expect(Number.isSafeInteger(id) && id >= 1).toBe(true);
  }
  if (filters.ward !== null) expect(Number.isSafeInteger(Number(filters.ward))).toBe(true);
}

function expectValidDates({ fromDate, toDate }: SearchState["filters"]): void {
  for (const date of [fromDate, toDate]) {
    if (date !== null) expect(parseIsoDate(date)).toBe(date);
  }
  if (fromDate !== null && toDate !== null) {
    expect(fromDate <= toDate).toBe(true);
  }
}

function expectValidState(state: SearchState): void {
  const { filters, sort } = state;
  expect(filters.query).toBe(filters.query.trim());
  expectValidIds(state);
  if (filters.sourceType !== null) expect(filters.sourceType).toMatch(/^[a-z_]+$/);
  if (filters.topic !== null) expect(ALL_TOPICS).toContain(filters.topic);
  expectValidDates(filters);
  expect(SEARCH_SORTS).toContain(sort);
}

describe("parseSearchParams properties", () => {
  it("never throws and keeps only valid values", () => {
    fc.assert(
      fc.property(searchParams, (params) => {
        expectValidState(parseSearchParams(params));
      }),
      PROPERTY_RUNS,
    );
  });

  it("parses the URL built from parsed filters back to the same filters and sort", () => {
    fc.assert(
      fc.property(searchParams, (params) => {
        const { filters, sort } = parseSearchParams(params);
        const builtUrl = new URL(buildSearchBaseUrl(filters, sort), URL_BASE);
        expect(parseSearchParams(builtUrl.searchParams)).toEqual({ filters, sort, page: 1 });
      }),
      PROPERTY_RUNS,
    );
  });

  it("reads only the first of repeated parameters", () => {
    fc.assert(
      fc.property(searchParams, paramValue, (params, extraValue) => {
        const withRepeats = new URLSearchParams(params);
        for (const name of new Set(params.keys())) withRepeats.append(name, extraValue);
        expect(parseSearchParams(withRepeats)).toEqual(parseSearchParams(params));
      }),
      PROPERTY_RUNS,
    );
  });
});
