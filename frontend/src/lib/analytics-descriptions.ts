// Dashboard text built from the data and its rules, so labels and numbers cannot drift.
import { type BroadCoverageWindow, type LensDefinition, type LensSummary } from "./analytics";

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
