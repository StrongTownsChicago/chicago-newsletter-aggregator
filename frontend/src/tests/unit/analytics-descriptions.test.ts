import { describe, expect, it } from "vitest";
import { type BroadCoverageWindow, type LensDefinition } from "../../lib/analytics";
import {
  describeBroadCoverageRule,
  describeMonthSpan,
  describeRecency,
  describeTopicDefinition,
  describeTopicMatching,
  describeWardScope,
  pluralize,
} from "../../lib/analytics-descriptions";

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

describe("describeBroadCoverageRule", () => {
  it("states the minimum number of sending wards", () => {
    expect(describeBroadCoverageRule(window)).toBe("at least 34 wards sent newsletters");
  });
});

describe("dashboard scope text", () => {
  it("spans the first and last month", () => {
    expect(describeMonthSpan(["2026-01", "2026-02", "2026-03"])).toBe("Jan 2026 – Mar 2026");
    expect(describeMonthSpan([])).toBe("–");
  });

  it("dates a newsletter against the archive's newest", () => {
    expect(describeRecency("2026-10-13", "2026-10-13")).toBe("Newest in the archive");
    expect(describeRecency("2026-10-01", "2026-10-13")).toBe("12 days before the archive's newest");
    expect(describeRecency("2026-10-12", "2026-10-13")).toBe("1 day before the archive's newest");
    expect(describeRecency("2026-10-01", null)).toBe("");
  });

  it("names the selected wards", () => {
    expect(describeWardScope({ wards: [] })).toBe("All wards");
    expect(describeWardScope({ wards: ["5"] })).toBe("Ward 5");
    expect(describeWardScope({ wards: ["5", "12"] })).toBe("Wards 5, 12");
  });
});
