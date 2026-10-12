import {
  addDaysToIsoDate,
  parseIsoDate,
  startOfChicagoDayUtc,
} from "./chicago-dates";
import { ALL_TOPICS } from "./topics";

/**
 * Search page URL parameters: parsing/validation into a typed filter object,
 * serialization back into a base URL for pagination, and application of the
 * filters to Supabase query builders.
 *
 * Invalid or out-of-range values are dropped (treated as "no filter") so a
 * hand-edited or stale URL never breaks the page.
 */

export const SEARCH_PATH = "/search";
export const SEARCH_PAGE_SIZE = 20;

export const MAX_RELEVANCE_SCORE = 10;

/** Selectable minimum relevance scores (1 through the maximum score). */
export const RELEVANCE_THRESHOLD_OPTIONS: number[] = Array.from(
  { length: MAX_RELEVANCE_SCORE },
  (_, index) => index + 1,
);

export const SEARCH_SORTS = ["newest", "oldest", "relevance"] as const;
export type SearchSort = (typeof SEARCH_SORTS)[number];
export const DEFAULT_SEARCH_SORT: SearchSort = "newest";

export const SEARCH_SORT_LABELS: Record<SearchSort, string> = {
  newest: "Newest first",
  oldest: "Oldest first",
  relevance: "Highest relevance",
};

/** URL parameter name for each search setting. */
export const SEARCH_PARAM_NAMES = {
  query: "q",
  ward: "ward",
  sourceId: "source",
  sourceType: "source_type",
  topic: "topic",
  fromDate: "from",
  toDate: "to",
  minRelevance: "min_relevance",
  sort: "sort",
  page: "page",
} as const;

export interface SearchFilters {
  /** Full-text search keywords; empty string when absent. */
  query: string;
  /** Ward number as stored in `sources.ward_number`. */
  ward: string | null;
  sourceId: number | null;
  sourceType: string | null;
  /** One of the canonical topics in `ALL_TOPICS`. */
  topic: string | null;
  /** Inclusive Chicago calendar date, `YYYY-MM-DD`. */
  fromDate: string | null;
  /** Inclusive Chicago calendar date, `YYYY-MM-DD`. */
  toDate: string | null;
  /** Minimum relevance score (1-10); null when not filtering. */
  minRelevance: number | null;
}

export interface SearchState {
  filters: SearchFilters;
  sort: SearchSort;
  page: number;
}

const POSITIVE_INTEGER_PATTERN = /^\d+$/;
const SOURCE_TYPE_PATTERN = /^[a-z_]+$/;

const readParam = (params: URLSearchParams, name: string): string =>
  params.get(name)?.trim() ?? "";

const parsePositiveInteger = (value: string): number | null => {
  if (!POSITIVE_INTEGER_PATTERN.test(value)) return null;
  const parsed = Number(value);
  return Number.isSafeInteger(parsed) && parsed >= 1 ? parsed : null;
};

const parseWard = (value: string): string | null => {
  const ward = parsePositiveInteger(value);
  return ward === null ? null : String(ward);
};

const parseSourceType = (value: string): string | null =>
  SOURCE_TYPE_PATTERN.test(value) ? value : null;

const parseTopic = (value: string): string | null =>
  ALL_TOPICS.includes(value) ? value : null;

/**
 * A minimum of 0 matches every scored newsletter, so it is treated as
 * "no filter" (which also keeps not-yet-scored newsletters in results).
 */
const parseMinRelevance = (value: string): number | null => {
  const score = parsePositiveInteger(value);
  return score !== null && score <= MAX_RELEVANCE_SCORE ? score : null;
};

const parseSort = (value: string): SearchSort =>
  (SEARCH_SORTS as readonly string[]).includes(value)
    ? (value as SearchSort)
    : DEFAULT_SEARCH_SORT;

const parsePage = (value: string): number => parsePositiveInteger(value) ?? 1;

/** Orders a date range chronologically so a reversed range still matches. */
const orderDateRange = (
  fromDate: string | null,
  toDate: string | null,
): Pick<SearchFilters, "fromDate" | "toDate"> =>
  fromDate && toDate && fromDate > toDate
    ? { fromDate: toDate, toDate: fromDate }
    : { fromDate, toDate };

/** Parses search page URL parameters into validated search state. */
export function parseSearchParams(params: URLSearchParams): SearchState {
  const read = (name: string) => readParam(params, name);

  return {
    filters: {
      query: read(SEARCH_PARAM_NAMES.query),
      ward: parseWard(read(SEARCH_PARAM_NAMES.ward)),
      sourceId: parsePositiveInteger(read(SEARCH_PARAM_NAMES.sourceId)),
      sourceType: parseSourceType(read(SEARCH_PARAM_NAMES.sourceType)),
      topic: parseTopic(read(SEARCH_PARAM_NAMES.topic)),
      ...orderDateRange(
        parseIsoDate(read(SEARCH_PARAM_NAMES.fromDate)),
        parseIsoDate(read(SEARCH_PARAM_NAMES.toDate)),
      ),
      minRelevance: parseMinRelevance(read(SEARCH_PARAM_NAMES.minRelevance)),
    },
    sort: parseSort(read(SEARCH_PARAM_NAMES.sort)),
    page: parsePage(read(SEARCH_PARAM_NAMES.page)),
  };
}

/**
 * Builds the search URL for the given filters and sort, without the page
 * parameter (pagination appends it). Empty filters and the default sort are
 * omitted to keep URLs short.
 */
export function buildSearchBaseUrl(
  filters: SearchFilters,
  sort: SearchSort,
): string {
  const entries: [string, string | number | null][] = [
    [SEARCH_PARAM_NAMES.query, filters.query || null],
    [SEARCH_PARAM_NAMES.ward, filters.ward],
    [SEARCH_PARAM_NAMES.sourceId, filters.sourceId],
    [SEARCH_PARAM_NAMES.sourceType, filters.sourceType],
    [SEARCH_PARAM_NAMES.topic, filters.topic],
    [SEARCH_PARAM_NAMES.fromDate, filters.fromDate],
    [SEARCH_PARAM_NAMES.toDate, filters.toDate],
    [SEARCH_PARAM_NAMES.minRelevance, filters.minRelevance],
    [SEARCH_PARAM_NAMES.sort, sort === DEFAULT_SEARCH_SORT ? null : sort],
  ];

  const params = new URLSearchParams();
  for (const [name, value] of entries) {
    if (value !== null) params.set(name, String(value));
  }

  const queryString = params.toString();
  return queryString ? `${SEARCH_PATH}?${queryString}` : SEARCH_PATH;
}

/**
 * Whether the filters reference `sources.*` columns, which requires an inner
 * join on sources (see `buildNewsletterCountSelect`). The source id filter
 * uses `newsletters.source_id` directly and needs no join.
 */
export function requiresSourceJoin(filters: SearchFilters): boolean {
  return filters.ward !== null || filters.sourceType !== null;
}

/** Zero-based inclusive row range for a 1-based page number. */
export function getPageRange(
  page: number,
  pageSize: number = SEARCH_PAGE_SIZE,
): { start: number; end: number } {
  const start = (page - 1) * pageSize;
  return { start, end: start + pageSize - 1 };
}

/** The subset of the PostgREST filter builder API used by search filters. */
export interface FilterableQuery {
  textSearch(
    column: string,
    query: string,
    options: { type: "websearch"; config: string },
  ): this;
  eq(column: string, value: string | number): this;
  contains(column: string, value: string[]): this;
  gte(column: string, value: string | number): this;
  lt(column: string, value: string): this;
}

interface ColumnOrdering {
  column: string;
  ascending: boolean;
  nullsFirst?: boolean;
}

/**
 * Column orderings for each sort, applied in sequence. Relevance sorting puts
 * unscored newsletters last and breaks ties by newest first.
 */
export const SEARCH_SORT_ORDERINGS: Record<SearchSort, ColumnOrdering[]> = {
  newest: [{ column: "received_date", ascending: false }],
  oldest: [{ column: "received_date", ascending: true }],
  relevance: [
    { column: "relevance_score", ascending: false, nullsFirst: false },
    { column: "received_date", ascending: false },
  ],
};

/** The subset of the PostgREST transform builder API used for sorting. */
export interface SortableQuery {
  order(
    column: string,
    options: { ascending: boolean; nullsFirst?: boolean },
  ): this;
}

/**
 * Applies the search filters to a newsletters query. Used for both the count
 * and the data query so they always filter identically.
 */
export function applySearchFilters<Query extends FilterableQuery>(
  query: Query,
  filters: SearchFilters,
): Query {
  let filtered = query;

  if (filters.query) {
    filtered = filtered.textSearch("search_vector", filters.query, {
      type: "websearch",
      config: "english",
    });
  }
  if (filters.sourceId !== null) {
    filtered = filtered.eq("source_id", filters.sourceId);
  }
  if (filters.sourceType !== null) {
    filtered = filtered.eq("sources.source_type", filters.sourceType);
  }
  if (filters.ward !== null) {
    filtered = filtered.eq("sources.ward_number", filters.ward);
  }
  if (filters.topic !== null) {
    filtered = filtered.contains("topics", [filters.topic]);
  }
  if (filters.fromDate !== null) {
    filtered = filtered.gte(
      "received_date",
      startOfChicagoDayUtc(filters.fromDate),
    );
  }
  if (filters.toDate !== null) {
    // Exclusive upper bound at the start of the next day keeps the whole "to" day.
    filtered = filtered.lt(
      "received_date",
      startOfChicagoDayUtc(addDaysToIsoDate(filters.toDate, 1)),
    );
  }
  if (filters.minRelevance !== null) {
    filtered = filtered.gte("relevance_score", filters.minRelevance);
  }

  return filtered;
}

/** Applies the sort order to a newsletters data query. */
export function applySearchSort<Query extends SortableQuery>(
  query: Query,
  sort: SearchSort,
): Query {
  return SEARCH_SORT_ORDERINGS[sort].reduce(
    (sorted, { column, ...options }) => sorted.order(column, options),
    query,
  );
}
