import { describe, expect, it } from "vitest";
import {
  COVERAGE_STATUS_LABELS,
  describeWardReach,
  formatCount,
  formatLift,
  formatMedian,
  formatOptionalShare,
  formatPercent,
  formatWard,
  LENS_WARD_STATUS_LABELS,
  sourceLabel,
} from "../../lib/analytics-format";

describe("analytics formats", () => {
  it("formats shares as percentages with one decimal", () => {
    expect(formatPercent(0.375)).toBe("37.5%");
    expect(formatPercent(0)).toBe("0.0%");
  });

  it("explains a missing share instead of showing a number", () => {
    expect(formatOptionalShare(0.5)).toBe("50.0%");
    expect(formatOptionalShare(null)).toBe("too few newsletters that month for a share");
  });

  it("caps unstable lifts", () => {
    expect(formatLift(2.345)).toBe("2.3×");
    expect(formatLift(100)).toBe("100.0×");
    expect(formatLift(250)).toBe(">100×");
  });

  it("names wards and sources", () => {
    expect(formatWard("5")).toBe("Ward 5");
    expect(sourceLabel({ name: "Ada Alder", ward: "5" })).toBe("Ada Alder (Ward 5)");
    expect(sourceLabel({ name: "Mayor's Office", ward: null })).toBe("Mayor's Office");
  });

  it("describes ward reach with its denominator", () => {
    const cell = { lens: "schools", month: "2026-01", wardsMentioning: 14, activeWards: 38, share: 14 / 38 };
    expect(describeWardReach(cell)).toBe("14 of 38 wards (36.8%)");
    expect(describeWardReach({ ...cell, wardsMentioning: 0, activeWards: 0, share: null })).toBe(
      "no ward sent newsletters",
    );
  });

  it("labels every lens ward status", () => {
    expect(Object.keys(LENS_WARD_STATUS_LABELS).sort()).toEqual(["mentioned", "no_newsletter", "not_mentioned"]);
  });
});

describe("dashboard number formats", () => {
  it("groups counts and rounds medians to one decimal", () => {
    expect(formatCount(1234)).toBe("1,234");
    expect(formatMedian(2.25)).toBe("2.3");
    expect(formatMedian(4)).toBe("4");
    expect(formatMedian(null)).toBe("–");
  });

  it("labels every coverage status", () => {
    expect(Object.keys(COVERAGE_STATUS_LABELS).sort()).toEqual(["received", "silent", "untracked"]);
  });
});
