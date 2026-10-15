// Observable Plot chart builders for the /analytics dashboard (browser only).
// Colors follow the dataviz reference palette: one blue hue for magnitude,
// gray for context (months before a ward was tracked).
import * as Plot from "@observablehq/plot";
import {
  buildSearchUrl,
  formatMonth,
  monthDateRange,
  type CoverageCell,
  type DistinctiveTerm,
  type RisingTerm,
  type SearchLinkParams,
  type SourceCoverage,
  type TermMonthPoint,
  type TermWardRow,
  type TopicMonthPoint,
} from "./analytics";

export const CHART_COLORS = {
  series: "#2a78d6",
  seriesLight: "#86b6ef",
  seriesDark: "#1c5cab",
  sequentialLow: "#cde2fb",
  sequentialHigh: "#104281",
  untracked: "#ebeae6",
  mutedInk: "#52514e",
  baseline: "#c3c2b7",
  surface: "#ffffff",
};

const FONT = 'system-ui, -apple-system, "Segoe UI", sans-serif';
const ROW_HEIGHT = 18;
const BAR_ROW_HEIGHT = 26;
const AXIS_BAND = 40;
const TOP_AXIS_MARGIN = 30;
const LEGEND_MARGIN = 16;
/** Bars fill at most this fraction of their band; the rest is air. */
const MAX_BAR_THICKNESS = 0.7;
/** Coverage grid columns never get narrower than this; wider grids scroll. */
const MIN_COVERAGE_CELL_WIDTH = 12;
/** With at most this many months the coverage grid labels every month, otherwise only years. */
const MAX_LABELED_MONTHS = 18;

export const formatPercent = (value: number): string => `${(value * 100).toFixed(1)}%`;
export const formatWard = (ward: string): string => `Ward ${ward}`;
export const formatOptionalShare = (share: number | null): string =>
  share === null ? "too few newsletters that month for a share" : formatPercent(share);
/** Lifts against near-zero baselines are unstable; above this, just say "over". */
const MAX_DISPLAYED_LIFT = 100;
export const formatLift = (lift: number): string =>
  lift > MAX_DISPLAYED_LIFT ? `>${MAX_DISPLAYED_LIFT}×` : `${lift.toFixed(1)}×`;
const yearTickFormat = (month: string): string => (month.endsWith("-01") ? month.slice(0, 4) : "");

/** Short month names, with the year under the first month and every January. */
function monthTickFormat(months: string[]): (month: string) => string {
  if (months.length > MAX_LABELED_MONTHS) return yearTickFormat;
  return (month) => {
    const [name, year] = formatMonth(month).split(" ");
    return month === months[0] || month.endsWith("-01") ? `${name}\n${year}` : name;
  };
}

export function sourceLabel(source: Pick<SourceCoverage, "name" | "ward">): string {
  return source.ward ? `${source.name} (Ward ${source.ward})` : source.name;
}

function baseOptions(width: number): Plot.PlotOptions {
  // maxWidth none: wide charts scroll inside their container instead of shrinking illegibly.
  return { width, style: { fontFamily: FONT, fontSize: "12px", color: CHART_COLORS.mutedInk, maxWidth: "none" } };
}

/** Render the color legend outside the plot so its end labels are never clipped. */
function withColorLegend(plot: ReturnType<typeof Plot.plot>): HTMLElement {
  const wrapper = document.createElement("div");
  const legend = plot.legend("color", {
    marginLeft: LEGEND_MARGIN,
    marginRight: LEGEND_MARGIN,
    style: { fontFamily: FONT },
  });
  if (legend) wrapper.append(legend);
  wrapper.append(plot);
  return wrapper;
}

interface KeyItem {
  label: string;
  color: string;
  /** Outline color, for swatches that would otherwise vanish on white. */
  outline?: string;
}

/** A legend row of colored swatches (dots or squares) for categories encoded by color. */
function renderKey(items: KeyItem[], shape: "dot" | "square" = "dot"): HTMLElement {
  const key = document.createElement("div");
  key.className = "flex flex-wrap gap-4 text-xs text-gray-600 mb-2";
  for (const item of items) {
    const entry = document.createElement("span");
    entry.className = "inline-flex items-center gap-1.5";
    const swatch = document.createElement("span");
    swatch.className = `inline-block w-2.5 h-2.5 ${shape === "dot" ? "rounded-full" : "rounded-sm"}`;
    swatch.style.backgroundColor = item.color;
    if (item.outline) swatch.style.boxShadow = `inset 0 0 0 1px ${item.outline}`;
    entry.append(swatch, item.label);
    key.append(entry);
  }
  return key;
}

function wrap(...nodes: Node[]): HTMLElement {
  const wrapper = document.createElement("div");
  wrapper.append(...nodes);
  return wrapper;
}

/** Line + wash for a monthly share series, with a crosshair tooltip. */
function monthlyShareMarks<T extends { month: string; share: number | null }>(
  points: T[],
  describe: (point: T) => string,
): Plot.Markish[] {
  return [
    Plot.areaY(points, { x: "month", y: "share", fill: CHART_COLORS.series, fillOpacity: 0.1 }),
    Plot.lineY(points, { x: "month", y: "share", stroke: CHART_COLORS.series, strokeWidth: 2 }),
    Plot.ruleY([0], { stroke: CHART_COLORS.baseline }),
    Plot.ruleX(points, Plot.pointerX({ x: "month", stroke: CHART_COLORS.baseline })),
    Plot.dot(
      points,
      Plot.pointerX({
        x: "month",
        y: "share",
        r: 4,
        fill: CHART_COLORS.series,
        stroke: CHART_COLORS.surface,
        strokeWidth: 2,
      }),
    ),
    Plot.tip(
      points,
      Plot.pointerX({ x: "month", y: (point: T) => point.share ?? 0, title: describe }),
    ),
  ];
}

export function renderTermTimeline(points: TermMonthPoint[], width: number): Element {
  return Plot.plot({
    ...baseOptions(width),
    height: 260,
    marginLeft: 48,
    x: { type: "band", label: null, tickFormat: yearTickFormat },
    y: { label: "Share of newsletters (%)", percent: true, grid: true, nice: true },
    marks: monthlyShareMarks(
      points,
      (point) =>
        `${point.month}\n${point.mentions} of ${point.newsletters} newsletters (${formatOptionalShare(point.share)})`,
    ),
  });
}

export function renderTopicTrend(points: TopicMonthPoint[], maxShare: number, width: number): Element {
  return Plot.plot({
    ...baseOptions(width),
    height: 140,
    marginLeft: 40,
    x: { type: "band", label: null, tickFormat: yearTickFormat },
    y: { label: null, percent: true, domain: [0, maxShare * 100 || 1], ticks: 3, grid: true },
    marks: monthlyShareMarks(
      points,
      (point) =>
        `${point.month}\n${point.newsletters} of ${point.monthNewsletters} newsletters (${formatOptionalShare(point.share)})`,
    ),
  });
}

export function renderTermWards(
  rows: TermWardRow[],
  term: string,
  searchScope: SearchLinkParams,
  width: number,
): Element {
  return Plot.plot({
    ...baseOptions(width),
    height: rows.length * BAR_ROW_HEIGHT + AXIS_BAND,
    marginLeft: 70,
    marginRight: 90,
    x: { label: "Newsletters mentioning the term", grid: true },
    y: { label: null, domain: rows.map((row) => row.ward), tickFormat: formatWard, padding: 1 - MAX_BAR_THICKNESS },
    marks: [
      Plot.barX(rows, {
        x: "mentions",
        y: "ward",
        fill: CHART_COLORS.series,
        rx: 4,
        href: (row: TermWardRow) => buildSearchUrl({ ...searchScope, q: term, ward: row.ward }),
        title: (row: TermWardRow) =>
          `${formatWard(row.ward)}: ${row.mentions} of ${row.newsletters} newsletters (${formatPercent(row.share)})\nClick to search`,
        tip: true,
      }),
      Plot.text(rows, {
        x: "mentions",
        y: "ward",
        text: (row: TermWardRow) => `${row.mentions} · ${formatPercent(row.share)}`,
        textAnchor: "start",
        dx: 6,
        fill: CHART_COLORS.mutedInk,
      }),
      Plot.ruleX([0], { stroke: CHART_COLORS.baseline }),
    ],
  });
}

export function renderDistinctiveTerms(terms: DistinctiveTerm[], ward: string, width: number): Element {
  return Plot.plot({
    ...baseOptions(width),
    height: terms.length * BAR_ROW_HEIGHT + AXIS_BAND,
    marginLeft: 170,
    marginRight: 60,
    x: { label: "Distinctiveness score (bar labels: times more likely than the rest of the city)", grid: true },
    y: { label: null, domain: terms.map((item) => item.term), padding: 1 - MAX_BAR_THICKNESS },
    marks: [
      Plot.barX(terms, {
        x: "score",
        y: "term",
        fill: CHART_COLORS.series,
        rx: 4,
        href: (item: DistinctiveTerm) => buildSearchUrl({ q: item.term, ward }),
        title: (item: DistinctiveTerm) =>
          `"${item.term}" in ${item.ward_newsletters} ${formatWard(ward)} newsletters (${formatPercent(item.ward_share)})\n` +
          `Rest of city: ${formatPercent(item.rest_share)} · ${formatLift(item.lift)} more likely\nClick to search`,
        tip: true,
      }),
      Plot.text(terms, {
        x: "score",
        y: "term",
        text: (item: DistinctiveTerm) => formatLift(item.lift),
        textAnchor: "start",
        dx: 6,
        fill: CHART_COLORS.mutedInk,
      }),
      Plot.ruleX([0], { stroke: CHART_COLORS.baseline }),
    ],
  });
}

export function renderRisingTerms(terms: RisingTerm[], baselineLabel: string, latestLabel: string, width: number): Element {
  const plot = Plot.plot({
    ...baseOptions(width),
    height: terms.length * BAR_ROW_HEIGHT + AXIS_BAND + TOP_AXIS_MARGIN,
    marginTop: TOP_AXIS_MARGIN,
    marginLeft: 170,
    marginRight: 30,
    x: { label: "Share of newsletters (%)", percent: true, grid: true, axis: "both" },
    y: { label: null, domain: terms.map((item) => item.term) },
    marks: [
      Plot.link(terms, {
        x1: "baseline_share",
        x2: "latest_share",
        y1: "term",
        y2: "term",
        stroke: CHART_COLORS.seriesLight,
        strokeWidth: 2,
      }),
      Plot.dot(terms, {
        x: "baseline_share",
        y: "term",
        r: 4,
        fill: CHART_COLORS.seriesLight,
        stroke: CHART_COLORS.surface,
        strokeWidth: 2,
      }),
      Plot.dot(terms, {
        x: "latest_share",
        y: "term",
        r: 5,
        fill: CHART_COLORS.seriesDark,
        stroke: CHART_COLORS.surface,
        strokeWidth: 2,
        href: (item: RisingTerm) => buildSearchUrl({ q: item.term }),
        title: (item: RisingTerm) =>
          `"${item.term}"\n${latestLabel}: ${item.latest_newsletters} newsletters from ${item.latest_sources} sources (${formatPercent(item.latest_share)})\n` +
          `${baselineLabel}: ${item.baseline_newsletters} newsletters (${formatPercent(item.baseline_share)})\nClick to search`,
        tip: true,
      }),
    ],
  });
  return wrap(
    renderKey([
      { label: baselineLabel, color: CHART_COLORS.seriesLight },
      { label: latestLabel, color: CHART_COLORS.seriesDark },
    ]),
    plot,
  );
}

export function renderCoverageGrid(
  cells: CoverageCell[],
  wards: string[],
  months: string[],
  searchScope: SearchLinkParams,
  width: number,
): Element {
  const marginLeft = 70;
  const marginRight = 10;
  const cellsByStatus = (status: CoverageCell["status"]) => cells.filter((cell) => cell.status === status);
  const wardsWithoutNewsletters = wards.filter((ward) =>
    cells.every((cell) => cell.ward !== ward || cell.status === "untracked"),
  );
  const plot = Plot.plot({
    ...baseOptions(Math.max(width, months.length * MIN_COVERAGE_CELL_WIDTH + marginLeft + marginRight)),
    height: wards.length * ROW_HEIGHT + AXIS_BAND + TOP_AXIS_MARGIN,
    marginTop: TOP_AXIS_MARGIN,
    marginLeft,
    marginRight,
    marginBottom: AXIS_BAND,
    padding: 0.08,
    x: { type: "band", domain: months, label: null, tickFormat: monthTickFormat(months), axis: "both" },
    y: { label: null, domain: wards, tickFormat: formatWard },
    color: {
      type: "linear",
      range: [CHART_COLORS.sequentialLow, CHART_COLORS.sequentialHigh],
      label: "Newsletters received that month",
    },
    marks: [
      Plot.cell(cellsByStatus("untracked"), {
        x: "month",
        y: "ward",
        fill: CHART_COLORS.untracked,
        rx: 2,
        title: (cell: CoverageCell) => `${formatWard(cell.ward)} · ${formatMonth(cell.month)}\nNot tracked yet`,
        tip: true,
      }),
      Plot.cell(cellsByStatus("silent"), {
        x: "month",
        y: "ward",
        fill: CHART_COLORS.surface,
        stroke: CHART_COLORS.baseline,
        inset: 0.5,
        rx: 2,
        title: (cell: CoverageCell) =>
          `${formatWard(cell.ward)} · ${formatMonth(cell.month)}\nTracked, no newsletters received`,
        tip: true,
      }),
      Plot.cell(cellsByStatus("received"), {
        x: "month",
        y: "ward",
        fill: "newsletters",
        rx: 2,
        href: (cell: CoverageCell) => buildSearchUrl({ ...searchScope, ...monthDateRange(cell.month), ward: cell.ward }),
        title: (cell: CoverageCell) =>
          `${formatWard(cell.ward)} · ${formatMonth(cell.month)}\n${cell.newsletters} newsletter${cell.newsletters === 1 ? "" : "s"}\nClick to search`,
        tip: true,
      }),
      Plot.text(wardsWithoutNewsletters, {
        x: () => months[0],
        y: (ward: string) => ward,
        text: () => "No newsletters archived",
        textAnchor: "start",
        frameAnchor: "left",
        dx: 4,
        fill: CHART_COLORS.mutedInk,
      }),
    ],
  });
  return wrap(
    renderKey(
      [
        { label: "Not tracked yet (before the ward's first archived newsletter)", color: CHART_COLORS.untracked },
        { label: "Tracked, none received", color: CHART_COLORS.surface, outline: CHART_COLORS.baseline },
      ],
      "square",
    ),
    withColorLegend(plot),
  );
}

// ---------------------------------------------------------------------------
// Table views: every chart has an accessible table twin.

export interface TableColumn<T> {
  label: string;
  value: (row: T) => string | number;
  numeric?: boolean;
}

export function renderTable<T>(columns: TableColumn<T>[], rows: T[]): HTMLTableElement {
  const table = document.createElement("table");
  table.className = "min-w-full text-sm text-left";
  const headerRow = table.createTHead().insertRow();
  for (const column of columns) {
    const cell = document.createElement("th");
    cell.textContent = column.label;
    cell.className = `px-2 py-1 font-semibold text-gray-700 border-b border-gray-200 ${column.numeric ? "text-right" : ""}`;
    headerRow.appendChild(cell);
  }
  const body = table.createTBody();
  for (const row of rows) {
    const tableRow = body.insertRow();
    for (const column of columns) {
      const cell = tableRow.insertCell();
      cell.textContent = String(column.value(row));
      cell.className = `px-2 py-1 border-b border-gray-100 text-gray-700 ${column.numeric ? "text-right tabular-nums" : ""}`;
    }
  }
  return table;
}
