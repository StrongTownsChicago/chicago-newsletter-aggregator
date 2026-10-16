// Archive coverage and sending cadence: which wards sent newsletters when, and the gaps between them.
import {
  compareWards,
  countBy,
  daysBetween,
  groupBy,
  monthOf,
  type NewsletterFact,
  type SourceCoverage,
} from "./analytics";

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
