// Pure aggregation logic for the local /analytics dashboard.
// Data shapes mirror the JSON written by backend/utils/compute_analytics.py.

export interface NewsletterFact {
  id: string;
  date: string; // YYYY-MM-DD, Chicago time
  source_id: number | null;
  ward: string | null;
  alder: string | null;
  topics: string[] | null; // null = not yet processed by the LLM
  relevance: number | null;
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
  minRelevance: number; // 0 = no relevance filter
}

export const EMPTY_FILTERS: AnalyticsFilters = {
  wards: [],
  topic: null,
  fromMonth: null,
  toMonth: null,
  minRelevance: 0,
};

/** Wards with fewer processed newsletters than this are left out of share comparisons. */
export const MIN_WARD_NEWSLETTERS_FOR_SHARES = 5;

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
      (filters.minRelevance <= 0 ||
        (fact.relevance !== null && fact.relevance >= filters.minRelevance)) &&
      (options.ignoreTopic || !filters.topic || (fact.topics ?? []).includes(filters.topic)),
  );
}

export interface FactSummary {
  newsletters: number;
  activeSources: number;
  firstDate: string | null;
  lastDate: string | null;
  averageRelevance: number | null;
  scoredNewsletters: number;
}

export function summarizeFacts(facts: NewsletterFact[]): FactSummary {
  const dates = facts.map((fact) => fact.date).sort();
  const scores = facts.flatMap((fact) => (fact.relevance === null ? [] : [fact.relevance]));
  return {
    newsletters: facts.length,
    activeSources: new Set(facts.map((fact) => fact.source_id)).size,
    firstDate: dates[0] ?? null,
    lastDate: dates.at(-1) ?? null,
    averageRelevance: scores.length
      ? scores.reduce((total, score) => total + score, 0) / scores.length
      : null,
    scoredNewsletters: scores.length,
  };
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

export function lookupTermPostings(index: TermIndex, query: string): number[] | null {
  return index.terms[normalizeTermQuery(query)] ?? null;
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
 * date only, matching the term index (which cannot be filtered by topic or
 * relevance).
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

export interface WardTopicCell {
  ward: string;
  topic: string;
  wardTopicNewsletters: number;
  wardNewsletters: number;
  wardShare: number;
  cityShare: number;
  /** log2(ward share / city share): +1 = twice the city rate, -1 = half. */
  logRatio: number;
}

/**
 * Each ward's share of newsletters mentioning each topic, relative to the
 * city-wide share. `wardFacts` supplies the ward rows (e.g. the selected
 * wards); `cityFacts` supplies the baseline, normally the same filters minus
 * the ward filter so "city average" always means the whole city. Only
 * LLM-processed newsletters count, and wards below minWardNewsletters are
 * omitted as too noisy. Shares are smoothed by half a newsletter so zero
 * counts stay finite.
 */
export function computeWardTopicCells(
  wardFacts: NewsletterFact[],
  cityFacts: NewsletterFact[],
  topics: string[],
  minWardNewsletters: number = MIN_WARD_NEWSLETTERS_FOR_SHARES,
): WardTopicCell[] {
  const cityProcessed = processedFacts(cityFacts);
  const cityTotal = cityProcessed.length;
  if (cityTotal === 0) return [];
  const cityTopicCounts = countTopics(cityProcessed);
  const factsByWard = groupBy(
    processedFacts(wardFacts).filter((fact) => fact.ward !== null),
    (fact) => fact.ward as string,
  );
  const smoothing = 0.5;

  return [...factsByWard.entries()]
    .filter(([, factsInWard]) => factsInWard.length >= minWardNewsletters)
    .sort(([a], [b]) => compareWards(a, b))
    .flatMap(([ward, factsInWard]) => {
      const wardTopicCounts = countTopics(factsInWard);
      return topics.map((topic) => {
        const wardTopicNewsletters = wardTopicCounts.get(topic) ?? 0;
        const cityTopicNewsletters = cityTopicCounts.get(topic) ?? 0;
        const smoothedWardShare =
          (wardTopicNewsletters + smoothing) / (factsInWard.length + 2 * smoothing);
        const smoothedCityShare =
          (cityTopicNewsletters + smoothing) / (cityTotal + 2 * smoothing);
        return {
          ward,
          topic,
          wardTopicNewsletters,
          wardNewsletters: factsInWard.length,
          wardShare: wardTopicNewsletters / factsInWard.length,
          cityShare: cityTopicNewsletters / cityTotal,
          logRatio: Math.log2(smoothedWardShare / smoothedCityShare),
        };
      });
    });
}

export interface TopicMonthPoint {
  month: string;
  topic: string;
  newsletters: number;
  monthNewsletters: number;
  share: number | null;
}

/**
 * Share of processed newsletters mentioning each topic, per month. Every month
 * in the span is listed; sparse months get a null share.
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
        share: shareOrNull(newsletters, monthFacts.length, minMonthNewsletters),
      };
    });
  });
}

// ---------------------------------------------------------------------------
// Cadence, relevance, coverage

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

export interface WardRelevance {
  ward: string;
  averageRelevance: number;
  scoredNewsletters: number;
}

export function computeRelevanceByWard(facts: NewsletterFact[]): WardRelevance[] {
  const scored = facts.filter((fact) => fact.ward !== null && fact.relevance !== null);
  return [...groupBy(scored, (fact) => fact.ward as string).entries()]
    .map(([ward, wardFacts]) => ({
      ward,
      averageRelevance:
        wardFacts.reduce((total, fact) => total + (fact.relevance as number), 0) /
        wardFacts.length,
      scoredNewsletters: wardFacts.length,
    }))
    .sort((a, b) => b.averageRelevance - a.averageRelevance || compareWards(a.ward, b.ward));
}

/** Sources with newsletters, limited to the selected wards, earliest first. */
export function selectCoverage(
  sources: SourceCoverage[],
  filters: AnalyticsFilters,
): SourceCoverage[] {
  return sources
    .filter((source) => source.newsletters > 0 && isInSelectedWards(source.ward, filters))
    .sort(
      (a, b) =>
        (a.first_date ?? "").localeCompare(b.first_date ?? "") || a.name.localeCompare(b.name),
    );
}

// ---------------------------------------------------------------------------
// Links

/** Link to the search page; multi-word terms are quoted as a phrase. */
export function buildSearchUrl(params: { q?: string; ward?: string; topic?: string }): string {
  const search = new URLSearchParams();
  if (params.q) search.set("q", params.q.includes(" ") ? `"${params.q}"` : params.q);
  if (params.ward) search.set("ward", params.ward);
  if (params.topic) search.set("topic", params.topic);
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
