// Term explorer: looks up a query in the term index and counts its mentions by month and ward.
import {
  compareWards,
  countBy,
  isInSelectedWards,
  isWithinMonths,
  listMonths,
  MIN_MONTH_NEWSLETTERS_FOR_SHARES,
  monthOf,
  shareOrNull,
  type AnalyticsFilters,
  type NewsletterFact,
  type TermIndex,
} from "./core";
import { foldTerm } from "./plurals";

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
