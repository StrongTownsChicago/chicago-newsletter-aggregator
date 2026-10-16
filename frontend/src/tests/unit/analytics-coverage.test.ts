import { describe, expect, it } from "vitest";
import {
  buildCoverageGrid,
  countNewslettersByWardMonth,
  findLongestGaps,
  summarizeWardCoverage,
} from "../../lib/analytics-coverage";
import { fact, source } from "../analytics-fixtures";

describe("cadence", () => {
  it("counts newsletters per ward per month", () => {
    const counts = countNewslettersByWardMonth([
      fact({ ward: "10", date: "2026-01-01" }),
      fact({ ward: "2", date: "2026-01-05" }),
      fact({ ward: "2", date: "2026-01-20" }),
      fact({ ward: null }),
    ]);
    expect(counts).toEqual([
      { ward: "2", month: "2026-01", newsletters: 2 },
      { ward: "10", month: "2026-01", newsletters: 1 },
    ]);
  });

  it("finds the longest gaps between consecutive newsletters per source", () => {
    const gaps = findLongestGaps(
      [
        fact({ source_id: 1, date: "2026-01-01" }),
        fact({ source_id: 1, date: "2026-03-01" }),
        fact({ source_id: 1, date: "2026-03-05" }),
        fact({ source_id: 2, date: "2026-01-01", ward: "2", alder: "Bo" }),
        fact({ source_id: 2, date: "2026-01-11", ward: "2", alder: "Bo" }),
      ],
      2,
    );
    expect(gaps).toEqual([
      { sourceId: 1, alder: "Ada Alder", ward: "1", from: "2026-01-01", to: "2026-03-01", days: 59 },
      { sourceId: 2, alder: "Bo", ward: "2", from: "2026-01-01", to: "2026-01-11", days: 10 },
    ]);
  });
});

describe("coverage", () => {
  it("marks months before a ward's first newsletter untracked and later empty months silent", () => {
    const archive = [
      fact({ ward: "1", date: "2026-02-10" }),
      fact({ ward: "1", date: "2026-02-20" }),
      fact({ ward: "1", date: "2026-04-01" }),
    ];
    const cells = buildCoverageGrid(archive, ["1", "4"], ["2026-01", "2026-02", "2026-03", "2026-04"]);
    expect(cells.map((cell) => [cell.ward, cell.month, cell.status, cell.newsletters])).toEqual([
      ["1", "2026-01", "untracked", 0],
      ["1", "2026-02", "received", 2],
      ["1", "2026-03", "silent", 0],
      ["1", "2026-04", "received", 1],
      ["4", "2026-01", "untracked", 0],
      ["4", "2026-02", "untracked", 0],
      ["4", "2026-03", "untracked", 0],
      ["4", "2026-04", "untracked", 0],
    ]);
  });

  it("keeps a ward tracked in a window that starts after its first newsletter", () => {
    const archive = [fact({ ward: "1", date: "2025-06-01" })];
    expect(buildCoverageGrid(archive, ["1"], ["2026-01"])[0].status).toBe("silent");
  });

  it("summarizes archive coverage per ward, merging sources and keeping wards with none", () => {
    const sources = [
      source({ id: 1, name: "Former", ward: "1", first_date: "2025-01-01", last_date: "2025-06-01", newsletters: 4 }),
      source({ id: 2, name: "Current", ward: "1", first_date: "2025-07-01", last_date: "2026-01-01", newsletters: 6 }),
      source({ id: 3, name: "Quiet", ward: "4", first_date: null, last_date: null, newsletters: 0 }),
    ];
    expect(summarizeWardCoverage(sources, ["1", "4", "7"])).toEqual([
      { ward: "1", aldermen: ["Former", "Current"], firstDate: "2025-01-01", lastDate: "2026-01-01", newsletters: 10 },
      { ward: "4", aldermen: ["Quiet"], firstDate: null, lastDate: null, newsletters: 0 },
      { ward: "7", aldermen: [], firstDate: null, lastDate: null, newsletters: 0 },
    ]);
  });
});
