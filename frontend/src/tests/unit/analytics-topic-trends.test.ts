import { describe, expect, it } from "vitest";
import type { LensReachCell } from "../../lib/analytics/reach";
import {
  describeLatestVsAverage,
  describeSparkline,
  describeTopicReach,
  findAsOfMonth,
  findLargestChangeTopic,
  findPeakPoint,
  findWidestReachTopic,
  formatLatestReach,
  formatPointChange,
  formatPoints,
  isPartialMonth,
  latestReachCell,
  listFullMonths,
  MIN_TREND_SPAN,
  orderBySwing,
  reachDeviation,
  summarizeTopicTrends,
  tightShareDomain,
} from "../../lib/analytics/topic-trends";

function cell(lens: string, month: string, wardsMentioning: number, activeWards = 10): LensReachCell {
  return { lens, month, wardsMentioning, activeWards, share: activeWards ? wardsMentioning / activeWards : null };
}

const months = ["2026-01", "2026-02", "2026-03"];

describe("partial months", () => {
  it("reads the month the data was generated in", () => {
    expect(findAsOfMonth("2026-10-15T18:12:27.974176-05:00")).toBe("2026-10");
    expect(findAsOfMonth("")).toBeNull();
  });

  it("treats the generation month as partial, even after its last newsletter", () => {
    expect(isPartialMonth("2026-03", "2026-03")).toBe(true);
    expect(isPartialMonth("2026-02", "2026-03")).toBe(false);
    expect(isPartialMonth("2026-03", null)).toBe(false);
  });

  it("keeps a month whose last newsletter came before its end once the month is over", () => {
    // Data through Mar 24, generated in April: March is complete.
    expect(listFullMonths(months, "2026-04")).toEqual(months);
  });

  it("drops the in-progress month and keeps windows that end earlier", () => {
    expect(listFullMonths(months, "2026-03")).toEqual(["2026-01", "2026-02"]);
    expect(listFullMonths(["2026-01", "2026-02"], "2026-03")).toEqual(["2026-01", "2026-02"]);
    expect(listFullMonths([], "2026-03")).toEqual([]);
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

  it("breaks ties by topic order", () => {
    const tied = summarizeTopicTrends(
      [cell("parks", "2026-03", 6), cell("budget", "2026-03", 6), cell("parks", "2026-02", 4), cell("budget", "2026-02", 4)],
      ["parks", "budget"],
      ["2026-02", "2026-03"],
      0,
    );
    expect(findWidestReachTopic(tied)?.lens).toBe("parks");
    expect(findLargestChangeTopic(tied)?.lens).toBe("parks");
    expect(findWidestReachTopic([...tied].reverse())?.lens).toBe("budget");
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

describe("findPeakPoint", () => {
  const trendOf = (shares: (number | null)[]) => ({
    lens: "x",
    points: shares.map((share, index) => ({ month: months[index], share })),
    averageShare: null,
    swing: 0,
    latest: null,
    latestChange: null,
  });

  it("finds the month with the widest reach, the latest on a tie", () => {
    expect(findPeakPoint(trendOf([0.4, 0.7, 0.5]))).toEqual({ month: "2026-02", share: 0.7 });
    expect(findPeakPoint(trendOf([0.7, 0.2, 0.7]))?.month).toBe("2026-03");
  });

  it("skips months without a share", () => {
    expect(findPeakPoint(trendOf([null, 0.1, null]))?.month).toBe("2026-02");
    expect(findPeakPoint(trendOf([null, null, null]))).toBeNull();
  });

  it("has no peak when no ward mentioned the topic", () => {
    expect(findPeakPoint(trendOf([0, 0, null]))).toBeNull();
  });
});

describe("latest reach", () => {
  const trendWith = (latest: LensReachCell | null) => ({
    lens: "x",
    points: [],
    averageShare: null,
    swing: 0,
    latest,
    latestChange: null,
  });

  it("states the last full month's wards with their denominator", () => {
    const trend = trendWith(cell("x", "2026-03", 28, 37));
    expect(latestReachCell(trend)?.month).toBe("2026-03");
    expect(formatLatestReach(trend)).toBe("28 of 37");
    expect(describeTopicReach(trend)).toBe("28 of 37 wards");
  });

  it("shows nothing when no ward sent newsletters that month", () => {
    for (const trend of [trendWith(null), trendWith(cell("x", "2026-03", 0, 0))]) {
      expect(latestReachCell(trend)).toBeNull();
      expect(formatLatestReach(trend)).toBe("–");
      expect(describeTopicReach(trend)).toBe("");
    }
  });
});

describe("describeLatestVsAverage", () => {
  const trend = {
    lens: "x",
    points: [],
    averageShare: 0.717,
    swing: 0,
    latest: cell("x", "2026-03", 28, 37),
    latestChange: 0.04,
  };

  it("compares the last full month with the topic's average", () => {
    expect(describeLatestVsAverage(trend, "2026-03")).toBe(
      "Mar 2026: 28 of 37 wards, +4 pts vs its average (71.7%, dashed).",
    );
  });

  it("is empty without a trend, a month, a change or an average", () => {
    expect(describeLatestVsAverage(undefined, "2026-03")).toBe("");
    expect(describeLatestVsAverage(trend, undefined)).toBe("");
    expect(describeLatestVsAverage({ ...trend, latest: null }, "2026-03")).toBe("");
    expect(describeLatestVsAverage({ ...trend, latestChange: null }, "2026-03")).toBe("");
    expect(describeLatestVsAverage({ ...trend, averageShare: null }, "2026-03")).toBe("");
  });
});
