import { describe, expect, it } from "vitest";
import { median, type NewsletterFact, type SourceCoverage } from "../../lib/analytics/core";
import {
  buildWardProfile,
  computeCityMedianPerTrackedMonth,
  MIN_WARD_MONTHS_FOR_SHARES,
  MIN_WARD_NEWSLETTERS_FOR_SHARES,
  summarizeCadence,
} from "../../lib/analytics/ward-profile";

let nextId = 0;
function fact(overrides: Partial<NewsletterFact> = {}): NewsletterFact {
  nextId += 1;
  return {
    id: `n${nextId}`,
    date: "2026-01-15",
    source_id: 1,
    ward: "1",
    alder: "Ada Alder",
    lenses: [],
    words: 500,
    ...overrides,
  };
}

function source(overrides: Partial<SourceCoverage> = {}): SourceCoverage {
  return {
    id: 1,
    name: "Ada Alder",
    ward: "1",
    source_type: "alderman",
    first_date: "2026-01-15",
    last_date: "2026-03-15",
    newsletters: 0,
    ...overrides,
  };
}

/** `count` newsletters from one ward in one month, on consecutive days from the 1st. */
function monthOfFacts(ward: string, month: string, count: number, lenses: string[] = []): NewsletterFact[] {
  return Array.from({ length: count }, (_, index) =>
    fact({ ward, source_id: Number(ward), date: `${month}-${String(index + 1).padStart(2, "0")}`, lenses }),
  );
}

describe("median", () => {
  it("returns the middle value, the mean of the middle two, or null", () => {
    expect(median([3, 1, 2])).toBe(2);
    expect(median([4, 1, 3, 2])).toBe(2.5);
    expect(median([])).toBeNull();
  });
});

describe("summarizeCadence", () => {
  it("counts silent tracked months as zero and ignores untracked months", () => {
    const cadence = summarizeCadence(
      [
        { ward: "1", month: "2026-01", status: "untracked", newsletters: 0 },
        { ward: "1", month: "2026-02", status: "received", newsletters: 4 },
        { ward: "1", month: "2026-03", status: "silent", newsletters: 0 },
        { ward: "1", month: "2026-04", status: "received", newsletters: 2 },
      ],
      ["2026-02-01", "2026-02-11", "2026-04-01"],
    );
    expect(cadence).toEqual({
      medianPerTrackedMonth: 2,
      medianDaysBetween: (10 + 49) / 2,
    });
  });

  it("has no gap with fewer than two newsletters", () => {
    expect(summarizeCadence([], ["2026-01-01"]).medianDaysBetween).toBeNull();
  });
});

describe("computeCityMedianPerTrackedMonth", () => {
  it("takes the median over wards of each ward's median tracked month", () => {
    const facts = [
      ...monthOfFacts("1", "2026-01", 1),
      ...monthOfFacts("1", "2026-02", 1),
      ...monthOfFacts("2", "2026-01", 5),
      ...monthOfFacts("2", "2026-02", 5),
      ...monthOfFacts("3", "2026-01", 3),
      ...monthOfFacts("3", "2026-02", 3),
    ];
    expect(computeCityMedianPerTrackedMonth(facts, ["2026-01", "2026-02"])).toBe(3);
  });
});

describe("buildWardProfile", () => {
  const months = ["2026-01", "2026-02", "2026-03", "2026-04"];
  const lensIds = ["budget", "parks"];

  it("describes a ward with coverage dates, cadence, and monthly topic cells", () => {
    const facts = [
      ...monthOfFacts("1", "2026-02", 2, ["budget"]),
      ...monthOfFacts("1", "2026-04", 1),
      ...monthOfFacts("2", "2026-01", 1, ["parks"]),
    ];
    const sources = [
      source({ first_date: "2026-02-01", last_date: "2026-04-01", newsletters: 3 }),
      source({ id: 2, name: "Bo Alder", ward: "2", newsletters: 1 }),
    ];
    const profile = buildWardProfile({ newsletters: facts, sources }, "1", { window: months, archive: months }, lensIds);

    expect(profile.aldermen).toEqual(["Ada Alder"]);
    expect(profile.firstDate).toBe("2026-02-01");
    expect(profile.archiveNewsletters).toBe(3);
    expect(profile.windowNewsletters).toBe(3);
    expect(profile.months.map((cell) => cell.status)).toEqual(["untracked", "received", "silent", "received"]);
    // Three tracked months (2, 0 and 1 newsletters): the untracked first month is left out.
    expect(profile.cadence.medianPerTrackedMonth).toBe(1);
    const budget = profile.topicCells.filter((cell) => cell.lens === "budget").map((cell) => cell.status);
    expect(budget).toEqual(["no_newsletter", "mentioned", "no_newsletter", "not_mentioned"]);
    // Shaded by the share of that month's newsletters mentioning the topic.
    const budgetShares = profile.topicCells.filter((cell) => cell.lens === "budget").map((cell) => cell.share);
    expect(budgetShares).toEqual([null, 1, null, 0]);
    expect(profile.topics.find((topic) => topic.lens === "budget")).toMatchObject({
      monthsMentioning: 1,
      monthsChecked: 2,
      newslettersMentioning: 2,
    });
  });

  it("restricts the window but keeps the whole archive for the ward's own history", () => {
    const facts = [...monthOfFacts("1", "2026-01", 6), ...monthOfFacts("1", "2026-03", 2)];
    const profile = buildWardProfile({ newsletters: facts, sources: [source()] }, "1", { window: ["2026-03"], archive: months }, lensIds);
    expect(profile.windowNewsletters).toBe(2);
    expect(profile.archiveNewsletters).toBe(8);
    expect(profile.cadence.medianPerTrackedMonth).toBe(2);
    // Jan 6, Feb 0, Mar 2, Apr 0 across the archive.
    expect(profile.archiveCadence.medianPerTrackedMonth).toBe(1);
  });

  it("withholds shares until the ward has enough newsletters and months", () => {
    const sparse = buildWardProfile({ newsletters: monthOfFacts("1", "2026-01", 5, ["budget"]), sources: [source()] }, "1", { window: months, archive: months }, lensIds);
    expect(sparse.sharesShown).toBe(false);
    expect(sparse.topics.every((topic) => topic.wardShare === null && topic.cityShare === null)).toBe(true);
  });

  it("compares the ward's share of months with the average share of active wards in the same months", () => {
    const perMonth = Math.ceil(MIN_WARD_NEWSLETTERS_FOR_SHARES / MIN_WARD_MONTHS_FOR_SHARES);
    const wardMonths = months.slice(0, MIN_WARD_MONTHS_FOR_SHARES);
    const facts = [
      // Ward 1 mentions the budget in its first month only.
      ...wardMonths.flatMap((month, index) => monthOfFacts("1", month, perMonth, index === 0 ? ["budget"] : [])),
      // Ward 2 mentions it every month, ward 3 never; both send every month.
      ...wardMonths.flatMap((month) => monthOfFacts("2", month, 1, ["budget"])),
      ...wardMonths.flatMap((month) => monthOfFacts("3", month, 1)),
    ];
    const profile = buildWardProfile({ newsletters: facts, sources: [source()] }, "1", { window: months, archive: months }, lensIds);
    const budget = profile.topics.find((topic) => topic.lens === "budget");

    expect(profile.sharesShown).toBe(true);
    expect(budget?.wardShare).toBeCloseTo(1 / MIN_WARD_MONTHS_FOR_SHARES);
    // First month 2 of 3 wards, then 1 of 3 in each other month.
    const expectedCity = (2 / 3 + (MIN_WARD_MONTHS_FOR_SHARES - 1) / 3) / MIN_WARD_MONTHS_FOR_SHARES;
    expect(budget?.cityShare).toBeCloseTo(expectedCity);
  });

  it("leaves months whose newsletters could not be read out of the share's denominator", () => {
    const perMonth = MIN_WARD_NEWSLETTERS_FOR_SHARES;
    const facts = [
      ...months.slice(0, MIN_WARD_MONTHS_FOR_SHARES).flatMap((month) => monthOfFacts("1", month, perMonth, ["budget"])),
      fact({ ward: "1", date: "2026-04-10", text_unavailable: true }),
    ];
    const budget = buildWardProfile({ newsletters: facts, sources: [source()] }, "1", { window: months, archive: months }, lensIds).topics.find(
      (topic) => topic.lens === "budget",
    );
    expect(budget?.monthsChecked).toBe(MIN_WARD_MONTHS_FOR_SHARES);
    expect(budget?.wardShare).toBe(1);
  });

  it("reports a ward with no archived newsletters without inventing activity", () => {
    const profile = buildWardProfile({ newsletters: monthOfFacts("2", "2026-01", 3), sources: [source({ ward: "4", newsletters: 0 })] }, "4", { window: months, archive: months }, lensIds);
    expect(profile.archiveNewsletters).toBe(0);
    expect(profile.months.every((cell) => cell.status === "untracked")).toBe(true);
    expect(profile.cadence.medianPerTrackedMonth).toBeNull();
  });
});
