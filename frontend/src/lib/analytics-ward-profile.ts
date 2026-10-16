// Pure logic for the /analytics ward profile: one ward's archived newsletters
// described against its own history and against all active wards. Nothing here
// ranks wards; the city figures are reference points, not a leaderboard.
import {
  daysBetween,
  groupBy,
  median,
  monthOf,
  type NewsletterFact,
  type SourceCoverage,
} from "./analytics";
import { buildCoverageGrid, summarizeWardCoverage, type CoverageCell } from "./analytics-coverage";
import {
  buildLensWardGrid,
  computeLensWardReach,
  isReadable,
  type LensWardStatus,
} from "./analytics-reach";

/** A ward needs at least this many newsletters in the window before its topic shares are shown. */
export const MIN_WARD_NEWSLETTERS_FOR_SHARES = 20;
/** ...and newsletters in at least this many months, so one busy month cannot stand for a habit. */
export const MIN_WARD_MONTHS_FOR_SHARES = 3;

export interface WardTopicMonthCell {
  lens: string;
  month: string;
  status: LensWardStatus;
  /** The ward's newsletters that month mentioning the topic. */
  mentioning: number;
  /** All of the ward's newsletters that month. */
  newsletters: number;
  /** mentioning / newsletters, or null with no newsletters. */
  share: number | null;
}

export interface WardTopicSummary {
  lens: string;
  /** Months in the window in which at least one of the ward's newsletters mentioned the topic. */
  monthsMentioning: number;
  /** Months in the window in which the ward's newsletters could be checked for topics. */
  monthsChecked: number;
  newslettersMentioning: number;
  /** monthsMentioning / monthsChecked, or null when the ward has too few newsletters for shares. */
  wardShare: number | null;
  /**
   * The average share of active wards mentioning the topic, over the same
   * months: the city-wide reference for wardShare. Null with wardShare.
   */
  cityShare: number | null;
}

export interface WardCadence {
  /**
   * Median newsletters per tracked month (from the ward's first archived
   * newsletter, or the window start, to the window end), counting months with none as zero.
   */
  medianPerTrackedMonth: number | null;
  /** Median days between consecutive newsletters, or null with fewer than two. */
  medianDaysBetween: number | null;
}

export interface WardProfile {
  ward: string;
  aldermen: string[];
  /** First and latest archived newsletter in the whole archive. */
  firstDate: string | null;
  lastDate: string | null;
  archiveNewsletters: number;
  windowNewsletters: number;
  /** One cell per window month: not tracked yet, tracked with none received, or a count. */
  months: CoverageCell[];
  cadence: WardCadence;
  /** The same measures over the ward's whole archive, for comparison with its own history. */
  archiveCadence: WardCadence;
  /** The median ward's newsletters per tracked month in the window, over wards with any tracked month. */
  cityMedianPerTrackedMonth: number | null;
  topicCells: WardTopicMonthCell[];
  topics: WardTopicSummary[];
  /** False when the ward has too few newsletters in the window for topic shares. */
  sharesShown: boolean;
}

function medianDaysBetween(dates: string[]): number | null {
  const ordered = [...dates].sort();
  const gaps = ordered.slice(1).map((date, index) => daysBetween(ordered[index], date));
  return median(gaps);
}

/** Cadence measures for one ward's coverage cells (already restricted to the months of interest). */
export function summarizeCadence(cells: CoverageCell[], dates: string[]): WardCadence {
  const tracked = cells.filter((cell) => cell.status !== "untracked");
  return {
    medianPerTrackedMonth: median(tracked.map((cell) => cell.newsletters)),
    medianDaysBetween: medianDaysBetween(dates),
  };
}

function isInMonths(fact: NewsletterFact, months: Set<string>): boolean {
  return months.has(monthOf(fact.date));
}

/** The median ward's newsletters per tracked month over the listed months. */
export function computeCityMedianPerTrackedMonth(allFacts: NewsletterFact[], months: string[]): number | null {
  const wards = [...groupBy(allFacts.filter((fact) => fact.ward !== null), (fact) => fact.ward as string).keys()];
  const cells = buildCoverageGrid(allFacts, wards, months);
  const perWard = [...groupBy(cells, (cell) => cell.ward).values()]
    .map((wardCells) => median(wardCells.filter((cell) => cell.status !== "untracked").map((cell) => cell.newsletters)))
    .filter((value): value is number => value !== null);
  return median(perWard);
}

function summarizeTopics(
  topicCells: WardTopicMonthCell[],
  cityFacts: NewsletterFact[],
  lensIds: string[],
  checkedMonths: string[],
  sharesShown: boolean,
): WardTopicSummary[] {
  const cityReach = computeLensWardReach(cityFacts, lensIds, checkedMonths);
  const checked = new Set(checkedMonths);
  return lensIds.map((lens) => {
    const cells = topicCells.filter((cell) => cell.lens === lens);
    const monthsMentioning = cells.filter((cell) => cell.status === "mentioned").length;
    const cityShares = cityReach
      .filter((cell) => cell.lens === lens && checked.has(cell.month))
      .flatMap((cell) => (cell.share === null ? [] : [cell.share]));
    const canShare = sharesShown && checkedMonths.length > 0 && cityShares.length > 0;
    return {
      lens,
      monthsMentioning,
      monthsChecked: checkedMonths.length,
      newslettersMentioning: cells.reduce((total, cell) => total + cell.mentioning, 0),
      wardShare: canShare ? monthsMentioning / checkedMonths.length : null,
      cityShare: canShare ? cityShares.reduce((total, share) => total + share, 0) / cityShares.length : null,
    };
  });
}

/**
 * Build one ward's profile for a date window.
 * `allFacts` is the whole archive (not filtered), `windowMonths` the months of
 * the selected window, and `archiveMonths` every month from the first to the
 * latest newsletter in the archive.
 */
export function buildWardProfile(
  allFacts: NewsletterFact[],
  sources: SourceCoverage[],
  ward: string,
  windowMonths: string[],
  archiveMonths: string[],
  lensIds: string[],
): WardProfile {
  const [coverage] = summarizeWardCoverage(sources, [ward]);
  const wardFacts = allFacts.filter((fact) => fact.ward === ward);
  const windowMonthSet = new Set(windowMonths);
  const windowFacts = wardFacts.filter((fact) => isInMonths(fact, windowMonthSet));
  const months = buildCoverageGrid(allFacts, [ward], windowMonths);
  const archiveCells = buildCoverageGrid(allFacts, [ward], archiveMonths);

  const topicCells = lensIds.flatMap((lens) =>
    buildLensWardGrid(windowFacts, lens, [ward], windowMonths).map(({ month, status, mentioning, newsletters }) => ({
      lens,
      month,
      status,
      mentioning,
      newsletters,
      share: newsletters ? mentioning / newsletters : null,
    })),
  );
  const readableFacts = windowFacts.filter(isReadable);
  const checkedMonths = windowMonths.filter((month) => readableFacts.some((fact) => monthOf(fact.date) === month));
  const sharesShown =
    readableFacts.length >= MIN_WARD_NEWSLETTERS_FOR_SHARES && checkedMonths.length >= MIN_WARD_MONTHS_FOR_SHARES;
  const cityFacts = allFacts.filter((fact) => isInMonths(fact, windowMonthSet));

  return {
    ward,
    aldermen: coverage.aldermen,
    firstDate: coverage.firstDate,
    lastDate: coverage.lastDate,
    archiveNewsletters: wardFacts.length,
    windowNewsletters: windowFacts.length,
    months,
    cadence: summarizeCadence(
      months,
      windowFacts.map((fact) => fact.date),
    ),
    archiveCadence: summarizeCadence(
      archiveCells,
      wardFacts.map((fact) => fact.date),
    ),
    cityMedianPerTrackedMonth: computeCityMedianPerTrackedMonth(allFacts, windowMonths),
    topicCells,
    topics: summarizeTopics(topicCells, cityFacts, lensIds, checkedMonths, sharesShown),
    sharesShown,
  };
}
