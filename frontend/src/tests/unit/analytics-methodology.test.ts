import { describe, expect, it } from "vitest";
import { BROAD_COVERAGE_PEAK_FRACTION, type BroadCoverageWindow, type LensDefinition } from "../../lib/analytics";
import {
  describeBoilerplateRule,
  describeBroadCoverageRule,
  describeDefaultWindow,
  describeTopicDefinition,
  describeTopicMatching,
  pluralize,
} from "../../lib/analytics-methodology";

const window: BroadCoverageWindow = {
  startMonth: "2026-01",
  endMonth: "2026-10",
  minActiveWards: 34,
  peakActiveWards: 38,
  maxActiveWardsBefore: 13,
  months: 10,
};

const lens: LensDefinition = {
  id: "budget_taxes",
  label: "Budget and taxes",
  description: "The city budget and property taxes.",
  strong_towns_focus: false,
  newsletters: 50,
  phrases: [
    { phrase: "budget", newsletters: 40 },
    { phrase: "property tax", newsletters: 1200 },
  ],
};

const wordingRules = (text: string) => {
  expect(text).not.toMatch(/\blens(es)?\b/i);
  expect(text).not.toMatch(/\balders?\b/i);
};

describe("pluralize", () => {
  it("adds an s except for one", () => {
    expect(pluralize(1, "ward")).toBe("1 ward");
    expect(pluralize(1200, "ward")).toBe("1,200 wards");
  });
});

describe("describeTopicMatching", () => {
  it("states the minimum mentions and whether repeated text is skipped", () => {
    const cleaned = describeTopicMatching({ text: "cleaned", min_mentions: 2 });
    expect(cleaned).toContain("2 separate times or more");
    expect(cleaned).toContain("Text a ward repeats");
    const raw = describeTopicMatching({ text: "raw", min_mentions: 1 });
    expect(raw).toContain("1 separate time or more");
    expect(raw).not.toContain("repeats");
    wordingRules(cleaned);
  });
});

describe("describeTopicDefinition", () => {
  it("lists the topic's exact phrases with their counts", () => {
    const { title, body } = describeTopicDefinition(lens, 200);
    expect(title).toBe("Budget and taxes: 50 newsletters (25%)");
    expect(body).toContain("budget (40), property tax (1,200)");
    wordingRules(title + body);
  });

  it("marks Strong Towns Chicago focus topics", () => {
    expect(describeTopicDefinition({ ...lens, strong_towns_focus: true }, 200).title).toContain(
      "(Strong Towns Chicago focus)",
    );
  });
});

describe("describeBoilerplateRule", () => {
  it("states the recorded thresholds", () => {
    const text = describeBoilerplateRule({ boilerplate: { min_share_percent: 30, min_source_newsletters: 10 } });
    expect(text).toContain("at least 30% of one ward's newsletters");
    expect(text).toContain("fewer than 10 newsletters");
  });

  it("falls back to a general description for data without the rule", () => {
    expect(describeBoilerplateRule({})).toContain("removed before counting");
  });
});

describe("describeDefaultWindow", () => {
  it("explains where the default window starts and why", () => {
    const text = describeDefaultWindow(window);
    expect(text).toContain("Jan 2026");
    expect(text).toContain(describeBroadCoverageRule(window));
    expect(text).toContain("at most 13 wards a month");
    expect(text).not.toMatch(/\d–\d/);
    expect(text).toContain(`${BROAD_COVERAGE_PEAK_FRACTION * 100}% of the busiest month's 38`);
  });

  it("says when the default is the whole archive", () => {
    expect(describeDefaultWindow(null)).toContain("whole archive");
  });
});
