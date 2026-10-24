import {
  barHeightPercent,
  buildMonthSearchUrl,
  buildTimelineApiUrl,
  clipTimelineToRange,
  formatMonthRange,
  formatShortMonth,
  formatTimelineMonth,
  getChicagoMonth,
  parseTimelineResponseBody,
  summarizeTimeline,
  yearLabelForBar,
  type TimelineMonth,
  type TimelineMonthRange,
} from "../lib/search-timeline";

/**
 * Client wiring for the /search timeline (`SearchTimeline.astro`). Crawlers
 * that don't run scripts never trigger the API. Any failure removes the card.
 */

const ROOT_SELECTOR = "[data-search-timeline-root]";

const pluralize = (count: number, singular: string, plural: string): string =>
  `${count.toLocaleString("en-US")} ${count === 1 ? singular : plural}`;

/** One-line summary, e.g. "106 newsletters, Jan–Oct 2026. Most in Jan 2026 (32, from 14 wards)." */
export function describeTimeline(months: TimelineMonth[]): string {
  const summary = summarizeTimeline(months);
  if (!summary) return "";
  const { totalNewsletters, peak } = summary;
  const range = formatMonthRange(months[0].month, months[months.length - 1].month);
  return (
    `${pluralize(totalNewsletters, "newsletter", "newsletters")}, ${range}. ` +
    `Most in ${formatTimelineMonth(peak.month)} ` +
    `(${peak.newsletterCount.toLocaleString("en-US")}, from ${pluralize(peak.wardCount, "ward", "wards")}).`
  );
}

export interface TimelineRenderContext {
  /** The page's URL; month links narrow it to one month. */
  searchUrl: URL;
  currentMonth: string;
  selectedMonth: string | null;
}

const element = <Tag extends keyof HTMLElementTagNameMap>(
  tag: Tag,
  className: string,
  text?: string,
): HTMLElementTagNameMap[Tag] => {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
};

const barColor = (isSelected: boolean, isPartial: boolean): string => {
  if (isSelected) return "bg-blue-800";
  if (isPartial) return "bg-blue-300 group-hover:bg-blue-400";
  return "bg-blue-600 group-hover:bg-blue-700";
};

const countClass = (hasMatches: boolean, isSelected: boolean): string => {
  if (!hasMatches) return "text-gray-400";
  return isSelected ? "font-semibold text-gray-900" : "text-gray-700";
};

const describeMonth = (entry: TimelineMonth, isPartial: boolean): string =>
  `${formatTimelineMonth(entry.month)}${isPartial ? " so far" : ""}: ` +
  `${pluralize(entry.newsletterCount, "newsletter", "newsletters")}, ` +
  `${pluralize(entry.wardCount, "ward", "wards")}`;

function buildMonthColumn(
  entry: TimelineMonth,
  index: number,
  maxCount: number,
  context: TimelineRenderContext,
): HTMLLIElement {
  const isPartial = entry.month === context.currentMonth;
  const isSelected = entry.month === context.selectedMonth;
  const hasMatches = entry.newsletterCount > 0;

  const column = element("li", "flex-1 min-w-[2.25rem] flex flex-col items-center");
  const target = hasMatches
    ? element("a", "group flex flex-col items-center w-full rounded focus-visible:outline-2 focus-visible:outline-blue-600")
    : element("div", "flex flex-col items-center w-full");
  if (target instanceof HTMLAnchorElement) {
    target.href = buildMonthSearchUrl(context.searchUrl, entry.month);
    if (isSelected) target.setAttribute("aria-current", "true");
  } else {
    // A generic div's aria-label is not announced; as an image it is read whole.
    target.setAttribute("role", "img");
  }
  target.setAttribute("aria-label", describeMonth(entry, isPartial));

  const count = element(
    "span",
    `text-xs tabular-nums ${countClass(hasMatches, isSelected)}`,
    entry.newsletterCount.toLocaleString("en-US"),
  );
  const track = element("span", "flex items-end justify-center w-full h-20 mt-0.5");
  const bar = element(
    "span",
    hasMatches
      ? `w-full max-w-[2.5rem] rounded-t ${barColor(isSelected, isPartial)}`
      : "w-full max-w-[2.5rem] h-px bg-gray-300",
  );
  if (hasMatches) bar.style.height = `${barHeightPercent(entry.newsletterCount, maxCount)}%`;
  track.append(bar);

  const monthLabel = element(
    "span",
    `mt-1 text-xs ${isSelected ? "font-semibold text-gray-900" : "text-gray-600"}`,
    formatShortMonth(entry.month),
  );
  target.append(track, monthLabel);
  // Outside the link, whose label already gives the count, so the link's visible text is just the month.
  count.setAttribute("aria-hidden", "true");

  const year = element("span", "text-[0.65rem] leading-3 h-3 text-gray-500", yearLabelForBar(entry.month, index) ?? "");
  year.setAttribute("aria-hidden", "true");
  column.append(count, target, year);
  return column;
}

/** Fills the card with one labelled, linked column per month. */
export function renderTimeline(
  root: HTMLElement,
  months: TimelineMonth[],
  context: TimelineRenderContext,
): void {
  const maxCount = Math.max(...months.map((entry) => entry.newsletterCount));
  const summary = root.querySelector<HTMLElement>("[data-timeline-summary]");
  const bars = root.querySelector<HTMLElement>("[data-timeline-bars]");
  if (!summary || !bars) throw new Error("Search timeline markup is incomplete");

  summary.textContent = describeTimeline(months);
  bars.replaceChildren(
    ...months.map((entry, index) => buildMonthColumn(entry, index, maxCount, context)),
  );
  bars.removeAttribute("aria-busy");
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

async function loadTimeline(
  root: HTMLElement,
  query: string,
  range: TimelineMonthRange,
): Promise<void> {
  const months = clipTimelineToRange(await fetchTimelineMonths(query), range);
  if (months.length === 0) {
    root.remove();
    return;
  }
  renderTimeline(root, months, {
    searchUrl: new URL(window.location.href),
    currentMonth: getChicagoMonth(new Date()),
    selectedMonth: root.dataset.selectedMonth ?? null,
  });
}

export function initSearchTimeline(): void {
  const root = document.querySelector<HTMLElement>(ROOT_SELECTOR);
  const query = root?.dataset.query;
  const startMonth = root?.dataset.startMonth;
  if (!root || !query || !startMonth) return;

  void loadTimeline(root, query, { startMonth, endMonth: root.dataset.endMonth ?? null });
}
