// Pure aggregation logic for the /analytics dashboard: data shapes, dates and
// wards, filtering, and the broad-coverage window. Terms, ward reach, coverage
// and search links live in the analytics-*.ts modules beside this one.
// Data shapes mirror the JSON written by backend/utils/compute_analytics.py.

export interface NewsletterFact {
  id: string;
  date: string; // YYYY-MM-DD, Chicago time
  source_id: number | null;
  ward: string | null;
  alder: string | null;
  /** Ids of the keyword lenses the newsletter mentions; empty when its text is unavailable. */
  lenses: string[];
  words: number;
  /** Too little text was extracted to analyze (image-only or "view in browser" issues). */
  text_unavailable?: boolean;
}

export interface SourceCoverage {
  id: number;
  name: string;
  ward: string | null;
  source_type: string;
  first_date: string | null;
  last_date: string | null;
  newsletters: number;
}

export interface TermIndex {
  min_newsletters: number;
  months: string[];
  /** [source_id, month_index] pairs. */
  buckets: [number, number][];
  /** Flat [bucket_index, newsletter_count, ...] postings per term. */
  terms: Record<string, number[]>;
}

export interface DistinctiveTerm {
  term: string;
  score: number;
  lift: number;
  ward_newsletters: number;
  ward_share: number;
  rest_share: number;
  /** Other terms from (nearly) the same newsletters that this entry stands for. */
  related_terms?: number;
}

/** A term mentioned by more wards in the latest month than in a typical recent month. */
export interface RisingTerm {
  term: string;
  latest_wards: number;
  /** Median of the baseline months' ward counts. */
  baseline_wards: number;
  baseline_month_wards: number[];
  ward_gain: number;
  latest_newsletters: number;
  /** A recurring calendar event (holiday, heritage month, seasonal program). */
  seasonal?: boolean;
}

export interface RisingTerms {
  latest_month: string | null;
  baseline_months: string[];
  /** Wards with readable newsletters in the latest month (the denominator). */
  latest_active_wards: number;
  baseline_active_wards: number[];
  terms: RisingTerm[];
}

export interface AnalyticsMetadata {
  generated_at: string;
  newsletter_count: number;
  source_count: number;
  first_date: string | null;
  last_date: string | null;
  term_count: number;
  min_term_newsletters: number;
}

/** One keyword lens: its reviewed phrase list and how many newsletters each phrase was found in. */
export interface LensDefinition {
  id: string;
  label: string;
  description: string;
  /** A Strong Towns Chicago focus area rather than a broad civic subject. */
  strong_towns_focus: boolean;
  /** Newsletters that mention the lens. */
  newsletters: number;
  phrases: { phrase: string; newsletters: number }[];
}

/** The lens definitions and the matching rules behind every lens flag (lenses.json). */
export interface LensSummary {
  /** Which text was matched: "cleaned" (standing boilerplate removed) or "raw". */
  text: "cleaned" | "raw";
  /** A newsletter mentions a lens when its phrases occur at least this many times. */
  min_mentions: number;
  /** Newsletters with enough extracted text to match. */
  readable_newsletters: number;
  lenses: LensDefinition[];
}

/** Everything the dashboard renders up front; the term index loads separately, on demand. */
export interface AnalyticsDataset {
  metadata: AnalyticsMetadata;
  newsletters: NewsletterFact[];
  sources: SourceCoverage[];
  lenses: LensSummary;
  distinctiveByWard: Record<string, DistinctiveTerm[]>;
  rising: RisingTerms;
}

export interface AnalyticsFilters {
  wards: string[]; // empty = all wards
  /** Lens id; only newsletters mentioning it are counted where a panel applies it. */
  lens: string | null;
  fromMonth: string | null; // YYYY-MM inclusive
  toMonth: string | null; // YYYY-MM inclusive
}

export const EMPTY_FILTERS: AnalyticsFilters = {
  wards: [],
  lens: null,
  fromMonth: null,
  toMonth: null,
};

/** Months with fewer newsletters than this get no share (a gap in trend lines). */
export const MIN_MONTH_NEWSLETTERS_FOR_SHARES = 10;

/** A share, or null when the denominator is too small to be meaningful. */
export function shareOrNull(count: number, total: number, minTotal: number): number | null {
  return total >= minTotal && total > 0 ? count / total : null;
}

// ---------------------------------------------------------------------------
// Dates and wards

export function monthOf(date: string): string {
  return date.slice(0, 7);
}

/** Every YYYY-MM month from start to end inclusive. */
export function listMonths(start: string, end: string): string[] {
  const months: string[] = [];
  let [year, month] = start.split("-").map(Number);
  const [endYear, endMonth] = end.split("-").map(Number);
  while (year < endYear || (year === endYear && month <= endMonth)) {
    months.push(`${year}-${String(month).padStart(2, "0")}`);
    month += 1;
    if (month > 12) {
      month = 1;
      year += 1;
    }
  }
  return months;
}

const monthNameFormat = new Intl.DateTimeFormat("en-US", { month: "short", timeZone: "UTC" });

/** "Feb 2026" for a YYYY-MM month. */
export function formatMonth(month: string): string {
  const [year, monthNumber] = month.split("-").map(Number);
  return `${monthNameFormat.format(new Date(Date.UTC(year, monthNumber - 1, 1)))} ${year}`;
}

const dayFormat = new Intl.DateTimeFormat("en-US", { dateStyle: "medium", timeZone: "UTC" });

/** "Jan 3, 2026" for a YYYY-MM-DD date. */
export function formatDay(date: string): string {
  return dayFormat.format(new Date(`${date}T00:00:00Z`));
}

const dataAsOfFormat = new Intl.DateTimeFormat("en-US", {
  dateStyle: "medium",
  timeStyle: "short",
  timeZone: "America/Chicago",
});
const countFormat = new Intl.NumberFormat("en-US");

/** "Data as of Oct 14, 2026, 3:05 PM from 1,234 newsletters (2024-01-02 to 2026-10-13)." */
export function describeDataAsOf(metadata: AnalyticsMetadata): string {
  const generatedAt = new Date(metadata.generated_at);
  const asOf = Number.isNaN(generatedAt.getTime()) ? "an unknown date" : dataAsOfFormat.format(generatedAt);
  const dateRange = metadata.first_date ? ` (${metadata.first_date} to ${metadata.last_date})` : "";
  return `Data as of ${asOf} from ${countFormat.format(metadata.newsletter_count)} newsletters${dateRange}.`;
}

/** Month names need about this many pixels each; tighter axes label years only. */
export const MIN_MONTH_LABEL_WIDTH = 30;
/** A year label needs about this many pixels before the next one. */
export const MIN_YEAR_LABEL_WIDTH = 36;

/**
 * Tick labels for a band axis of consecutive YYYY-MM months, sized to the
 * axis: month names with the year under the first month and every January
 * when there is room, otherwise the year at every January (and at the first
 * month, when it is far enough from the next January not to collide).
 */
export function monthTickLabeler(months: string[], axisWidth: number): (month: string) => string {
  const pixelsPerMonth = months.length ? axisWidth / months.length : axisWidth;
  const first = months[0];
  if (pixelsPerMonth >= MIN_MONTH_LABEL_WIDTH) {
    return (month) => {
      const [name, year] = formatMonth(month).split(" ");
      return month === first || month.endsWith("-01") ? `${name}\n${year}` : name;
    };
  }
  const monthsPerYear = 12;
  // Months from the first month to the next January (12 when the first month is a January).
  const monthsUntilJanuary = first ? monthsPerYear + 1 - Number(first.slice(5, 7)) : 0;
  const labelFirst = first !== undefined && monthsUntilJanuary * pixelsPerMonth >= MIN_YEAR_LABEL_WIDTH;
  return (month) => (month.endsWith("-01") || (labelFirst && month === first) ? month.slice(0, 4) : "");
}

export function daysBetween(start: string, end: string): number {
  const millisecondsPerDay = 24 * 60 * 60 * 1000;
  return Math.round((Date.parse(end) - Date.parse(start)) / millisecondsPerDay);
}

/** Numeric wards in numeric order, then any non-numeric labels alphabetically. */
export function compareWards(a: string, b: string): number {
  const aNumber = Number(a);
  const bNumber = Number(b);
  const aIsNumber = Number.isInteger(aNumber);
  const bIsNumber = Number.isInteger(bNumber);
  if (aIsNumber && bIsNumber) return aNumber - bNumber;
  if (aIsNumber !== bIsNumber) return aIsNumber ? -1 : 1;
  return a.localeCompare(b);
}

export function listWards(facts: NewsletterFact[]): string[] {
  const wards = new Set(facts.flatMap((fact) => (fact.ward ? [fact.ward] : [])));
  return [...wards].sort(compareWards);
}

// ---------------------------------------------------------------------------
// Filtering and summary

/** Whether a YYYY-MM month falls inside the filters' date window. */
export function isWithinMonths(month: string, filters: AnalyticsFilters): boolean {
  return (
    (!filters.fromMonth || month >= filters.fromMonth) &&
    (!filters.toMonth || month <= filters.toMonth)
  );
}

/** Whether a ward passes the ward filter (an empty selection passes every ward). */
export function isInSelectedWards(ward: string | null, filters: AnalyticsFilters): boolean {
  return filters.wards.length === 0 || (ward !== null && filters.wards.includes(ward));
}

/**
 * Apply the global filters. Panels that compare lenses, or count wards and
 * newsletters regardless of subject, pass ignoreLens so a lens filter does not
 * trivially make that lens 100% of everything.
 */
export function filterFacts(
  facts: NewsletterFact[],
  filters: AnalyticsFilters,
  options: { ignoreLens?: boolean } = {},
): NewsletterFact[] {
  return facts.filter(
    (fact) =>
      isInSelectedWards(fact.ward, filters) &&
      isWithinMonths(monthOf(fact.date), filters) &&
      (options.ignoreLens || !filters.lens || fact.lenses.includes(filters.lens)),
  );
}

/** Every ward with a source in the database, including wards with no newsletters yet. */
export function listSourceWards(sources: SourceCoverage[]): string[] {
  return [...new Set(sources.flatMap((source) => (source.ward ? [source.ward] : [])))].sort(compareWards);
}

/** The wards a view covers: the selected wards, or every ward when none are selected. */
export function wardsInScope(allWards: string[], filters: AnalyticsFilters): string[] {
  return filters.wards.length === 0 ? allWards : allWards.filter((ward) => filters.wards.includes(ward));
}

/**
 * The YYYY-MM months a filter window spans, defaulting open ends to the
 * first and last month with data.
 */
export function listWindowMonths(filters: AnalyticsFilters, dataMonths: string[]): string[] {
  const start = filters.fromMonth ?? dataMonths[0];
  const end = filters.toMonth ?? dataMonths.at(-1);
  return start && end ? listMonths(start, end) : [];
}

export interface WardCountSummary {
  /** Wards the view covers (the denominator). */
  scopeWards: number;
  /** Of those, wards with at least one newsletter in `windowFacts`. */
  wardsWithNewsletters: number;
  /** Of those, wards with no newsletter anywhere in the archive. */
  wardsNeverArchived: string[];
}

/**
 * How many of the wards in scope sent newsletters in the window, and which
 * have never had one archived. `archiveFacts` must not be date-filtered.
 */
export function summarizeWardCounts(
  scopeWards: string[],
  windowFacts: NewsletterFact[],
  archiveFacts: NewsletterFact[],
): WardCountSummary {
  const windowWards = new Set(listWards(windowFacts));
  const archivedWards = new Set(listWards(archiveFacts));
  return {
    scopeWards: scopeWards.length,
    wardsWithNewsletters: scopeWards.filter((ward) => windowWards.has(ward)).length,
    wardsNeverArchived: scopeWards.filter((ward) => !archivedWards.has(ward)),
  };
}

// ---------------------------------------------------------------------------
// Broad-coverage date window

/**
 * The default date window starts in the first month in which at least this
 * fraction of the peak number of active wards sent newsletters. Before that
 * only a handful of wards were tracked, so pooled metrics would mix "more
 * wards were added" with real change.
 */
export const BROAD_COVERAGE_PEAK_FRACTION = 0.9;

export interface MonthWardActivity {
  month: string;
  activeWards: number;
}

/** Distinct wards that sent at least one newsletter, for every month in the span. */
export function countActiveWardsByMonth(facts: NewsletterFact[]): MonthWardActivity[] {
  const wardsByMonth = new Map<string, Set<string>>();
  for (const fact of facts) {
    if (fact.ward === null) continue;
    const month = monthOf(fact.date);
    const wards = wardsByMonth.get(month) ?? new Set<string>();
    wards.add(fact.ward);
    wardsByMonth.set(month, wards);
  }
  const months = [...wardsByMonth.keys()].sort();
  if (months.length === 0) return [];
  return listMonths(months[0], months[months.length - 1]).map((month) => ({
    month,
    activeWards: wardsByMonth.get(month)?.size ?? 0,
  }));
}

export interface BroadCoverageWindow {
  /** First month (YYYY-MM) with broad coverage; the window runs to the latest month. */
  startMonth: string;
  endMonth: string;
  /** Active wards a month needs to count as broadly covered. */
  minActiveWards: number;
  peakActiveWards: number;
  /** Most wards active in any month before the window. */
  maxActiveWardsBefore: number;
  /** Months in the window. */
  months: number;
}

/**
 * The span from the first broadly covered month to the latest month. Null
 * without data, or when coverage was broad from the first month (the window
 * would be the whole archive, so there is nothing narrower to offer).
 */
export function findBroadCoverageWindow(
  facts: NewsletterFact[],
  peakFraction: number = BROAD_COVERAGE_PEAK_FRACTION,
): BroadCoverageWindow | null {
  const activity = countActiveWardsByMonth(facts);
  if (activity.length === 0) return null;
  const peakActiveWards = Math.max(...activity.map((month) => month.activeWards));
  const minActiveWards = Math.ceil(peakActiveWards * peakFraction);
  const startIndex = activity.findIndex((month) => month.activeWards >= minActiveWards);
  if (startIndex === 0) return null;
  return {
    startMonth: activity[startIndex].month,
    endMonth: activity[activity.length - 1].month,
    minActiveWards,
    peakActiveWards,
    maxActiveWardsBefore: Math.max(...activity.slice(0, startIndex).map((month) => month.activeWards)),
    months: activity.length - startIndex,
  };
}

export type DateWindowKind = "broad" | "full" | "custom";

/** Whether the date filters match the broad-coverage window, the full archive, or neither. */
export function classifyDateWindow(
  filters: AnalyticsFilters,
  window: BroadCoverageWindow | null,
): DateWindowKind {
  if (!filters.fromMonth && !filters.toMonth) return "full";
  if (window && filters.fromMonth === window.startMonth && !filters.toMonth) return "broad";
  return "custom";
}

/**
 * Drop leading and trailing points without a share, so charts start where
 * there is enough data instead of at the first stray newsletter.
 */
export function trimSparseEdges<T extends { share: number | null }>(points: T[]): T[] {
  const first = points.findIndex((point) => point.share !== null);
  if (first === -1) return [];
  const last = points.findLastIndex((point) => point.share !== null);
  return points.slice(first, last + 1);
}

// ---------------------------------------------------------------------------
// Helpers

/** The middle value (mean of the middle two for an even count), or null for no values. */
export function median(values: number[]): number | null {
  if (values.length === 0) return null;
  const sorted = [...values].sort((a, b) => a - b);
  const middle = Math.floor(sorted.length / 2);
  return sorted.length % 2 ? sorted[middle] : (sorted[middle - 1] + sorted[middle]) / 2;
}

export function countBy<T, K>(items: T[], keyOf: (item: T) => K): Map<K, number> {
  const counts = new Map<K, number>();
  for (const item of items) {
    const key = keyOf(item);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

export function groupBy<T, K>(items: T[], keyOf: (item: T) => K): Map<K, T[]> {
  const groups = new Map<K, T[]>();
  for (const item of items) {
    const key = keyOf(item);
    const group = groups.get(key);
    if (group) group.push(item);
    else groups.set(key, [item]);
  }
  return groups;
}
