// Builders for analytics test data: newsletter facts, filters and sources with sensible defaults.
import { EMPTY_FILTERS, type AnalyticsFilters, type NewsletterFact, type SourceCoverage } from "../lib/analytics/core";

let nextId = 0;
export function fact(overrides: Partial<NewsletterFact> = {}): NewsletterFact {
  nextId += 1;
  return {
    id: `n${nextId}`,
    date: "2026-01-15",
    source_id: 1,
    ward: "1",
    alder: "Ada Alder",
    lenses: [],
    words: 100,
    ...overrides,
  };
}

export function filters(overrides: Partial<AnalyticsFilters> = {}): AnalyticsFilters {
  return { ...EMPTY_FILTERS, ...overrides };
}

export function source(overrides: Partial<SourceCoverage> = {}): SourceCoverage {
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
