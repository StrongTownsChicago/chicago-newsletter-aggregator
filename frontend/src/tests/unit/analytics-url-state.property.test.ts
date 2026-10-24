import { describe, expect, it } from "vitest";
import fc from "fast-check";
import { compareWards, type AnalyticsFilters } from "../../lib/analytics/core";
import { normalizeTermQuery } from "../../lib/analytics/terms";
import {
  DASHBOARD_URL_PARAMS,
  FULL_ARCHIVE_WINDOW,
  LEGACY_PROFILE_WARD_PARAM,
  MAX_TERM_QUERY_LENGTH,
  parseDashboardUrlState,
  reconcileDateWindow,
  serializeDashboardUrlState,
  type DashboardUrlContext,
  type DashboardViewState,
} from "../../lib/analytics/url-state";

const PROPERTY_RUNS = { numRuns: 200 };

const month = fc
  .tuple(fc.integer({ min: 2018, max: 2030 }), fc.integer({ min: 1, max: 12 }))
  .map(([year, monthNumber]) => `${year}-${String(monthNumber).padStart(2, "0")}`);

const ward = fc.oneof(fc.integer({ min: 1, max: 50 }).map(String), fc.constantFrom("citywide", "Cook County"));

const urlContext: fc.Arbitrary<DashboardUrlContext> = fc
  .record({
    wards: fc.uniqueArray(ward, { maxLength: 12 }),
    months: fc.uniqueArray(month, { minLength: 1, maxLength: 24 }).map((months) => months.sort()),
    lensIds: fc.uniqueArray(fc.stringMatching(/^[a-z][a-z_]{0,14}$/), { maxLength: 6 }),
  })
  .chain((values) =>
    fc.option(fc.constantFrom(...values.months)).map((defaultFromMonth) => ({ ...values, defaultFromMonth })),
  );

const optionOf = (values: string[]) => (values.length ? fc.option(fc.constantFrom(...values)) : fc.constant(null));

/** A view built only from values the context offers, as the dashboard itself produces. */
const validViewState = (context: DashboardUrlContext): fc.Arbitrary<DashboardViewState> =>
  fc
    .record({
      wards: fc.subarray(context.wards).map((wards) => [...wards].sort(compareWards)),
      lens: optionOf(context.lensIds),
      fromMonth: optionOf(context.months),
      term: fc
        .string({ unit: "grapheme", maxLength: 40 })
        .map(normalizeTermQuery)
        .filter((term) => term.length <= MAX_TERM_QUERY_LENGTH),
    })
    .chain(({ fromMonth, term, ...filters }) =>
      optionOf(context.months.filter((candidate) => fromMonth === null || candidate >= fromMonth)).map((toMonth) => ({
        filters: { ...filters, fromMonth, toMonth },
        term,
      })),
    );

/** Query parameters mixing the dashboard's names with context values and arbitrary text. */
const dashboardParams = (context: DashboardUrlContext) => {
  const contextValue = fc.constantFrom(...context.months, ...context.wards, ...context.lensIds, FULL_ARCHIVE_WINDOW);
  const value = fc.oneof(
    fc.string({ unit: "binary" }),
    contextValue,
    fc.array(contextValue, { maxLength: 4 }).map((values) => values.join(",")),
  );
  const name = fc.oneof(
    fc.constantFrom(...Object.values(DASHBOARD_URL_PARAMS), LEGACY_PROFILE_WARD_PARAM),
    fc.string({ unit: "binary" }),
  );
  return fc.array(fc.tuple(name, value), { maxLength: 10 }).map((entries) => new URLSearchParams(entries));
};

const contextWithParams = urlContext.chain((context) => dashboardParams(context).map((params) => ({ context, params })));
const contextWithState = urlContext.chain((context) => validViewState(context).map((state) => ({ context, state })));

describe("parseDashboardUrlState properties", () => {
  it("never throws and keeps only values the context allows", () => {
    fc.assert(
      fc.property(contextWithParams, ({ context, params }) => {
        const { filters, term } = parseDashboardUrlState(params, context);
        expect(filters.wards.every((value) => context.wards.includes(value))).toBe(true);
        expect(filters.wards).toEqual([...new Set(filters.wards)].sort(compareWards));
        expect(filters.lens === null || context.lensIds.includes(filters.lens)).toBe(true);
        for (const chosenMonth of [filters.fromMonth, filters.toMonth]) {
          expect(chosenMonth === null || context.months.includes(chosenMonth)).toBe(true);
        }
        if (filters.fromMonth !== null && filters.toMonth !== null) {
          expect(filters.fromMonth <= filters.toMonth).toBe(true);
        }
        expect(term).toBe(normalizeTermQuery(term));
        expect(term.length).toBeLessThanOrEqual(MAX_TERM_QUERY_LENGTH);
      }),
      PROPERTY_RUNS,
    );
  });

  it("parses a serialized view back to the same view", () => {
    fc.assert(
      fc.property(contextWithState, ({ context, state }) => {
        const query = serializeDashboardUrlState(state, context);
        expect(parseDashboardUrlState(new URLSearchParams(query), context)).toEqual(state);
      }),
      PROPERTY_RUNS,
    );
  });

  it("serializes whatever it parsed to a stable query string", () => {
    fc.assert(
      fc.property(contextWithParams, ({ context, params }) => {
        const query = serializeDashboardUrlState(parseDashboardUrlState(params, context), context);
        const reparsed = parseDashboardUrlState(new URLSearchParams(query), context);
        expect(serializeDashboardUrlState(reparsed, context)).toBe(query);
      }),
      PROPERTY_RUNS,
    );
  });
});

const filtersWithWindow: fc.Arbitrary<AnalyticsFilters> = fc.record({
  wards: fc.uniqueArray(ward, { maxLength: 3 }),
  lens: fc.option(fc.constantFrom("public_safety", "housing")),
  fromMonth: fc.option(month),
  toMonth: fc.option(month),
});

describe("reconcileDateWindow properties", () => {
  it("never leaves a window ending before it starts, and keeps the month just chosen", () => {
    fc.assert(
      fc.property(filtersWithWindow, fc.constantFrom("from" as const, "to" as const), (filters, changed) => {
        const reconciled = reconcileDateWindow(filters, changed);
        const { fromMonth, toMonth } = reconciled;
        if (fromMonth !== null && toMonth !== null) expect(fromMonth <= toMonth).toBe(true);
        const chosenField = changed === "from" ? "fromMonth" : "toMonth";
        expect(reconciled[chosenField]).toBe(filters[chosenField]);
        expect({ ...reconciled, fromMonth: null, toMonth: null }).toEqual({ ...filters, fromMonth: null, toMonth: null });
      }),
      PROPERTY_RUNS,
    );
  });

  it("returns an ordered window unchanged", () => {
    fc.assert(
      fc.property(filtersWithWindow, fc.constantFrom("from" as const, "to" as const), (filters, changed) => {
        const { fromMonth, toMonth } = filters;
        fc.pre(fromMonth === null || toMonth === null || fromMonth <= toMonth);
        expect(reconcileDateWindow(filters, changed)).toBe(filters);
      }),
      PROPERTY_RUNS,
    );
  });
});
