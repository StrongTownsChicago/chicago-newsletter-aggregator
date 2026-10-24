import { describe, it, expect, vi, afterEach } from "vitest";
import {
  describeTimeline,
  fetchTimelineMonths,
  renderTimeline,
} from "../../client/search-timeline";

const months = [
  { month: "2026-01", newsletterCount: 1, wardCount: 1 },
  { month: "2026-02", newsletterCount: 0, wardCount: 0 },
  { month: "2026-03", newsletterCount: 4, wardCount: 3 },
];

const TIMELINE_MARKUP = `<p data-timeline-summary></p><ol data-timeline-bars aria-busy="true"></ol>`;

const context = {
  searchUrl: new URL("https://example.org/search?q=snow&page=3"),
  currentMonth: "2026-03",
  selectedMonth: "2026-01",
};

describe("describeTimeline", () => {
  it("summarizes the total, the range and the peak month", () => {
    expect(describeTimeline(months)).toBe(
      "5 newsletters, Jan–Mar 2026. Most in Mar 2026 (4, from 3 wards).",
    );
  });

  it("uses singular forms", () => {
    expect(describeTimeline([{ month: "2026-01", newsletterCount: 1, wardCount: 1 }])).toBe(
      "1 newsletter, Jan 2026. Most in Jan 2026 (1, from 1 ward).",
    );
  });
});

describe("renderTimeline", () => {
  const render = () => {
    const root = document.createElement("div");
    // eslint-disable-next-line no-unsanitized/property -- static test fixture markup
    root.innerHTML = TIMELINE_MARKUP;
    renderTimeline(root, months, context);
    return root;
  };

  it("labels every month with its count and links months that have matches", () => {
    const root = render();
    const columns = [...root.querySelectorAll("[data-timeline-bars] > li")];
    expect(columns.map((column) => column.textContent)).toEqual(["1Jan2026", "0Feb", "4Mar"]);

    const links = [...root.querySelectorAll<HTMLAnchorElement>("[data-timeline-bars] a")];
    expect(links.map((link) => link.getAttribute("href"))).toEqual([
      "/search?q=snow&from=2026-01-01&to=2026-01-31",
      "/search?q=snow&from=2026-03-01&to=2026-03-31",
    ]);
    expect(links[1].getAttribute("aria-label")).toBe("Mar 2026 so far: 4 newsletters, 3 wards");
    // The label contains the link's visible text (WCAG 2.5.3); the count beside it is hidden from screen readers.
    expect(links[1].textContent).toBe("Mar");
    expect(columns[2].querySelector('[aria-hidden="true"]')?.textContent).toBe("4");
    expect(root.querySelector("[data-timeline-bars]")?.hasAttribute("aria-busy")).toBe(false);
  });

  it("marks the selected month", () => {
    const root = render();
    expect(root.querySelector("[aria-current]")?.getAttribute("aria-label")).toBe(
      "Jan 2026: 1 newsletter, 1 ward",
    );
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
