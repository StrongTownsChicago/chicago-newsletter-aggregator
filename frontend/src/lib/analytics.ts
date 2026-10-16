// Pure aggregation logic for the local /analytics dashboard.
// Data shapes mirror the JSON written by backend/utils/compute_analytics.py.

import { foldTerm } from "./plurals";

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

function isWithinMonths(month: string, filters: AnalyticsFilters): boolean {
  return (
    (!filters.fromMonth || month >= filters.fromMonth) &&
    (!filters.toMonth || month <= filters.toMonth)
  );
}

function isInSelectedWards(ward: string | null, filters: AnalyticsFilters): boolean {
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
// Term explorer

/** Normalize user input the same way the backend tokenizer normalizes text. */
export function normalizeTermQuery(query: string): string {
  return query.toLowerCase().replace(/[‘’]/g, "'").trim().replace(/\s+/g, " ");
}

const indexedTermsByFold = new WeakMap<TermIndex, Map<string, string>>();

/** Map each folded term to the written form the index stores it under, built once per index. */
function indexedTermsByFoldedForm(index: TermIndex): Map<string, string> {
  let byFold = indexedTermsByFold.get(index);
  if (!byFold) {
    byFold = new Map(Object.keys(index.terms).map((term) => [foldTerm(term), term]));
    indexedTermsByFold.set(index, byFold);
  }
  return byFold;
}

/**
 * The index key for a query, or null. The backend merges singular and plural
 * forms under the most common written one, so "bike lane" finds "bike lanes".
 */
export function resolveIndexedTerm(index: TermIndex, query: string): string | null {
  const term = normalizeTermQuery(query);
  if (!term) return null;
  // Own keys only: "constructor" or "__proto__" must not resolve to Object.prototype members.
  if (Object.hasOwn(index.terms, term)) return term;
  return indexedTermsByFoldedForm(index).get(foldTerm(term)) ?? null;
}

/** Up to `limit` indexed terms that start with the query, most specific first; the query's own term is left out. */
export function suggestTerms(index: TermIndex, query: string, limit: number): string[] {
  const normalized = normalizeTermQuery(query);
  if (!normalized) return [];
  const queriedTerm = resolveIndexedTerm(index, normalized);
  return Object.keys(index.terms)
    .filter((term) => term.startsWith(normalized) && term !== queriedTerm)
    .sort((a, b) => a.length - b.length || a.localeCompare(b))
    .slice(0, limit);
}

export interface TermBucketCount {
  sourceId: number;
  ward: string | null;
  month: string;
  newsletters: number;
}

/** Expand a term's postings into bucket counts restricted to the ward/date filters. */
export function expandTermPostings(
  index: TermIndex,
  postings: number[],
  wardBySource: Map<number, string | null>,
  filters: AnalyticsFilters,
): TermBucketCount[] {
  const counts: TermBucketCount[] = [];
  for (let position = 0; position < postings.length; position += 2) {
    const [sourceId, monthIndex] = index.buckets[postings[position]];
    const ward = wardBySource.get(sourceId) ?? null;
    const month = index.months[monthIndex];
    if (isInSelectedWards(ward, filters) && isWithinMonths(month, filters)) {
      counts.push({ sourceId, ward, month, newsletters: postings[position + 1] });
    }
  }
  return counts;
}

export interface TermMonthPoint {
  month: string;
  mentions: number;
  newsletters: number;
  share: number | null;
}

/**
 * Newsletters mentioning a term per month, as a share of all newsletters that
 * month (null for sparse months). `scopeFacts` must be filtered by ward and
 * date only, matching the term index (which cannot be filtered by lens).
 */
export function termMentionsByMonth(
  bucketCounts: TermBucketCount[],
  scopeFacts: NewsletterFact[],
  minMonthNewsletters: number = MIN_MONTH_NEWSLETTERS_FOR_SHARES,
): TermMonthPoint[] {
  const totals = countBy(scopeFacts, (fact) => monthOf(fact.date));
  const mentions = new Map<string, number>();
  for (const bucket of bucketCounts) {
    mentions.set(bucket.month, (mentions.get(bucket.month) ?? 0) + bucket.newsletters);
  }
  const months = [...totals.keys()].sort();
  if (months.length === 0) return [];
  return listMonths(months[0], months[months.length - 1]).map((month) => {
    const newsletters = totals.get(month) ?? 0;
    const mentionCount = mentions.get(month) ?? 0;
    return {
      month,
      mentions: mentionCount,
      newsletters,
      share: shareOrNull(mentionCount, newsletters, minMonthNewsletters),
    };
  });
}

export interface TermWardRow {
  ward: string;
  mentions: number;
  newsletters: number;
  share: number;
}

/** Wards ranked by how many of their newsletters mention the term. */
export function termMentionsByWard(
  bucketCounts: TermBucketCount[],
  scopeFacts: NewsletterFact[],
): TermWardRow[] {
  const totals = countBy(
    scopeFacts.filter((fact) => fact.ward !== null),
    (fact) => fact.ward as string,
  );
  const mentions = new Map<string, number>();
  for (const bucket of bucketCounts) {
    if (bucket.ward !== null) {
      mentions.set(bucket.ward, (mentions.get(bucket.ward) ?? 0) + bucket.newsletters);
    }
  }
  return [...mentions.entries()]
    .map(([ward, mentionCount]) => {
      const newsletters = totals.get(ward) ?? 0;
      return {
        ward,
        mentions: mentionCount,
        newsletters,
        share: newsletters ? mentionCount / newsletters : 0,
      };
    })
    .sort((a, b) => b.mentions - a.mentions || compareWards(a.ward, b.ward));
}

// ---------------------------------------------------------------------------
// Lens ward reach

/**
 * City-wide ward-reach months with fewer wards sending readable newsletters
 * than this are faded: a share of a dozen wards says little about the city.
 */
export const MIN_ACTIVE_WARDS_FOR_REACH = 20;

export interface LensReachCell {
  lens: string;
  month: string;
  /** Wards with at least one newsletter mentioning the lens that month. */
  wardsMentioning: number;
  /** Wards with at least one readable newsletter that month (the denominator). */
  activeWards: number;
  /** wardsMentioning / activeWards, or null when no ward was active. */
  share: number | null;
}

/** Readable newsletters can mention a lens; image-only ones cannot be read for any. */
export function isReadable(fact: NewsletterFact): boolean {
  return !fact.text_unavailable;
}

interface WardMonthActivity {
  readableWards: Set<string>;
  wardsByLens: Map<string, Set<string>>;
}

function groupWardActivityByMonth(facts: NewsletterFact[]): Map<string, WardMonthActivity> {
  const byMonth = new Map<string, WardMonthActivity>();
  for (const fact of facts) {
    if (fact.ward === null) continue;
    const month = monthOf(fact.date);
    let activity = byMonth.get(month);
    if (!activity) {
      activity = { readableWards: new Set(), wardsByLens: new Map() };
      byMonth.set(month, activity);
    }
    if (!isReadable(fact)) continue;
    activity.readableWards.add(fact.ward);
    for (const lens of fact.lenses) {
      const wards = activity.wardsByLens.get(lens) ?? new Set<string>();
      wards.add(fact.ward);
      activity.wardsByLens.set(lens, wards);
    }
  }
  return byMonth;
}

/**
 * For each lens and month: how many wards mentioned the lens, out of the wards
 * with at least one readable newsletter that month. Wards whose newsletters
 * that month were all image-only are left out of the denominator, since they
 * could not be seen mentioning anything.
 * `facts` should be filtered by ward and date, never by lens.
 */
export function computeLensWardReach(
  facts: NewsletterFact[],
  lensIds: string[],
  months: string[],
): LensReachCell[] {
  const byMonth = groupWardActivityByMonth(facts);
  return lensIds.flatMap((lens) =>
    months.map((month) => {
      const activity = byMonth.get(month);
      const activeWards = activity?.readableWards.size ?? 0;
      const wardsMentioning = activity?.wardsByLens.get(lens)?.size ?? 0;
      return {
        lens,
        month,
        wardsMentioning,
        activeWards,
        share: activeWards > 0 ? wardsMentioning / activeWards : null,
      };
    }),
  );
}

/** Whether a reach cell rests on too few wards to describe the city (always false when the threshold is 0). */
export function isReachFaded(cell: Pick<LensReachCell, "activeWards">, minActiveWards: number): boolean {
  return cell.activeWards < minActiveWards;
}

export type LensWardStatus = "mentioned" | "not_mentioned" | "no_newsletter";

export interface LensWardCell {
  ward: string;
  month: string;
  status: LensWardStatus;
  /** Newsletters that month mentioning the lens. */
  mentioning: number;
  /** All newsletters that month. */
  newsletters: number;
}

/**
 * One cell per ward per month for a single lens: did the ward's newsletters
 * mention it, not mention it, or not arrive at all. Newsletters without
 * readable text cannot mention a lens, so a month of only those is "not
 * mentioned".
 */
export function buildLensWardGrid(
  facts: NewsletterFact[],
  lens: string,
  wards: string[],
  months: string[],
): LensWardCell[] {
  const counts = new Map<string, { mentioning: number; newsletters: number }>();
  for (const fact of facts) {
    if (fact.ward === null) continue;
    const key = `${fact.ward}|${monthOf(fact.date)}`;
    const count = counts.get(key) ?? { mentioning: 0, newsletters: 0 };
    count.newsletters += 1;
    if (isReadable(fact) && fact.lenses.includes(lens)) count.mentioning += 1;
    counts.set(key, count);
  }
  return wards.flatMap((ward) =>
    months.map((month) => {
      const count = counts.get(`${ward}|${month}`) ?? { mentioning: 0, newsletters: 0 };
      const status: LensWardStatus =
        count.mentioning > 0 ? "mentioned" : count.newsletters > 0 ? "not_mentioned" : "no_newsletter";
      return { ward, month, status, ...count };
    }),
  );
}

// ---------------------------------------------------------------------------
// Coverage and cadence

export interface WardMonthCount {
  ward: string;
  month: string;
  newsletters: number;
}

export function countNewslettersByWardMonth(facts: NewsletterFact[]): WardMonthCount[] {
  const counts = countBy(
    facts.filter((fact) => fact.ward !== null),
    (fact) => `${fact.ward}|${monthOf(fact.date)}`,
  );
  return [...counts.entries()]
    .map(([key, newsletters]) => {
      const [ward, month] = key.split("|");
      return { ward, month, newsletters };
    })
    .sort((a, b) => compareWards(a.ward, b.ward) || a.month.localeCompare(b.month));
}

export interface SendingGap {
  sourceId: number;
  alder: string | null;
  ward: string | null;
  from: string;
  to: string;
  days: number;
}

/** The longest stretches between consecutive newsletters from the same source. */
export function findLongestGaps(facts: NewsletterFact[], limit: number): SendingGap[] {
  const factsBySource = groupBy(
    facts.filter((fact) => fact.source_id !== null),
    (fact) => fact.source_id as number,
  );
  const gaps: SendingGap[] = [];
  for (const [sourceId, sourceFacts] of factsBySource) {
    const ordered = [...sourceFacts].sort((a, b) => a.date.localeCompare(b.date));
    for (let index = 1; index < ordered.length; index += 1) {
      const previous = ordered[index - 1];
      const current = ordered[index];
      gaps.push({
        sourceId,
        alder: current.alder,
        ward: current.ward,
        from: previous.date,
        to: current.date,
        days: daysBetween(previous.date, current.date),
      });
    }
  }
  return gaps.sort((a, b) => b.days - a.days || a.from.localeCompare(b.from)).slice(0, limit);
}

export type CoverageStatus = "untracked" | "silent" | "received";

export interface CoverageCell {
  ward: string;
  month: string;
  /**
   * untracked: before the ward's first archived newsletter (or none ever);
   * silent: tracked, but nothing received that month; received: newsletters > 0.
   */
  status: CoverageStatus;
  newsletters: number;
}

/**
 * One cell per ward per month. A ward counts as tracked from the month of its
 * first archived newsletter, so `allFacts` must not be date-filtered; only the
 * listed months are returned.
 */
export function buildCoverageGrid(
  allFacts: NewsletterFact[],
  wards: string[],
  months: string[],
): CoverageCell[] {
  const counts = new Map(
    countNewslettersByWardMonth(allFacts).map((count) => [`${count.ward}|${count.month}`, count.newsletters]),
  );
  const firstMonthByWard = new Map<string, string>();
  for (const fact of allFacts) {
    if (fact.ward === null) continue;
    const month = monthOf(fact.date);
    const first = firstMonthByWard.get(fact.ward);
    if (!first || month < first) firstMonthByWard.set(fact.ward, month);
  }
  return wards.flatMap((ward) =>
    months.map((month) => {
      const newsletters = counts.get(`${ward}|${month}`) ?? 0;
      const firstMonth = firstMonthByWard.get(ward);
      const status: CoverageStatus =
        newsletters > 0 ? "received" : firstMonth && month >= firstMonth ? "silent" : "untracked";
      return { ward, month, status, newsletters };
    }),
  );
}

export interface WardCoverage {
  ward: string;
  aldermen: string[];
  firstDate: string | null;
  lastDate: string | null;
  /** Newsletters in the whole archive. */
  newsletters: number;
}

/** Archive coverage for every listed ward, merging wards served by several sources. */
export function summarizeWardCoverage(sources: SourceCoverage[], wards: string[]): WardCoverage[] {
  const sourcesByWard = groupBy(
    sources.filter((source) => source.ward !== null),
    (source) => source.ward as string,
  );
  return wards.map((ward) => {
    const wardSources = sourcesByWard.get(ward) ?? [];
    const firstDates = wardSources.flatMap((source) => (source.first_date ? [source.first_date] : [])).sort();
    const lastDates = wardSources.flatMap((source) => (source.last_date ? [source.last_date] : [])).sort();
    return {
      ward,
      aldermen: wardSources.map((source) => source.name),
      firstDate: firstDates[0] ?? null,
      lastDate: lastDates.at(-1) ?? null,
      newsletters: wardSources.reduce((total, source) => total + source.newsletters, 0),
    };
  });
}

// ---------------------------------------------------------------------------
// Links

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
