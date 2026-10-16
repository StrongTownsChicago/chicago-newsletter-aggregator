// Dashboard text built from the data and its rules, so labels and numbers cannot drift.
import {
  daysBetween,
  formatMonth,
  type AnalyticsFilters,
  type BroadCoverageWindow,
  type LensDefinition,
  type LensSummary,
} from "./analytics";
import { formatWard } from "./analytics-format";

const numberFormat = new Intl.NumberFormat("en-US");
const sharePercentFormat = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 });

export function pluralize(count: number, noun: string): string {
  return `${numberFormat.format(count)} ${noun}${count === 1 ? "" : "s"}`;
}

/** "at least 34 wards sent newsletters". */
export function describeBroadCoverageRule(window: BroadCoverageWindow): string {
  return `at least ${window.minActiveWards} wards sent newsletters`;
}

/** How a newsletter is found to mention a topic, from the rules recorded with the data. */
export function describeTopicMatching(summary: Pick<LensSummary, "text" | "min_mentions">): string {
  return (
    `A newsletter mentions a topic when the topic's phrases appear ${pluralize(summary.min_mentions, "separate time")} or more ` +
    "(whole words, any case, singular or plural; overlapping phrases count once)." +
    (summary.text === "cleaned" ? " Text a ward repeats in many issues, like footers, is skipped." : "")
  );
}

export interface TopicDefinitionText {
  title: string;
  body: string;
}

/** One topic's heading (with how many newsletters mention it) and its phrase list. */
export function describeTopicDefinition(lens: LensDefinition, analyzedNewsletters: number): TopicDefinitionText {
  const share = analyzedNewsletters ? lens.newsletters / analyzedNewsletters : 0;
  return {
    title:
      `${lens.label}${lens.strong_towns_focus ? " (Strong Towns Chicago focus)" : ""}: ` +
      `${pluralize(lens.newsletters, "newsletter")} (${sharePercentFormat.format(share)})`,
    body:
      `${lens.description} Phrases (newsletters with each): ` +
      lens.phrases.map((item) => `${item.phrase} (${numberFormat.format(item.newsletters)})`).join(", "),
  };
}

/** "Jan 2026 – Mar 2026", or "–" for no months. */
export function describeMonthSpan(months: string[]): string {
  return months.length ? `${formatMonth(months[0])} – ${formatMonth(months[months.length - 1])}` : "–";
}

/** "Newest in the archive", "12 days before the archive's newest". */
export function describeRecency(date: string, archiveLastDate: string | null): string {
  if (!archiveLastDate) return "";
  const days = daysBetween(date, archiveLastDate);
  return days <= 0 ? "Newest in the archive" : `${pluralize(days, "day")} before the archive's newest`;
}

/** "All wards", "Ward 5" or "Wards 5, 12". */
export function describeWardScope(filters: Pick<AnalyticsFilters, "wards">): string {
  if (filters.wards.length === 0) return "All wards";
  return filters.wards.length === 1
    ? formatWard(filters.wards[0])
    : `Wards ${filters.wards.join(", ")}`;
}
