// Ward reach: how many wards' newsletters mention each topic (keyword lens) each month.
import { monthOf, type NewsletterFact } from "./core";

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
