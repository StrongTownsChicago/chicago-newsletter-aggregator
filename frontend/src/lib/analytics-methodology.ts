// Plain-language descriptions of how the analytics are computed, built from the
// data and the dashboard's constants so the page and the numbers cannot drift.
import {
  BROAD_COVERAGE_PEAK_FRACTION,
  formatMonth,
  type AnalyticsMetadata,
  type BroadCoverageWindow,
  type LensDefinition,
  type LensSummary,
} from "./analytics";

export const METHODOLOGY_PATH = "/analytics/methodology";
/** Where readers report a missing newsletter or a correction. */
export const REPORT_ISSUE_URL = "https://github.com/StrongTownsChicago/chicago-newsletter-aggregator/issues";

const numberFormat = new Intl.NumberFormat("en-US");
const percentFormat = new Intl.NumberFormat("en-US", { style: "percent" });
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

/** The repeated-text rule recorded with the data, or a general description for older data. */
export function describeBoilerplateRule(metadata: Pick<AnalyticsMetadata, "boilerplate">): string {
  const rule = metadata.boilerplate;
  if (!rule) return "Text a ward repeats across many of its newsletters is removed before counting.";
  return (
    `Text found in at least ${rule.min_share_percent}% of one ward's newsletters is removed before counting. ` +
    `Wards with fewer than ${rule.min_source_newsletters} newsletters keep all their text.`
  );
}

export function describeDefaultWindow(window: BroadCoverageWindow | null): string {
  if (!window) return "The dashboard shows the whole archive by default.";
  return (
    `The dashboard starts at ${formatMonth(window.startMonth)}, the first month ${describeBroadCoverageRule(window)} ` +
    `(${percentFormat.format(BROAD_COVERAGE_PEAK_FRACTION)} of the busiest month's ${window.peakActiveWards}). ` +
    `Before that, at most ${window.maxActiveWardsBefore} wards a month did, so totals mostly track wards being added. ` +
    '"Show all dates" includes those months.'
  );
}
