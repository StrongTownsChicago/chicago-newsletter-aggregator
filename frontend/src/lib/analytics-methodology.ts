// Plain-language descriptions of how the analytics are computed, built from
// the generated data and the dashboard's own constants so the dashboard and
// the methodology page cannot drift from what the numbers actually do.
import {
  BROAD_COVERAGE_PEAK_FRACTION,
  formatMonth,
  type AnalyticsMetadata,
  type BroadCoverageWindow,
  type LensDefinition,
  type LensSummary,
} from "./analytics";

export const METHODOLOGY_PATH = "/analytics/methodology";
/** Where readers can report a missing newsletter or a correction. */
export const REPORT_ISSUE_URL = "https://github.com/StrongTownsChicago/chicago-newsletter-aggregator/issues";

const numberFormat = new Intl.NumberFormat("en-US");
const percentFormat = new Intl.NumberFormat("en-US", { style: "percent" });
const sharePercentFormat = new Intl.NumberFormat("en-US", { style: "percent", maximumFractionDigits: 1 });

export function pluralize(count: number, noun: string): string {
  return `${numberFormat.format(count)} ${noun}${count === 1 ? "" : "s"}`;
}

/** "months when at least 34 wards sent newsletters (90% of the 38 in the busiest month)". */
export function describeBroadCoverageRule(window: BroadCoverageWindow): string {
  return (
    `months when at least ${window.minActiveWards} wards sent newsletters ` +
    `(${percentFormat.format(BROAD_COVERAGE_PEAK_FRACTION)} of the ${window.peakActiveWards} in the busiest month)`
  );
}

/** How a newsletter is found to mention a topic, from the rules recorded with the data. */
export function describeTopicMatching(summary: Pick<LensSummary, "text" | "min_mentions">): string {
  return (
    `A newsletter mentions a topic when the topic's words and phrases appear at least ${pluralize(summary.min_mentions, "separate time")} ` +
    "in its subject and text (whole words within one sentence, any capitalization, singular or plural). " +
    'The same phrase twice counts twice, but phrases that overlap or sit side by side, as in "city council meeting", count once, ' +
    "so a single passing mention does not count. " +
    (summary.text === "cleaned"
      ? "Matching skips text a ward repeats across many of its issues (footers, standing resource lists), so a standing block does not count as news every month."
      : "Matching reads the full text, including standing blocks a ward repeats in every issue.")
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
      `${lens.description} Phrases (newsletters containing each): ` +
      lens.phrases.map((item) => `${item.phrase} (${numberFormat.format(item.newsletters)})`).join(", "),
  };
}

/** The boilerplate rule recorded with the data, or a general description for older data. */
export function describeBoilerplateRule(metadata: Pick<AnalyticsMetadata, "boilerplate">): string {
  const rule = metadata.boilerplate;
  if (!rule) return "Text a ward repeats across many of its newsletters is removed before counting.";
  return (
    `Text that appears in at least ${rule.min_share_percent}% of one ward's newsletters is removed before counting. ` +
    `Wards with fewer than ${rule.min_source_newsletters} newsletters keep all their text.`
  );
}

export function describeDefaultWindow(window: BroadCoverageWindow | null): string {
  if (!window) return "The dashboard shows the whole archive by default.";
  const before =
    window.minActiveWardsBefore === window.maxActiveWardsBefore
      ? `${window.maxActiveWardsBefore}`
      : `${window.minActiveWardsBefore}–${window.maxActiveWardsBefore}`;
  return (
    `The dashboard starts at ${formatMonth(window.startMonth)}, the first of the ${describeBroadCoverageRule(window)}. ` +
    `Earlier months had ${before} wards a month, so pooled numbers would mostly show wards being added. ` +
    '"Show full archive" includes them.'
  );
}
