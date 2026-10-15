import {
  barHeightPercent,
  buildTimelineApiUrl,
  formatTimelineMonth,
  getChicagoMonth,
  parseTimelineResponseBody,
  summarizeTimeline,
  type TimelineMonth,
} from "../lib/search-timeline";

/**
 * Client wiring for the /search timeline (`SearchTimeline.astro`).
 *
 * The timeline loads only when its anchor nears the viewport, so visitors who
 * never scroll past the results (and crawlers that don't run scripts) cause no
 * database work. Any failure (missing database function, network error,
 * malformed response) leaves the section hidden.
 */

const ROOT_SELECTOR = "[data-search-timeline-root]";
/** Start loading a little before the section scrolls into view. */
const PRELOAD_MARGIN = "200px";

const pluralize = (count: number, singular: string, plural: string): string =>
  `${count.toLocaleString("en-US")} ${count === 1 ? singular : plural}`;

const newslettersLabel = (count: number) =>
  pluralize(count, "newsletter", "newsletters");
const wardsLabel = (count: number) => pluralize(count, "ward", "wards");

/** Month label, marking the current month as partial. */
const monthLabel = (month: string, currentMonth: string): string =>
  month === currentMonth
    ? `${formatTimelineMonth(month)} (so far)`
    : formatTimelineMonth(month);

/** One-sentence description of the timeline. */
export function describeTimeline(months: TimelineMonth[]): string {
  const summary = summarizeTimeline(months);
  if (!summary) return "";

  const { totalNewsletters, monthsWithMatches, peak } = summary;
  return (
    `${newslettersLabel(totalNewsletters)} in ` +
    `${pluralize(monthsWithMatches, "month", "months")}. ` +
    `Most in ${formatTimelineMonth(peak.month)}: ` +
    `${newslettersLabel(peak.newsletterCount)} from ${wardsLabel(peak.wardCount)}.`
  );
}

const createElement = <Tag extends keyof HTMLElementTagNameMap>(
  tag: Tag,
  className: string,
  text?: string,
): HTMLElementTagNameMap[Tag] => {
  const element = document.createElement(tag);
  element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
};

const buildBar = (
  entry: TimelineMonth,
  maxCount: number,
  currentMonth: string,
): HTMLElement => {
  const column = createElement("div", "flex-1 min-w-[3px] h-full flex items-end");
  column.title =
    `${monthLabel(entry.month, currentMonth)}: ` +
    `${newslettersLabel(entry.newsletterCount)}, ${wardsLabel(entry.wardCount)}`;
  const bar = createElement("div", "w-full bg-blue-600 rounded-t-sm");
  bar.style.height = `${barHeightPercent(entry.newsletterCount, maxCount)}%`;
  column.append(bar);
  return column;
};

const buildTableRow = (
  entry: TimelineMonth,
  currentMonth: string,
): HTMLTableRowElement => {
  const row = document.createElement("tr");
  row.append(
    createElement("th", "py-1 pr-4 font-normal text-left", monthLabel(entry.month, currentMonth)),
    createElement("td", "py-1 pr-4 text-right tabular-nums", entry.newsletterCount.toLocaleString("en-US")),
    createElement("td", "py-1 text-right tabular-nums", entry.wardCount.toLocaleString("en-US")),
  );
  row.firstElementChild?.setAttribute("scope", "row");
  return row;
};

const requireElement = (root: HTMLElement, selector: string): HTMLElement => {
  const element = root.querySelector<HTMLElement>(selector);
  if (!element) throw new Error(`Search timeline markup is missing ${selector}`);
  return element;
};

/** Fills the timeline section with bars, labels, summary and table. */
export function renderTimeline(
  root: HTMLElement,
  months: TimelineMonth[],
  currentMonth: string,
): void {
  const maxCount = Math.max(...months.map((entry) => entry.newsletterCount));

  requireElement(root, "[data-timeline-summary]").textContent =
    describeTimeline(months);
  requireElement(root, "[data-timeline-bars]").replaceChildren(
    ...months.map((entry) => buildBar(entry, maxCount, currentMonth)),
  );
  requireElement(root, "[data-timeline-start]").textContent =
    formatTimelineMonth(months[0].month);
  requireElement(root, "[data-timeline-end]").textContent =
    formatTimelineMonth(months[months.length - 1].month);
  requireElement(root, "[data-timeline-rows]").replaceChildren(
    ...months.map((entry) => buildTableRow(entry, currentMonth)),
  );
}

/** Fetches the timeline JSON; resolves [] on any failure. */
export async function fetchTimelineMonths(query: string): Promise<TimelineMonth[]> {
  try {
    const response = await fetch(buildTimelineApiUrl(query));
    if (!response.ok) return [];
    return parseTimelineResponseBody(await response.json());
  } catch {
    return [];
  }
}

async function loadTimeline(root: HTMLElement, query: string): Promise<void> {
  const months = await fetchTimelineMonths(query);
  if (months.length === 0) return;

  renderTimeline(root, months, getChicagoMonth(new Date()));
  requireElement(root, "[data-timeline-section]").hidden = false;
}

/** Loads the timeline once its anchor approaches the viewport. */
export function initSearchTimeline(): void {
  const root = document.querySelector<HTMLElement>(ROOT_SELECTOR);
  const query = root?.dataset.query;
  if (!root || !query) return;

  const load = () => void loadTimeline(root, query);

  if (!("IntersectionObserver" in window)) {
    load();
    return;
  }

  const observer = new IntersectionObserver(
    (entries) => {
      if (entries.some((entry) => entry.isIntersecting)) {
        observer.disconnect();
        load();
      }
    },
    { rootMargin: PRELOAD_MARGIN },
  );
  observer.observe(root);
}
