// Pure aggregation logic for the local /analytics dashboard.
// Data shapes mirror the JSON written by backend/utils/compute_analytics.py.

export interface NewsletterFact {
  id: string;
  date: string; // YYYY-MM-DD, Chicago time
  source_id: number | null;
  ward: string | null;
  alder: string | null;
  topics: string[] | null; // null = not yet processed by the LLM
  words: number;
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
}

export interface RisingTerm {
  term: string;
  ratio: number;
  latest_newsletters: number;
  latest_sources: number;
  latest_share: number;
  baseline_newsletters: number;
  baseline_share: number;
}

export interface RisingTerms {
  latest_month: string | null;
  baseline_months: string[];
  latest_newsletters: number;
  baseline_newsletters: number;
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

export interface AnalyticsDataset {
  metadata: AnalyticsMetadata;
  newsletters: NewsletterFact[];
  sources: SourceCoverage[];
  terms: TermIndex;
  distinctiveByWard: Record<string, DistinctiveTerm[]>;
  rising: RisingTerms;
}

export interface AnalyticsFilters {
  wards: string[]; // empty = all wards
  topic: string | null;
  fromMonth: string | null; // YYYY-MM inclusive
  toMonth: string | null; // YYYY-MM inclusive
}

export const EMPTY_FILTERS: AnalyticsFilters = {
  wards: [],
  topic: null,
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

export function listTopics(facts: NewsletterFact[]): string[] {
  return [...new Set(facts.flatMap((fact) => fact.topics ?? []))].sort();
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
 * Apply the global filters. Panels that compare topics pass ignoreTopic so a
 * topic filter does not trivially make that topic 100% of everything.
 */
export function filterFacts(
  facts: NewsletterFact[],
  filters: AnalyticsFilters,
  options: { ignoreTopic?: boolean } = {},
): NewsletterFact[] {
  return facts.filter(
    (fact) =>
      isInSelectedWards(fact.ward, filters) &&
      isWithinMonths(monthOf(fact.date), filters) &&
      (options.ignoreTopic || !filters.topic || (fact.topics ?? []).includes(filters.topic)),
  );
}

export interface FactSummary {
  newsletters: number;
  firstDate: string | null;
  lastDate: string | null;
}

export function summarizeFacts(facts: NewsletterFact[]): FactSummary {
  const dates = facts.map((fact) => fact.date).sort();
  return {
    newsletters: facts.length,
    firstDate: dates[0] ?? null,
    lastDate: dates.at(-1) ?? null,
  };
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
  /** Fewest and most wards active in any month before the window. */
  minActiveWardsBefore: number;
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
  const activeWardsBefore = activity.slice(0, startIndex).map((month) => month.activeWards);
  return {
    startMonth: activity[startIndex].month,
    endMonth: activity[activity.length - 1].month,
    minActiveWards,
    peakActiveWards,
    minActiveWardsBefore: Math.min(...activeWardsBefore),
    maxActiveWardsBefore: Math.max(...activeWardsBefore),
    months: activity.length - startIndex,
  };
}

/** How many of the listed months had at least `minActiveWards` wards sending. */
export function countBroadlyCoveredMonths(
  months: string[],
  activity: MonthWardActivity[],
  minActiveWards: number,
): number {
  const activeWardsByMonth = new Map(activity.map((month) => [month.month, month.activeWards]));
  return months.filter((month) => (activeWardsByMonth.get(month) ?? 0) >= minActiveWards).length;
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

/**
 * The months from the first to the last point with a share in any series, so
 * small multiples share one x axis instead of each starting where its own
 * data does.
 */
export function listMonthsWithShares(points: { month: string; share: number | null }[]): string[] {
  const months = points
    .filter((point) => point.share !== null)
    .map((point) => point.month)
    .sort();
  return months.length ? listMonths(months[0], months[months.length - 1]) : [];
}

// ---------------------------------------------------------------------------
// Term explorer

/** Normalize user input the same way the backend tokenizer normalizes text. */
export function normalizeTermQuery(query: string): string {
  return query.toLowerCase().replace(/[‘’]/g, "'").trim().replace(/\s+/g, " ");
}

export function lookupTermPostings(index: TermIndex, query: string): number[] | null {
  const term = normalizeTermQuery(query);
  // Own keys only: "constructor" or "__proto__" must not resolve to Object.prototype members.
  return Object.hasOwn(index.terms, term) ? index.terms[term] : null;
}

/** Up to `limit` indexed terms that start with the query, most specific first. */
export function suggestTerms(index: TermIndex, query: string, limit: number): string[] {
  const normalized = normalizeTermQuery(query);
  if (!normalized) return [];
  return Object.keys(index.terms)
    .filter((term) => term.startsWith(normalized) && term !== normalized)
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
 * date only, matching the term index (which cannot be filtered by topic).
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
// Topics

function processedFacts(facts: NewsletterFact[]): NewsletterFact[] {
  return facts.filter((fact) => fact.topics !== null);
}

export interface TopicMonthPoint {
  month: string;
  topic: string;
  newsletters: number;
  monthNewsletters: number;
  share: number | null;
}

/**
 * First complete month labeled with `street_safety_or_traffic_calming`, which
 * joined the LLM topic list on 2026-01-31 (commit c574312) without a backfill.
 */
export const STREET_SAFETY_LABELING_START_MONTH = "2026-02";

/**
 * Topics added to the LLM taxonomy after labeling began, mapped to the first
 * complete month labeled with them. Earlier newsletters were never re-labeled,
 * so their months would show a false 0%. Add an entry (with its own named
 * constant) whenever a topic joins backend/processing/llm_processor.py:TOPICS
 * without a backfill.
 */
export const TOPIC_LABELING_START_MONTH: Readonly<Record<string, string>> = {
  street_safety_or_traffic_calming: STREET_SAFETY_LABELING_START_MONTH,
};

/** Whether newsletters from this month could have been labeled with the topic. */
export function isTopicLabeledInMonth(topic: string, month: string): boolean {
  return !Object.hasOwn(TOPIC_LABELING_START_MONTH, topic) || month >= TOPIC_LABELING_START_MONTH[topic];
}

/**
 * Share of processed newsletters mentioning each topic, per month. Every month
 * in the span is listed; sparse months, and months before a topic entered the
 * taxonomy, get a null share.
 */
export function computeTopicTrends(
  facts: NewsletterFact[],
  topics: string[],
  minMonthNewsletters: number = MIN_MONTH_NEWSLETTERS_FOR_SHARES,
): TopicMonthPoint[] {
  const factsByMonth = groupBy(processedFacts(facts), (fact) => monthOf(fact.date));
  const months = [...factsByMonth.keys()].sort();
  if (months.length === 0) return [];
  return listMonths(months[0], months[months.length - 1]).flatMap((month) => {
    const monthFacts = factsByMonth.get(month) ?? [];
    const topicCounts = countTopics(monthFacts);
    return topics.map((topic) => {
      const newsletters = topicCounts.get(topic) ?? 0;
      return {
        month,
        topic,
        newsletters,
        monthNewsletters: monthFacts.length,
        share: isTopicLabeledInMonth(topic, month)
          ? shareOrNull(newsletters, monthFacts.length, minMonthNewsletters)
          : null,
      };
    });
  });
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
  topic?: string;
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
 * The global filters as search link parameters, so a click-through lists the
 * same newsletters the chart counted. Panels whose data ignores the topic
 * filter (the term index, the coverage grid) opt out.
 */
export function searchScopeForFilters(
  filters: AnalyticsFilters,
  options: { includeTopic: boolean },
): SearchLinkParams {
  const scope: SearchLinkParams = {};
  if (filters.fromMonth) scope.fromDate = monthDateRange(filters.fromMonth).fromDate;
  if (filters.toMonth) scope.toDate = monthDateRange(filters.toMonth).toDate;
  if (options.includeTopic && filters.topic) scope.topic = filters.topic;
  return scope;
}

/** Link to the search page; multi-word terms are quoted as a phrase. */
export function buildSearchUrl(params: SearchLinkParams): string {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q.includes(" ") ? `"${params.q}"` : params.q);
  if (params.ward) search.set("ward", params.ward);
  if (params.topic) search.set("topic", params.topic);
  if (params.fromDate) search.set("from", params.fromDate);
  if (params.toDate) search.set("to", params.toDate);
  const query = search.toString();
  return query ? `/search?${query}` : "/search";
}

// ---------------------------------------------------------------------------
// Helpers

function countBy<T, K>(items: T[], keyOf: (item: T) => K): Map<K, number> {
  const counts = new Map<K, number>();
  for (const item of items) {
    const key = keyOf(item);
    counts.set(key, (counts.get(key) ?? 0) + 1);
  }
  return counts;
}

function groupBy<T, K>(items: T[], keyOf: (item: T) => K): Map<K, T[]> {
  const groups = new Map<K, T[]>();
  for (const item of items) {
    const key = keyOf(item);
    const group = groups.get(key);
    if (group) group.push(item);
    else groups.set(key, [item]);
  }
  return groups;
}

function countTopics(facts: NewsletterFact[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const fact of facts) {
    for (const topic of new Set(fact.topics ?? [])) {
      counts.set(topic, (counts.get(topic) ?? 0) + 1);
    }
  }
  return counts;
}
