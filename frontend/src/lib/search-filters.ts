import {
  addDaysToIsoDate,
  parseIsoDate,
  startOfChicagoDayUtc,
} from "./chicago-dates";
import { formatLongDate } from "./archive-months";
import { humanizeIdentifier } from "./format";
import { ALL_TOPICS, formatTopicLabel } from "./topics";

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

export const SEARCH_SORTS = ["newest", "oldest"] as const;
export type SearchSort = (typeof SEARCH_SORTS)[number];
export const DEFAULT_SEARCH_SORT: SearchSort = "newest";

export const SEARCH_SORT_LABELS: Record<SearchSort, string> = {
  newest: "Newest first",
  oldest: "Oldest first",
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
}

export const EMPTY_SEARCH_FILTERS: SearchFilters = {
  query: "",
  ward: null,
  sourceId: null,
  sourceType: null,
  topic: null,
  fromDate: null,
  toDate: null,
};

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
    [SEARCH_PARAM_NAMES.sort, sort === DEFAULT_SEARCH_SORT ? null : sort],
  ];

  const params = new URLSearchParams();
  for (const [name, value] of entries) {
    if (value !== null) params.set(name, String(value));
  }

  const queryString = params.toString();
  return queryString ? `${SEARCH_PATH}?${queryString}` : SEARCH_PATH;
}

/** Filters other than the keyword query, which has its own search box. */
type NarrowingFilterKey = Exclude<keyof SearchFilters, "query">;

export interface ActiveSearchFilter {
  key: NarrowingFilterKey;
  label: string;
  /** Search URL with this one filter removed, back on the first page. */
  removeUrl: string;
}

const describeFilter = (
  key: NarrowingFilterKey,
  filters: SearchFilters,
  sourceNames: ReadonlyMap<number, string>,
): string | null => {
  switch (key) {
    case "ward":
      return filters.ward && `Ward ${filters.ward}`;
    case "sourceId":
      return filters.sourceId === null
        ? null
        : (sourceNames.get(filters.sourceId) ?? `Source ${filters.sourceId}`);
    case "sourceType":
      return filters.sourceType && humanizeIdentifier(filters.sourceType);
    case "topic":
      return filters.topic && formatTopicLabel(filters.topic);
    case "fromDate":
      return filters.fromDate && `From ${formatLongDate(filters.fromDate)}`;
    case "toDate":
      return filters.toDate && `To ${formatLongDate(filters.toDate)}`;
  }
};

const NARROWING_FILTER_KEYS: readonly NarrowingFilterKey[] = [
  "topic",
  "ward",
  "sourceId",
  "sourceType",
  "fromDate",
  "toDate",
];

/**
 * The filters narrowing the results beyond the keyword query, each with a
 * label and a link that removes it. `sourceNames` labels a source filter.
 */
export function listActiveSearchFilters(
  filters: SearchFilters,
  sort: SearchSort,
  sourceNames: ReadonlyMap<number, string>,
): ActiveSearchFilter[] {
  return NARROWING_FILTER_KEYS.flatMap((key) => {
    const label = describeFilter(key, filters, sourceNames);
    if (!label) return [];
    const removeUrl = buildSearchBaseUrl({ ...filters, [key]: null }, sort);
    return [{ key, label, removeUrl }];
  });
}

/** The search URL keeping only the keywords and sort, dropping every filter. */
export function buildSearchUrlWithoutFilters(
  filters: SearchFilters,
  sort: SearchSort,
): string {
  return buildSearchBaseUrl({ ...EMPTY_SEARCH_FILTERS, query: filters.query }, sort);
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
  gte(column: string, value: string): this;
  lt(column: string, value: string): this;
}

interface ColumnOrdering {
  column: string;
  ascending: boolean;
}

/** Column orderings for each sort, applied in sequence. */
export const SEARCH_SORT_ORDERINGS: Record<SearchSort, ColumnOrdering[]> = {
  newest: [{ column: "received_date", ascending: false }],
  oldest: [{ column: "received_date", ascending: true }],
};

/** The subset of the PostgREST transform builder API used for sorting. */
export interface SortableQuery {
  order(column: string, options: { ascending: boolean }): this;
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
