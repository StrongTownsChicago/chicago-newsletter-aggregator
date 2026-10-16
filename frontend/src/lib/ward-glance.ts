// Helpers for the ward page summary. Data: src/generated/ward-glance.json, from
// backend/analytics/ward_glance.py.

import { formatLongMonth, formatMonthRange } from "./archive-months";

export interface WardGlanceTopic {
  id: string;
  /** This ward's readable newsletters in the window that mention the topic. */
  newsletters: number;
  /** Wards that mentioned the topic in the latest month. */
  city_wards: number;
}

export interface WardGlance {
  first_date: string;
  last_date: string;
  newsletters: number;
  /** Newsletters per window month; null before the ward's first archived newsletter. */
  recent_months: (number | null)[];
  per_month: number | null;
  /** Readable newsletters in the window: the denominator for topic shares. */
  topic_newsletters: number;
  topics: WardGlanceTopic[];
}

export interface WardGlanceFile {
  data_through: string | null;
  topics: Record<string, string>;
  /** Topic shares are shown as percentages only with at least this many newsletters. */
  min_share_newsletters: number;
  latest_month: string | null;
  window_months: string[];
  /** Wards with a readable newsletter in the latest month: the city reach denominator. */
  city_readable_wards: number;
  wards: Record<string, WardGlance>;
}

/** The ward's summary, or null when the archive has no newsletters from it. */
export function findWardGlance(file: WardGlanceFile, wardNumber: number): WardGlance | null {
  return file.wards[String(wardNumber)] ?? null;
}

export interface WardMonthCount {
  month: string;
  /** null when the month is before the ward's first newsletter in the archive. */
  newsletters: number | null;
}

/** Pairs each window month with the ward's newsletter count. */
export function listWardMonthCounts(file: WardGlanceFile, glance: WardGlance): WardMonthCount[] {
  return file.window_months.map((month, index) => ({
    month,
    newsletters: glance.recent_months[index] ?? null,
  }));
}

/** The window months in which the ward was in the archive. */
export function listTrackedMonths(counts: WardMonthCount[]): string[] {
  return counts.filter((count) => count.newsletters !== null).map((count) => count.month);
}

const perMonthFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

/** "4.7 newsletters a month", or null when there is nothing to average. */
export function describeCadence(glance: WardGlance): string | null {
  if (glance.per_month === null || glance.per_month === 0) {
    return null;
  }
  const amount = perMonthFormat.format(glance.per_month);
  return `${amount} newsletter${amount === "1" ? "" : "s"} a month`;
}

/** "April to September 2026" for the window months the ward was in the archive. */
export function describeTrackedPeriod(trackedMonths: string[]): string | null {
  if (trackedMonths.length === 0) {
    return null;
  }
  return formatMonthRange(trackedMonths[0], trackedMonths[trackedMonths.length - 1]);
}

export interface TopicShare {
  /** Whole-number percentage, or null when too few newsletters to quote one. */
  percent: number | null;
  /** Bar width as a fraction of the full track (0 to 1). */
  fraction: number;
  /** "23 of 28 newsletters" */
  countLabel: string;
}

/** Describes how many of the ward's own newsletters mentioned a topic. */
export function describeTopicShare(
  count: number,
  total: number,
  minShareNewsletters: number,
): TopicShare {
  const fraction = total > 0 ? count / total : 0;
  return {
    percent: total >= minShareNewsletters ? Math.round(fraction * 100) : null,
    fraction,
    countLabel: `${count} of ${total} newsletter${total === 1 ? "" : "s"}`,
  };
}

/** "Citywide: 25 of 37 wards in September 2026", or null without a latest month. */
export function describeCityReach(file: WardGlanceFile, topic: WardGlanceTopic): string | null {
  if (!file.latest_month || file.city_readable_wards === 0) {
    return null;
  }
  const wards = file.city_readable_wards === 1 ? "ward" : "wards";
  return `Citywide: ${topic.city_wards} of ${file.city_readable_wards} ${wards} in ${formatLongMonth(file.latest_month)}`;
}
