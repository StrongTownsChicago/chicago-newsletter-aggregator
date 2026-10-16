// Links from dashboard charts to the search page.
import type { AnalyticsFilters } from "./core";

/** Search page parameters a dashboard click-through can set. Dates are inclusive YYYY-MM-DD. */
export interface SearchLinkParams {
  q?: string;
  ward?: string;
  fromDate?: string;
  toDate?: string;
}

/** First and last calendar day (YYYY-MM-DD) of a YYYY-MM month. */
export function monthDateRange(month: string): { fromDate: string; toDate: string } {
  const [year, monthNumber] = month.split("-").map(Number);
  // Day 0 of the following month is the last day of this one.
  const lastDay = new Date(Date.UTC(year, monthNumber, 0)).getUTCDate();
  return { fromDate: `${month}-01`, toDate: `${month}-${String(lastDay).padStart(2, "0")}` };
}

/**
 * The global date filters as search link parameters, so a click-through lists
 * the newsletters in the same window. Search cannot filter by lens, so only
 * panels that ignore the lens filter link to it.
 */
export function searchScopeForFilters(filters: AnalyticsFilters): SearchLinkParams {
  const scope: SearchLinkParams = {};
  if (filters.fromMonth) scope.fromDate = monthDateRange(filters.fromMonth).fromDate;
  if (filters.toMonth) scope.toDate = monthDateRange(filters.toMonth).toDate;
  return scope;
}

/** Link to the search page; multi-word terms are quoted as a phrase. */
export function buildSearchUrl(params: SearchLinkParams): string {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q.includes(" ") ? `"${params.q}"` : params.q);
  if (params.ward) search.set("ward", params.ward);
  if (params.fromDate) search.set("from", params.fromDate);
  if (params.toDate) search.set("to", params.toDate);
  const query = search.toString();
  return query ? `/search?${query}` : "/search";
}
