import { describe, expect, it } from "vitest";
import { buildLensWardGrid, computeLensWardReach, isReachFaded } from "../../lib/analytics/reach";
import { fact } from "../analytics-fixtures";

describe("lens ward reach", () => {
  const facts = [
    fact({ ward: "1", date: "2026-01-05", lenses: ["schools"] }),
    fact({ ward: "1", date: "2026-01-20", lenses: ["schools", "events"] }),
    fact({ ward: "2", date: "2026-01-07", lenses: [] }),
    // Image-only: cannot mention anything, so ward 3 is left out of January's denominator.
    fact({ ward: "3", date: "2026-01-09", lenses: [], text_unavailable: true }),
    fact({ ward: "2", date: "2026-02-03", lenses: ["schools"] }),
    fact({ ward: null, date: "2026-02-03", lenses: ["schools"] }),
  ];

  it("counts wards mentioning each lens out of wards with readable newsletters", () => {
    const cells = computeLensWardReach(facts, ["schools", "events"], ["2026-01", "2026-02", "2026-03"]);
    expect(cells).toEqual([
      { lens: "schools", month: "2026-01", wardsMentioning: 1, activeWards: 2, share: 0.5 },
      { lens: "schools", month: "2026-02", wardsMentioning: 1, activeWards: 1, share: 1 },
      { lens: "schools", month: "2026-03", wardsMentioning: 0, activeWards: 0, share: null },
      { lens: "events", month: "2026-01", wardsMentioning: 1, activeWards: 2, share: 0.5 },
      { lens: "events", month: "2026-02", wardsMentioning: 0, activeWards: 1, share: 0 },
      { lens: "events", month: "2026-03", wardsMentioning: 0, activeWards: 0, share: null },
    ]);
  });

  it("counts a ward once however many of its newsletters mention the lens", () => {
    const [january] = computeLensWardReach(facts, ["schools"], ["2026-01"]);
    expect(january.wardsMentioning).toBe(1);
  });

  it("fades cells resting on too few wards, never when the threshold is 0", () => {
    expect(isReachFaded({ activeWards: 19 }, 20)).toBe(true);
    expect(isReachFaded({ activeWards: 20 }, 20)).toBe(false);
    expect(isReachFaded({ activeWards: 1 }, 0)).toBe(false);
  });

  it("grids one lens by ward and month, showing a month of only image-only newsletters as not mentioned", () => {
    const cells = buildLensWardGrid(facts, "schools", ["1", "2", "3"], ["2026-01"]);
    expect(cells).toEqual([
      { ward: "1", month: "2026-01", status: "mentioned", mentioning: 2, newsletters: 2 },
      { ward: "2", month: "2026-01", status: "not_mentioned", mentioning: 0, newsletters: 1 },
      { ward: "3", month: "2026-01", status: "not_mentioned", mentioning: 0, newsletters: 1 },
    ]);
    expect(buildLensWardGrid(facts, "schools", ["4"], ["2026-01"])[0].status).toBe("no_newsletter");
  });
});
