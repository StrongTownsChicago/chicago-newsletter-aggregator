// The /analytics view as a query string, for sharing and back/forward.
// Parsing never throws: invalid values fall back to the defaults.
import { compareWards, type AnalyticsFilters } from "./core";
import { normalizeTermQuery } from "./terms";

/** Query parameter names; readers see "topic", never the internal "lens". */
export const DASHBOARD_URL_PARAMS = {
  wards: "wards",
  topic: "topic",
  from: "from",
  to: "to",
  window: "window",
  term: "term",
} as const;

/** The former ward profile parameter. It still opens that ward and wins over `wards`. */
export const LEGACY_PROFILE_WARD_PARAM = "ward";

/** `window=` value for a window starting at the beginning of the archive. */
export const FULL_ARCHIVE_WINDOW = "all";
/** Longer term queries are ignored; the index holds one- and two-word terms. */
export const MAX_TERM_QUERY_LENGTH = 80;
const WARD_LIST_SEPARATOR = ",";
const ENCODED_WARD_LIST_SEPARATOR = encodeURIComponent(WARD_LIST_SEPARATOR);

export interface DashboardViewState {
  filters: AnalyticsFilters;
  /** The term explorer query (normalized), or "". */
  term: string;
}

/** The values a URL may choose from; anything else is ignored. */
export interface DashboardUrlContext {
  /** Wards the ward filter offers. */
  wards: string[];
  /** Every month the date filters offer, in order. */
  months: string[];
  lensIds: string[];
  /** The default window's first month, or null when the default is the full archive. */
  defaultFromMonth: string | null;
}

function parseWards(value: string | null, allowed: string[]): string[] {
  if (!value) return [];
  const allowedWards = new Set(allowed);
  const wards = new Set(
    value
      .split(WARD_LIST_SEPARATOR)
      .map((ward) => ward.trim())
      .filter((ward) => allowedWards.has(ward)),
  );
  return [...wards].sort(compareWards);
}

function parseChoice(value: string | null, allowed: string[]): string | null {
  return value !== null && allowed.includes(value) ? value : null;
}

function parseTerm(value: string | null): string {
  const term = normalizeTermQuery(value ?? "");
  return term.length <= MAX_TERM_QUERY_LENGTH ? term : "";
}

export function parseDashboardUrlState(params: URLSearchParams, context: DashboardUrlContext): DashboardViewState {
  const fromMonth =
    params.get(DASHBOARD_URL_PARAMS.window) === FULL_ARCHIVE_WINDOW
      ? null
      : (parseChoice(params.get(DASHBOARD_URL_PARAMS.from), context.months) ?? context.defaultFromMonth);
  const toCandidate = parseChoice(params.get(DASHBOARD_URL_PARAMS.to), context.months);
  // A window that ends before it starts is ignored rather than shown empty.
  const toMonth = toCandidate !== null && (fromMonth === null || toCandidate >= fromMonth) ? toCandidate : null;
  const legacyWard = parseChoice(params.get(LEGACY_PROFILE_WARD_PARAM), context.wards);
  return {
    filters: {
      wards: legacyWard !== null ? [legacyWard] : parseWards(params.get(DASHBOARD_URL_PARAMS.wards), context.wards),
      lens: parseChoice(params.get(DASHBOARD_URL_PARAMS.topic), context.lensIds),
      fromMonth,
      toMonth,
    },
    term: parseTerm(params.get(DASHBOARD_URL_PARAMS.term)),
  };
}

/**
 * The query string (without "?") for a view, leaving out every default so the
 * default view has a bare URL. Parameters come in a fixed order, so equal views
 * give equal strings.
 */
export function serializeDashboardUrlState(state: DashboardViewState, context: DashboardUrlContext): string {
  const params = new URLSearchParams();
  const { filters } = state;
  if (filters.wards.length) {
    params.set(DASHBOARD_URL_PARAMS.wards, [...filters.wards].sort(compareWards).join(WARD_LIST_SEPARATOR));
  }
  if (filters.lens) params.set(DASHBOARD_URL_PARAMS.topic, filters.lens);
  if (filters.fromMonth === null && context.defaultFromMonth !== null) {
    params.set(DASHBOARD_URL_PARAMS.window, FULL_ARCHIVE_WINDOW);
  } else if (filters.fromMonth !== null && filters.fromMonth !== context.defaultFromMonth) {
    params.set(DASHBOARD_URL_PARAMS.from, filters.fromMonth);
  }
  if (filters.toMonth) params.set(DASHBOARD_URL_PARAMS.to, filters.toMonth);
  const term = normalizeTermQuery(state.term);
  if (term) params.set(DASHBOARD_URL_PARAMS.term, term);
  // Commas are valid in a query string; leaving them unescaped keeps shared links readable ("wards=1,2").
  return params.toString().replaceAll(ENCODED_WARD_LIST_SEPARATOR, WARD_LIST_SEPARATOR);
}

/** Changes closer together than this share one history entry, so Back skips a burst of clicks. */
export const HISTORY_COALESCE_MS = 1000;

/** Push a new history entry, or replace the current one when the last push was moments ago. */
export function chooseHistoryMode(nowMs: number, lastPushMs: number | null): "push" | "replace" {
  return lastPushMs !== null && nowMs - lastPushMs < HISTORY_COALESCE_MS ? "replace" : "push";
}

/**
 * Keep a window from ending before it starts: moving "from" past "to" clears
 * "to" (latest), and moving "to" before "from" moves "from" to the same month.
 */
export function reconcileDateWindow(filters: AnalyticsFilters, changed: "from" | "to"): AnalyticsFilters {
  const { fromMonth, toMonth } = filters;
  if (fromMonth === null || toMonth === null || fromMonth <= toMonth) return filters;
  return changed === "from" ? { ...filters, toMonth: null } : { ...filters, fromMonth: toMonth };
}

/** The production link to a view: the page's canonical URL with the view's query string. */
export function buildCanonicalViewUrl(canonicalUrl: string, query: string): string {
  const url = new URL(canonicalUrl);
  url.search = query;
  return url.href;
}
