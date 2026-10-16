// Pure logic for the /analytics topic overview: each topic's ward reach
// against its own average, the civic calendar's row order, and the headline
// topics for the summary tiles.
import { formatMonth } from "./analytics";
import { isReachFaded, type LensReachCell } from "./analytics-reach";

/**
 * Sparklines and the topic trend use a y scale spanning at least this share
 * (5 points), so a near-flat topic doesn't look volatile.
 */
export const MIN_TREND_SPAN = 0.05;

const MONTH_PREFIX = /^(\d{4}-\d{2})-\d{2}/;

/**
 * The month the data was generated in (from `generated_at`, written in
 * Chicago time), or null when unreadable. Like the backend's rising terms,
 * months from this one on are still in progress.
 */
export function findAsOfMonth(generatedAt: string): string | null {
  return MONTH_PREFIX.exec(generatedAt)?.[1] ?? null;
}

/** Whether `month` was still in progress when the data was generated, so its counts are incomplete. */
export function isPartialMonth(month: string, asOfMonth: string | null): boolean {
  return asOfMonth !== null && month >= asOfMonth;
}

/** The window's months that had ended when the data was generated. */
export function listFullMonths(months: string[], asOfMonth: string | null): string[] {
  return months.filter((month) => !isPartialMonth(month, asOfMonth));
}

export interface TopicTrendPoint {
  month: string;
  /** Ward reach, or null when too few wards sent newsletters that month. */
  share: number | null;
}

export interface TopicTrend {
  lens: string;
  /** One point per full month. */
  points: TopicTrendPoint[];
  /** Mean ward reach over the points with a share. */
  averageShare: number | null;
  /**
   * Swing: the topic's highest minus lowest monthly ward reach. The civic
   * calendar lists topics by swing, so those that change most come first.
   */
  swing: number;
  /** The last full month's cell. */
  latest: LensReachCell | null;
  /** The last full month's reach minus the average. */
  latestChange: number | null;
}

function mean(values: number[]): number | null {
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : null;
}

/**
 * Each topic's ward reach over the full months, in `lensIds` order. Months
 * resting on fewer than `minActiveWards` wards have no share.
 */
export function summarizeTopicTrends(
  cells: LensReachCell[],
  lensIds: string[],
  fullMonths: string[],
  minActiveWards: number,
): TopicTrend[] {
  const cellByKey = new Map(cells.map((cell) => [`${cell.lens}|${cell.month}`, cell]));
  return lensIds.map((lens) => {
    const points = fullMonths.map((month) => {
      const cell = cellByKey.get(`${lens}|${month}`);
      const share = cell && !isReachFaded(cell, minActiveWards) ? cell.share : null;
      return { month, share };
    });
    const shares = points.flatMap((point) => (point.share === null ? [] : [point.share]));
    const averageShare = mean(shares);
    const lastMonth = fullMonths.at(-1);
    const latest = lastMonth ? (cellByKey.get(`${lens}|${lastMonth}`) ?? null) : null;
    const lastShare = points.at(-1)?.share ?? null;
    return {
      lens,
      points,
      averageShare,
      swing: shares.length ? Math.max(...shares) - Math.min(...shares) : 0,
      latest,
      latestChange: lastShare !== null && averageShare !== null ? lastShare - averageShare : null,
    };
  });
}

/** Topics by swing, largest first; ties keep their order. */
export function orderBySwing(trends: TopicTrend[]): TopicTrend[] {
  return [...trends].sort((a, b) => b.swing - a.swing);
}

function latestShare(trend: TopicTrend): number | null {
  return trend.points.at(-1)?.share ?? null;
}

/** The topic with the widest ward reach in the last full month, or null when that month has too few wards. */
export function findWidestReachTopic(trends: TopicTrend[]): TopicTrend | null {
  return trends.reduce<TopicTrend | null>((best, trend) => {
    const share = latestShare(trend);
    if (share === null) return best;
    return best === null || share > (latestShare(best) ?? 0) ? trend : best;
  }, null);
}

/** The topic whose last full month is furthest from its average, or null. */
export function findLargestChangeTopic(trends: TopicTrend[]): TopicTrend | null {
  return trends.reduce<TopicTrend | null>((best, trend) => {
    if (trend.latestChange === null) return best;
    return best === null || Math.abs(trend.latestChange) > Math.abs(best.latestChange ?? 0) ? trend : best;
  }, null);
}

/** The full month with the topic's widest ward reach (the latest on a tie), or null when no ward mentioned it. */
export function findPeakPoint(trend: TopicTrend): TopicTrendPoint | null {
  return trend.points.reduce<TopicTrendPoint | null>((best, point) => {
    if (!point.share) return best;
    return best === null || point.share >= (best.share ?? 0) ? point : best;
  }, null);
}

/** A cell's ward reach minus its topic's average, or null when either is missing. */
export function reachDeviation(cell: Pick<LensReachCell, "share">, averageShare: number | null): number | null {
  return cell.share === null || averageShare === null ? null : cell.share - averageShare;
}

/** A y domain hugging the shares, at least `minSpan` wide and within 0–1. */
export function tightShareDomain(shares: number[], minSpan: number = MIN_TREND_SPAN): [number, number] {
  if (shares.length === 0) return [0, minSpan];
  const low = Math.min(...shares);
  const high = Math.max(...shares);
  const span = Math.max(minSpan, high - low);
  const start = Math.min(Math.max(0, (low + high - span) / 2), 1 - span);
  return [start, start + span];
}

/** Text alternative for a sparkline: "Public safety, Feb 2026 – Apr 2026: 74%, 69%, no data." */
export function describeSparkline(label: string, points: TopicTrendPoint[]): string {
  if (points.length === 0) return `${label}: no full months.`;
  const values = points.map((point) => (point.share === null ? "no data" : `${Math.round(point.share * 100)}%`));
  const span = `${formatMonth(points[0].month)} – ${formatMonth(points[points.length - 1].month)}`;
  return `${label}, ${span}: ${values.join(", ")}.`;
}

/** "12 pts", "1 pt": a difference in ward reach, in percentage points, without a sign. */
export function formatPoints(difference: number): string {
  const points = Math.abs(Math.round(difference * 100));
  return `${points} ${points === 1 ? "pt" : "pts"}`;
}

/** "+6 pts", "−1 pt", "0 pts": a change in ward reach, in percentage points. */
export function formatPointChange(change: number): string {
  const points = Math.round(change * 100);
  const sign = points > 0 ? "+" : points < 0 ? "−" : "";
  return `${sign}${formatPoints(change)}`;
}
