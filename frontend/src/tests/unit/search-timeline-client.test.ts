import { describe, it, expect, vi, afterEach } from "vitest";
import {
  describeTimeline,
  fetchTimelineMonths,
  renderTimeline,
} from "../../scripts/search-timeline";

const months = [
  { month: "2026-01", newsletterCount: 1, wardCount: 1 },
  { month: "2026-02", newsletterCount: 0, wardCount: 0 },
  { month: "2026-03", newsletterCount: 4, wardCount: 3 },
];

const TIMELINE_MARKUP = `
  <p data-timeline-summary></p>
  <div data-timeline-bars></div>
  <span data-timeline-start></span><span data-timeline-end></span>
  <table><tbody data-timeline-rows></tbody></table>
`;

describe("describeTimeline", () => {
  it("summarizes totals and the peak month", () => {
    expect(describeTimeline(months)).toBe(
      "5 newsletters in 2 months. Most in Mar 2026: 4 newsletters from 3 wards.",
    );
  });

  it("uses singular forms", () => {
    expect(describeTimeline([{ month: "2026-01", newsletterCount: 1, wardCount: 1 }])).toBe(
      "1 newsletter in 1 month. Most in Jan 2026: 1 newsletter from 1 ward.",
    );
  });
});

describe("renderTimeline", () => {
  it("renders one bar and one table row per month, including zero months", () => {
    const root = document.createElement("div");
    root.innerHTML = TIMELINE_MARKUP;

    renderTimeline(root, months, "2026-03");

    const bars = root.querySelectorAll<HTMLElement>("[data-timeline-bars] > div");
    expect(bars).toHaveLength(3);
    expect((bars[1].firstElementChild as HTMLElement).style.height).toBe("0%");
    expect((bars[2].firstElementChild as HTMLElement).style.height).toBe("100%");

    const rows = [...root.querySelectorAll("[data-timeline-rows] tr")].map((row) =>
      [...row.children].map((cell) => cell.textContent),
    );
    expect(rows).toEqual([
      ["Jan 2026", "1", "1"],
      ["Feb 2026", "0", "0"],
      ["Mar 2026 (so far)", "4", "3"],
    ]);
    expect(root.querySelector("[data-timeline-rows] th")?.getAttribute("scope")).toBe("row");
    expect(root.querySelector("[data-timeline-start]")?.textContent).toBe("Jan 2026");
    expect(root.querySelector("[data-timeline-end]")?.textContent).toBe("Mar 2026");
    expect(root.querySelector("[data-timeline-summary]")?.textContent).toContain("5 newsletters");
  });
});

describe("fetchTimelineMonths", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  const stubFetch = (implementation: () => Promise<Response>) => {
    const fetchMock = vi.fn(implementation);
    vi.stubGlobal("fetch", fetchMock);
    return fetchMock;
  };

  it("requests the API for the query and returns months", async () => {
    const fetchMock = stubFetch(async () => Response.json({ months }));

    expect(await fetchTimelineMonths("snow removal")).toEqual(months);
    expect(fetchMock).toHaveBeenCalledWith("/api/search-timeline?q=snow+removal");
  });

  it("returns no months when the function is missing (404)", async () => {
    stubFetch(async () => Response.json({ error: "timeline_unavailable" }, { status: 404 }));
    expect(await fetchTimelineMonths("snow")).toEqual([]);
  });

  it("returns no months on network errors or malformed JSON", async () => {
    stubFetch(async () => {
      throw new TypeError("offline");
    });
    expect(await fetchTimelineMonths("snow")).toEqual([]);

    stubFetch(async () => new Response("not json"));
    expect(await fetchTimelineMonths("snow")).toEqual([]);
  });
});
