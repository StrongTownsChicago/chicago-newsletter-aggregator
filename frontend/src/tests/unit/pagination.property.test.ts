import { describe, expect, it } from "vitest";
import fc from "fast-check";
import { countPages, getPageRange, parsePageParam } from "../../lib/pagination";
import { getPageRange as getSearchPageRange } from "../../lib/search-filters";

const page = fc.integer({ min: 1, max: 100_000 });
const pageSize = fc.integer({ min: 1, max: 500 });
const PROPERTY_RUNS = { numRuns: 200 };

describe("pagination properties", () => {
  it("parses any page parameter to a positive integer", () => {
    fc.assert(
      fc.property(fc.option(fc.string({ unit: "binary" })), (rawPage) => {
        const parsed = parsePageParam(rawPage);
        expect(Number.isInteger(parsed) && parsed >= 1).toBe(true);
      }),
      PROPERTY_RUNS,
    );
  });

  it("gives each page exactly pageSize rows, right after the previous page", () => {
    fc.assert(
      fc.property(page, pageSize, (pageNumber, size) => {
        const { from, to } = getPageRange(pageNumber, size);
        expect(to - from + 1).toBe(size);
        expect(getPageRange(pageNumber + 1, size).from).toBe(to + 1);
        expect(getSearchPageRange(pageNumber, size)).toEqual({ start: from, end: to });
      }),
      PROPERTY_RUNS,
    );
    expect(getPageRange(1).from).toBe(0);
  });

  it("has a last page that holds the last row and no empty page", () => {
    fc.assert(
      fc.property(fc.integer({ min: 1, max: 1_000_000 }), pageSize, (totalCount, size) => {
        const lastPage = countPages(totalCount, size);
        const { from, to } = getPageRange(lastPage, size);
        expect(from).toBeLessThanOrEqual(totalCount - 1);
        expect(to).toBeGreaterThanOrEqual(totalCount - 1);
      }),
      PROPERTY_RUNS,
    );
    expect(countPages(0)).toBe(0);
  });
});
