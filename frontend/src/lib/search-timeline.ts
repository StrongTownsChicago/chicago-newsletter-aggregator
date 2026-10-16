import type { SupabaseClient } from "@supabase/supabase-js";
import { CHICAGO_TIME_ZONE } from "./chicago-dates";
import { SEARCH_PARAM_NAMES } from "./search-filters";

/**
 * Search term timeline: how many newsletters matching a /search query were
 * received each month (America/Chicago), and from how many wards.
 *
 * Counts come from the `search_term_timeline` Postgres function (migration
 * 007), which uses the same full-text matching as the search page. This module
 * holds the pure parts: query validation, RPC result parsing, month filling,
 * and the API response contract shared by the API route and the browser.
 */

export const SEARCH_TIMELINE_RPC = "search_term_timeline";
export const SEARCH_TIMELINE_API_PATH = "/api/search-timeline";
export const SEARCH_TIMELINE_QUERY_PARAM = "q";

/** Must match `max_query_length` in `backend/migrations/007_search_term_timeline.sql`. */
export const SEARCH_TIMELINE_MAX_QUERY_LENGTH = 200;

/**
 * PostgREST and Postgres error codes meaning the function does not exist,
 * i.e. the migration has not been applied yet.
 */
const MISSING_FUNCTION_ERROR_CODES = new Set(["PGRST202", "42883"]);

/** Postgres `query_canceled`, raised when the statement timeout is hit. */
const STATEMENT_TIMEOUT_ERROR_CODE = "57014";

/**
 * Whitespace that `websearch_to_tsquery` treats as a separator. Only these
 * runs are collapsed: other Unicode spaces (e.g. U+00A0) can change how the
 * query is parsed, so they are passed through exactly as search passes them.
 */
const QUERY_WHITESPACE_RUN = /[ \t\n\r\f\v]+/g;

const RPC_MONTH_PATTERN = /^(\d{4})-(\d{2})-01$/;
const TIMELINE_MONTH_PATTERN = /^\d{4}-(0[1-9]|1[0-2])$/;
const MONTHS_PER_YEAR = 12;

/** One month of the timeline. `month` is `YYYY-MM` in Chicago time. */
export interface TimelineMonth {
  month: string;
  newsletterCount: number;
  wardCount: number;
}

/** JSON body of a successful `/api/search-timeline` response. */
export interface SearchTimelineResponseBody {
  months: TimelineMonth[];
}

export type SearchTimelineResult =
  | { status: "ok"; months: TimelineMonth[] }
  | { status: "unavailable" }
  | { status: "timedOut" };

/**
 * Validates a search query for the timeline. Trims it like the search page
 * does and collapses ASCII whitespace runs (which does not change
 * `websearch_to_tsquery` matching, and lets equivalent queries share a cache
 * entry). Returns null when empty or too long; length is counted in
 * characters, as Postgres `char_length` does.
 */
export function normalizeTimelineQuery(
  rawQuery: string | null | undefined,
): string | null {
  const query = (rawQuery ?? "").trim().replace(QUERY_WHITESPACE_RUN, " ");
  if (!query) return null;
  return [...query].length <= SEARCH_TIMELINE_MAX_QUERY_LENGTH ? query : null;
}

const isCount = (value: unknown): value is number =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= 0;

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === "object" && value !== null;

/**
 * Parses `search_term_timeline` rows (`month` as `YYYY-MM-01`), dropping any
 * malformed row rather than failing the whole timeline.
 */
export function parseTimelineRpcRows(data: unknown): TimelineMonth[] {
  if (!Array.isArray(data)) return [];

  return data.flatMap((row): TimelineMonth[] => {
    if (!isRecord(row) || typeof row.month !== "string") return [];
    const monthMatch = RPC_MONTH_PATTERN.exec(row.month);
    const { newsletter_count: newsletterCount, ward_count: wardCount } = row;
    if (!monthMatch || !isCount(newsletterCount) || !isCount(wardCount)) {
      return [];
    }
    const month = `${monthMatch[1]}-${monthMatch[2]}`;
    return TIMELINE_MONTH_PATTERN.test(month)
      ? [{ month, newsletterCount, wardCount }]
      : [];
  });
}

/** Parses a `/api/search-timeline` JSON body; returns [] if malformed. */
export function parseTimelineResponseBody(body: unknown): TimelineMonth[] {
  if (!isRecord(body) || !Array.isArray(body.months)) return [];

  const months = body.months.filter(
    (entry): entry is TimelineMonth =>
      isRecord(entry) &&
      typeof entry.month === "string" &&
      TIMELINE_MONTH_PATTERN.test(entry.month) &&
      isCount(entry.newsletterCount) &&
      isCount(entry.wardCount),
  );
  return months.length === body.months.length ? months : [];
}

const chicagoYearMonthFormatter = new Intl.DateTimeFormat("en-CA", {
  timeZone: CHICAGO_TIME_ZONE,
  year: "numeric",
  month: "2-digit",
});

/** The Chicago calendar month containing `instant`, as `YYYY-MM`. */
export function getChicagoMonth(instant: Date): string {
  const parts = Object.fromEntries(
    chicagoYearMonthFormatter
      .formatToParts(instant)
      .map(({ type, value }) => [type, value]),
  );
  return `${parts.year}-${parts.month}`;
}

const toMonthIndex = (month: string): number => {
  const [year, monthOfYear] = month.split("-").map(Number);
  return year * MONTHS_PER_YEAR + (monthOfYear - 1);
};

const fromMonthIndex = (monthIndex: number): string => {
  const year = Math.floor(monthIndex / MONTHS_PER_YEAR);
  const monthOfYear = (monthIndex % MONTHS_PER_YEAR) + 1;
  return `${year}-${String(monthOfYear).padStart(2, "0")}`;
};

/**
 * Returns a continuous month series from the first month with a match through
 * `throughMonth` (or the last match, if later), with zero counts for months
 * that had no matches, so gaps are shown rather than skipped. Earlier months
 * are left out: before the first match, the archive may not have covered the
 * wards that later mention the term.
 */
export function fillTimelineMonths(
  months: TimelineMonth[],
  throughMonth: string,
): TimelineMonth[] {
  if (months.length === 0) return [];

  const countsByMonth = new Map(months.map((entry) => [entry.month, entry]));
  const monthIndexes = months.map((entry) => toMonthIndex(entry.month));
  const firstIndex = Math.min(...monthIndexes);
  const lastIndex = Math.max(...monthIndexes, toMonthIndex(throughMonth));

  return Array.from({ length: lastIndex - firstIndex + 1 }, (_, offset) => {
    const month = fromMonthIndex(firstIndex + offset);
    return (
      countsByMonth.get(month) ?? { month, newsletterCount: 0, wardCount: 0 }
    );
  });
}

/**
 * First month shown when the search has no start date. Before 2026 only a
 * handful of wards were in the archive, so earlier counts mostly reflect
 * coverage, not attention.
 */
export const TIMELINE_DEFAULT_START_MONTH = "2026-01";

export interface TimelineMonthRange {
  startMonth: string;
  /** Null shows through the latest month in the data. */
  endMonth: string | null;
}

/** The months to chart for a search's date filters (`YYYY-MM-DD` Chicago days). */
export function timelineRangeForDates(
  fromDate: string | null,
  toDate: string | null,
): TimelineMonthRange {
  return {
    startMonth: fromDate?.slice(0, 7) ?? TIMELINE_DEFAULT_START_MONTH,
    endMonth: toDate?.slice(0, 7) ?? null,
  };
}

/**
 * The continuous month series for `range`, with zero counts where nothing
 * matched. Empty when the range has no matches.
 */
export function clipTimelineToRange(
  months: TimelineMonth[],
  range: TimelineMonthRange,
): TimelineMonth[] {
  if (months.length === 0) return [];
  const countsByMonth = new Map(months.map((entry) => [entry.month, entry]));
  const firstIndex = toMonthIndex(range.startMonth);
  const lastIndex = toMonthIndex(range.endMonth ?? months[months.length - 1].month);
  if (lastIndex < firstIndex) return [];

  const clipped = Array.from({ length: lastIndex - firstIndex + 1 }, (_, offset) => {
    const month = fromMonthIndex(firstIndex + offset);
    return countsByMonth.get(month) ?? { month, newsletterCount: 0, wardCount: 0 };
  });
  return clipped.some((entry) => entry.newsletterCount > 0) ? clipped : [];
}

/** Whether a Supabase RPC error means the timeline function is not deployed. */
export function isMissingFunctionError(error: { code?: string }): boolean {
  return error.code !== undefined && MISSING_FUNCTION_ERROR_CODES.has(error.code);
}

/** Whether a Supabase RPC error is the statement timeout cancelling the query. */
export function isStatementTimeoutError(error: { code?: string }): boolean {
  return error.code === STATEMENT_TIMEOUT_ERROR_CODE;
}

/**
 * Fetches the timeline for a normalized query, filled through the current
 * Chicago month. Resolves `unavailable` when the database function is missing
 * and `timedOut` when the query hit its statement timeout; throws on any other
 * database error.
 */
export async function fetchSearchTimeline(
  supabase: Pick<SupabaseClient, "rpc">,
  query: string,
  now: Date,
): Promise<SearchTimelineResult> {
  const response = await supabase.rpc(SEARCH_TIMELINE_RPC, {
    search_query: query,
  });
  const { error } = response;
  // Untyped client: parseTimelineRpcRows validates the rows.
  const data: unknown = response.data;

  if (error) {
    if (isMissingFunctionError(error)) return { status: "unavailable" };
    if (isStatementTimeoutError(error)) return { status: "timedOut" };
    throw new Error(`Failed to fetch search timeline: ${error.message}`);
  }

  return {
    status: "ok",
    months: fillTimelineMonths(parseTimelineRpcRows(data), getChicagoMonth(now)),
  };
}

/** The API URL that returns the timeline for `query`. */
export function buildTimelineApiUrl(query: string): string {
  const params = new URLSearchParams({ [SEARCH_TIMELINE_QUERY_PARAM]: query });
  return `${SEARCH_TIMELINE_API_PATH}?${params.toString()}`;
}

const monthLabelFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  month: "short",
  year: "numeric",
});

/** Formats `YYYY-MM` as e.g. "Mar 2026". */
export function formatTimelineMonth(month: string): string {
  const [year, monthOfYear] = month.split("-").map(Number);
  return monthLabelFormatter.format(new Date(Date.UTC(year, monthOfYear - 1)));
}

const shortMonthFormatter = new Intl.DateTimeFormat("en-US", {
  timeZone: "UTC",
  month: "short",
});

/** Formats `YYYY-MM` as e.g. "Mar". */
export function formatShortMonth(month: string): string {
  const [year, monthOfYear] = month.split("-").map(Number);
  return shortMonthFormatter.format(new Date(Date.UTC(year, monthOfYear - 1)));
}

/** "Jan–Oct 2026", or "Nov 2025–Mar 2026" across years. */
export function formatMonthRange(firstMonth: string, lastMonth: string): string {
  if (firstMonth === lastMonth) return formatTimelineMonth(firstMonth);
  const end = formatTimelineMonth(lastMonth);
  const start =
    firstMonth.slice(0, 4) === lastMonth.slice(0, 4)
      ? formatShortMonth(firstMonth)
      : formatTimelineMonth(firstMonth);
  return `${start}–${end}`;
}

/** Year label under a bar: on the first bar and at each January, else null. */
export function yearLabelForBar(month: string, index: number): string | null {
  return index === 0 || month.endsWith("-01") ? month.slice(0, 4) : null;
}

/** First and last day (`YYYY-MM-DD`) of a `YYYY-MM` month. */
export function monthDateRange(month: string): { from: string; to: string } {
  const [year, monthOfYear] = month.split("-").map(Number);
  const lastDay = new Date(Date.UTC(year, monthOfYear, 0)).getUTCDate();
  return { from: `${month}-01`, to: `${month}-${String(lastDay).padStart(2, "0")}` };
}

/** The month a search's dates cover exactly, or null for any other range. */
export function selectedTimelineMonth(
  fromDate: string | null,
  toDate: string | null,
): string | null {
  if (!fromDate || !toDate) return null;
  const month = fromDate.slice(0, 7);
  const range = monthDateRange(month);
  return range.from === fromDate && range.to === toDate ? month : null;
}

/**
 * The months to chart for a search. A search narrowed to one month (e.g. by
 * clicking a bar) keeps the full chart so that month shows in context.
 */
export function timelineRangeForSearch(
  fromDate: string | null,
  toDate: string | null,
): TimelineMonthRange {
  const selected = selectedTimelineMonth(fromDate, toDate);
  if (!selected) return timelineRangeForDates(fromDate, toDate);
  return {
    startMonth: selected < TIMELINE_DEFAULT_START_MONTH ? selected : TIMELINE_DEFAULT_START_MONTH,
    endMonth: null,
  };
}

/** The current search URL without its date filters, back on page 1. */
export function buildSearchUrlWithoutDates(searchUrl: URL): string {
  const url = new URL(searchUrl);
  for (const name of [SEARCH_PARAM_NAMES.fromDate, SEARCH_PARAM_NAMES.toDate, SEARCH_PARAM_NAMES.page]) {
    url.searchParams.delete(name);
  }
  return `${url.pathname}${url.search}`;
}

/** The current search URL narrowed to one month, back on page 1. */
export function buildMonthSearchUrl(searchUrl: URL, month: string): string {
  const url = new URL(searchUrl);
  const { from, to } = monthDateRange(month);
  url.searchParams.set(SEARCH_PARAM_NAMES.fromDate, from);
  url.searchParams.set(SEARCH_PARAM_NAMES.toDate, to);
  url.searchParams.delete(SEARCH_PARAM_NAMES.page);
  return `${url.pathname}${url.search}`;
}

/** Smallest bar height (percent) for a non-zero month, so it stays visible. */
const MIN_NONZERO_BAR_PERCENT = 4;
const FULL_BAR_PERCENT = 100;

/** Bar height as a percentage of the tallest month; zero months stay at 0. */
export function barHeightPercent(count: number, maxCount: number): number {
  if (count <= 0 || maxCount <= 0) return 0;
  return Math.max(
    MIN_NONZERO_BAR_PERCENT,
    Math.round((count / maxCount) * FULL_BAR_PERCENT),
  );
}

export interface TimelineSummary {
  totalNewsletters: number;
  monthsWithMatches: number;
  /** The month with the most matching newsletters (earliest on ties). */
  peak: TimelineMonth;
}

/** Totals and the peak month; null for an empty timeline. */
export function summarizeTimeline(
  months: TimelineMonth[],
): TimelineSummary | null {
  if (months.length === 0) return null;

  return {
    totalNewsletters: months.reduce(
      (total, entry) => total + entry.newsletterCount,
      0,
    ),
    monthsWithMatches: months.filter((entry) => entry.newsletterCount > 0)
      .length,
    peak: months.reduce((peak, entry) =>
      entry.newsletterCount > peak.newsletterCount ? entry : peak,
    ),
  };
}
