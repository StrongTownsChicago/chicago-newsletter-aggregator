import { describe, expect, it } from "vitest";
import type { LensReachCell } from "../../lib/analytics";
import {
  describeSparkline,
  findLargestChangeTopic,
  findWidestReachTopic,
  formatPointChange,
  formatPoints,
  isPartialMonth,
  listFullMonths,
  MIN_TREND_SPAN,
  orderBySwing,
  reachDeviation,
  summarizeTopicTrends,
  tightShareDomain,
} from "../../lib/analytics-topic-trends";

function cell(lens: string, month: string, wardsMentioning: number, activeWards = 10): LensReachCell {
  return { lens, month, wardsMentioning, activeWards, share: activeWards ? wardsMentioning / activeWards : null };
}

const months = ["2026-01", "2026-02", "2026-03"];

describe("partial months", () => {
  it("treats the archive's last month as partial until its last day", () => {
    expect(isPartialMonth("2026-03", "2026-03-14")).toBe(true);
    expect(isPartialMonth("2026-03", "2026-03-31")).toBe(false);
    expect(isPartialMonth("2026-02", "2026-03-14")).toBe(false);
    expect(isPartialMonth("2026-03", null)).toBe(false);
  });

  it("drops only a trailing partial month", () => {
    expect(listFullMonths(months, "2026-03-14")).toEqual(["2026-01", "2026-02"]);
    expect(listFullMonths(months, "2026-03-31")).toEqual(months);
    expect(listFullMonths(["2026-01", "2026-02"], "2026-03-14")).toEqual(["2026-01", "2026-02"]);
    expect(listFullMonths([], "2026-03-14")).toEqual([]);
  });
});

describe("summarizeTopicTrends", () => {
  const cells = [
    cell("parks", "2026-01", 5),
    cell("parks", "2026-02", 7),
    cell("parks", "2026-03", 9),
    cell("budget", "2026-01", 4),
    cell("budget", "2026-02", 4),
    cell("budget", "2026-03", 4),
  ];

  it("measures each topic against its own average and swing", () => {
    const [parks, budget] = summarizeTopicTrends(cells, ["parks", "budget"], months, 0);
    expect(parks.averageShare).toBeCloseTo(0.7);
    expect(parks.swing).toBeCloseTo(0.4);
    expect(parks.latest?.wardsMentioning).toBe(9);
    expect(parks.latestChange).toBeCloseTo(0.2);
    expect(parks.points.map((point) => point.share)).toEqual([0.5, 0.7, 0.9]);
    expect(budget.swing).toBe(0);
    expect(budget.latestChange).toBeCloseTo(0);
  });

  it("leaves months with too few wards out of the average", () => {
    const thin = [cell("parks", "2026-01", 1, 2), cell("parks", "2026-02", 6), cell("parks", "2026-03", 8)];
    const [parks] = summarizeTopicTrends(thin, ["parks"], months, 5);
    expect(parks.points[0].share).toBeNull();
    expect(parks.averageShare).toBeCloseTo(0.7);
    expect(parks.swing).toBeCloseTo(0.2);
  });

  it("covers only the months it is given", () => {
    const [parks] = summarizeTopicTrends(cells, ["parks"], ["2026-01", "2026-02"], 0);
    expect(parks.latest?.month).toBe("2026-02");
    expect(parks.averageShare).toBeCloseTo(0.6);
  });

  it("has no average or change without data", () => {
    const [empty] = summarizeTopicTrends([], ["parks"], months, 0);
    expect(empty).toMatchObject({ averageShare: null, swing: 0, latest: null, latestChange: null });
  });

  it("orders by swing, keeping ties in their original order", () => {
    const trends = summarizeTopicTrends(
      [...cells, cell("schools", "2026-01", 1), cell("schools", "2026-03", 1)],
      ["budget", "schools", "parks"],
      months,
      0,
    );
    expect(orderBySwing(trends).map((trend) => trend.lens)).toEqual(["parks", "budget", "schools"]);
  });

  it("picks the widest-reaching and most changed topics in the last full month", () => {
    const trends = summarizeTopicTrends(
      [...cells, cell("schools", "2026-01", 9), cell("schools", "2026-02", 9), cell("schools", "2026-03", 10)],
      ["parks", "budget", "schools"],
      months,
      0,
    );
    expect(findWidestReachTopic(trends)?.lens).toBe("schools");
    expect(findLargestChangeTopic(trends)?.lens).toBe("parks");
    expect(findWidestReachTopic([])).toBeNull();
    // A last month resting on too few wards names no topic.
    const thinLatest = summarizeTopicTrends([cell("parks", "2026-03", 2, 2)], ["parks"], months, 5);
    expect(findWidestReachTopic(thinLatest)).toBeNull();
    expect(findLargestChangeTopic([])).toBeNull();
  });
});

describe("reachDeviation", () => {
  it("is the share minus the average, or null when either is missing", () => {
    expect(reachDeviation({ share: 0.8 }, 0.6)).toBeCloseTo(0.2);
    expect(reachDeviation({ share: null }, 0.6)).toBeNull();
    expect(reachDeviation({ share: 0.8 }, null)).toBeNull();
  });
});

describe("tightShareDomain", () => {
  it("hugs the shares", () => {
    expect(tightShareDomain([0.6, 0.85, 0.7])).toEqual([0.6, 0.85]);
  });

  it("widens flat series to the minimum span, within 0 to 1", () => {
    const [start, end] = tightShareDomain([0.5, 0.51]);
    expect(end - start).toBeCloseTo(MIN_TREND_SPAN);
    expect(tightShareDomain([0, 0])).toEqual([0, MIN_TREND_SPAN]);
    const [nearTop, top] = tightShareDomain([1, 1]);
    expect(top).toBe(1);
    expect(nearTop).toBeCloseTo(1 - MIN_TREND_SPAN);
    expect(tightShareDomain([])).toEqual([0, MIN_TREND_SPAN]);
  });
});

describe("formatting", () => {
  it("formats point changes with a sign and point differences without", () => {
    expect(formatPointChange(0.064)).toBe("+6 pts");
    expect(formatPointChange(-0.01)).toBe("−1 pt");
    expect(formatPointChange(-0.004)).toBe("0 pts");
    expect(formatPoints(0.12)).toBe("12 pts");
    expect(formatPoints(-0.12)).toBe("12 pts");
  });

  it("describes a sparkline as text", () => {
    expect(
      describeSparkline("Parks", [
        { month: "2026-01", share: 0.5 },
        { month: "2026-02", share: null },
      ]),
    ).toBe("Parks, Jan 2026 – Feb 2026: 50%, no data.");
    expect(describeSparkline("Parks", [])).toBe("Parks: no full months.");
  });
});
