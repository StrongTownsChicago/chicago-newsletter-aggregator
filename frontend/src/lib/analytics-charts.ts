// Observable Plot chart builders for the /analytics dashboard (browser only).
// Colors follow the dataviz reference palette: one blue hue for magnitude,
// blue <-> red with a gray midpoint for above/below the city average.
import * as Plot from "@observablehq/plot";
import {
  buildSearchUrl,
  monthDateRange,
  type DistinctiveTerm,
  type RisingTerm,
  type SearchLinkParams,
  type SourceCoverage,
  type TermMonthPoint,
  type TermWardRow,
  type TopicMonthPoint,
  type WardMonthCount,
  type WardRelevance,
  type WardTopicCell,
} from "./analytics";
import { humanizeIdentifier } from "./format";

export const CHART_COLORS = {
  series: "#2a78d6",
  seriesLight: "#86b6ef",
  seriesDark: "#1c5cab",
  sequentialLow: "#cde2fb",
  sequentialHigh: "#104281",
  divergingLow: "#e34948",
  divergingMid: "#f0efec",
  divergingHigh: "#2a78d6",
  ink: "#0b0b0b",
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
const HEATMAP_CELL_WIDTH = 22;
const HEATMAP_ROW_HEIGHT = 28;
const HEATMAP_LABEL_MARGIN = 280;
/** Heatmap colors clamp at log2 ratio +/-2: four times or a quarter of the city rate. */
const LOG_RATIO_LABELS: Record<number, string> = { [-2]: "¼×", [-1]: "½×", 0: "same", 1: "2×", 2: "4×" };
const MAX_LOG_RATIO = 2;

export const formatPercent = (value: number): string => `${(value * 100).toFixed(1)}%`;
export const formatWard = (ward: string): string => `Ward ${ward}`;
export const formatOptionalShare = (share: number | null): string =>
  share === null ? "too few newsletters that month for a share" : formatPercent(share);
/** Lifts against near-zero baselines are unstable; above this, just say "over". */
const MAX_DISPLAYED_LIFT = 100;
export const formatLift = (lift: number): string =>
  lift > MAX_DISPLAYED_LIFT ? `>${MAX_DISPLAYED_LIFT}×` : `${lift.toFixed(1)}×`;
const yearTickFormat = (month: string): string => (month.endsWith("-01") ? month.slice(0, 4) : "");

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

/** A legend row of colored dots for charts whose series are encoded by color. */
function renderDotKey(items: { label: string; color: string }[]): HTMLElement {
  const key = document.createElement("div");
  key.className = "flex flex-wrap gap-4 text-xs text-gray-600 mb-2";
  for (const item of items) {
    const entry = document.createElement("span");
    entry.className = "inline-flex items-center gap-1.5";
    const swatch = document.createElement("span");
    swatch.className = "inline-block w-2.5 h-2.5 rounded-full";
    swatch.style.backgroundColor = item.color;
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

export function renderWardTopicHeatmap(
  cells: WardTopicCell[],
  selectedTopic: string | null,
  searchScope: SearchLinkParams,
  width: number,
): Element {
  const wards = [...new Set(cells.map((cell) => cell.ward))];
  const topics = [...new Set(cells.map((cell) => cell.topic))];
  const plot = Plot.plot({
    ...baseOptions(Math.max(width, wards.length * HEATMAP_CELL_WIDTH + HEATMAP_LABEL_MARGIN + 10)),
    height: topics.length * HEATMAP_ROW_HEIGHT + 70,
    marginLeft: HEATMAP_LABEL_MARGIN,
    marginBottom: 40,
    padding: 0.08,
    x: { label: "Ward", domain: wards },
    y: { label: null, domain: topics, tickFormat: humanizeIdentifier },
    color: {
      type: "linear",
      domain: [-MAX_LOG_RATIO, 0, MAX_LOG_RATIO],
      range: [CHART_COLORS.divergingLow, CHART_COLORS.divergingMid, CHART_COLORS.divergingHigh],
      clamp: true,
      label: "Topic share vs city average",
      ticks: Object.keys(LOG_RATIO_LABELS).map(Number),
      tickFormat: (value: number) => LOG_RATIO_LABELS[value] ?? "",
    },
    marks: [
      Plot.cell(cells, {
        x: "ward",
        y: "topic",
        fill: "logRatio",
        rx: 2,
        href: (cell: WardTopicCell) => buildSearchUrl({ ...searchScope, ward: cell.ward, topic: cell.topic }),
        title: (cell: WardTopicCell) =>
          `${formatWard(cell.ward)} · ${humanizeIdentifier(cell.topic)}\n` +
          `${cell.wardTopicNewsletters} of ${cell.wardNewsletters} newsletters (${formatPercent(cell.wardShare)})\n` +
          `City: ${formatPercent(cell.cityShare)}\nClick to search`,
        tip: true,
      }),
      ...(selectedTopic
        ? [
            Plot.cell(
              cells.filter((cell) => cell.topic === selectedTopic),
              { x: "ward", y: "topic", stroke: CHART_COLORS.ink, strokeWidth: 1.5, fill: "none" },
            ),
          ]
        : []),
    ],
  });
  return withColorLegend(plot);
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
    renderDotKey([
      { label: baselineLabel, color: CHART_COLORS.seriesLight },
      { label: latestLabel, color: CHART_COLORS.seriesDark },
    ]),
    plot,
  );
}

export function renderCadenceHeatmap(
  counts: WardMonthCount[],
  months: string[],
  searchScope: SearchLinkParams,
  width: number,
): Element {
  const wards = [...new Set(counts.map((count) => count.ward))];
  const plot = Plot.plot({
    ...baseOptions(width),
    height: wards.length * ROW_HEIGHT + AXIS_BAND + TOP_AXIS_MARGIN,
    marginTop: TOP_AXIS_MARGIN,
    marginLeft: 70,
    padding: 0.06,
    x: { type: "band", domain: months, label: null, tickFormat: yearTickFormat, axis: "both" },
    y: { label: null, domain: wards, tickFormat: formatWard },
    color: {
      type: "linear",
      range: [CHART_COLORS.sequentialLow, CHART_COLORS.sequentialHigh],
      label: "Newsletters per month",
    },
    marks: [
      Plot.cell(counts, {
        x: "month",
        y: "ward",
        fill: "newsletters",
        rx: 2,
        href: (count: WardMonthCount) => buildSearchUrl({ ...searchScope, ...monthDateRange(count.month), ward: count.ward }),
        title: (count: WardMonthCount) => `${formatWard(count.ward)} · ${count.month}\n${count.newsletters} newsletters`,
        tip: true,
      }),
    ],
  });
  return withColorLegend(plot);
}

export function renderRelevanceByWard(rows: WardRelevance[], searchScope: SearchLinkParams, width: number): Element {
  return Plot.plot({
    ...baseOptions(width),
    height: rows.length * ROW_HEIGHT + AXIS_BAND + TOP_AXIS_MARGIN,
    marginTop: TOP_AXIS_MARGIN,
    marginLeft: 70,
    marginRight: 70,
    x: { label: "Average relevance score (0-10)", domain: [0, 10], grid: true, axis: "both" },
    y: { label: null, domain: rows.map((row) => row.ward), tickFormat: formatWard, padding: 1 - MAX_BAR_THICKNESS },
    marks: [
      Plot.barX(rows, {
        x: "averageRelevance",
        y: "ward",
        fill: CHART_COLORS.series,
        rx: 4,
        href: (row: WardRelevance) => buildSearchUrl({ ...searchScope, ward: row.ward }),
        title: (row: WardRelevance) =>
          `${formatWard(row.ward)}: ${row.averageRelevance.toFixed(2)} average over ${row.scoredNewsletters} scored newsletters\nClick to search`,
        tip: true,
      }),
      Plot.text(rows, {
        x: "averageRelevance",
        y: "ward",
        text: (row: WardRelevance) => `${row.averageRelevance.toFixed(1)} (n=${row.scoredNewsletters})`,
        textAnchor: "start",
        dx: 6,
        fill: CHART_COLORS.mutedInk,
      }),
      Plot.ruleX([0], { stroke: CHART_COLORS.baseline }),
    ],
  });
}

export function renderCoverage(sources: SourceCoverage[], width: number): Element {
  // Noon avoids time-zone shifts moving a date to the neighboring day.
  const rows = sources.map((source) => ({
    ...source,
    label: sourceLabel(source),
    first: new Date(`${source.first_date}T12:00:00`),
    last: new Date(`${source.last_date}T12:00:00`),
  }));
  type Row = (typeof rows)[number];
  return Plot.plot({
    ...baseOptions(width),
    height: rows.length * ROW_HEIGHT + AXIS_BAND + TOP_AXIS_MARGIN,
    marginTop: TOP_AXIS_MARGIN,
    marginLeft: 230,
    marginRight: 50,
    x: { type: "utc", label: null, grid: true, axis: "both" },
    y: { label: null, domain: rows.map((row) => row.label) },
    marks: [
      Plot.ruleY(rows, { y: "label", x1: "first", x2: "last", stroke: CHART_COLORS.series, strokeWidth: 2 }),
      Plot.dot(rows, {
        x: "first",
        y: "label",
        r: 4,
        fill: CHART_COLORS.series,
        stroke: CHART_COLORS.surface,
        strokeWidth: 2,
        title: (row: Row) => `${row.label}\n${row.newsletters} newsletters, ${row.first_date} to ${row.last_date}`,
        tip: true,
      }),
      Plot.text(rows, {
        x: "last",
        y: "label",
        text: (row: Row) => String(row.newsletters),
        textAnchor: "start",
        dx: 6,
        fill: CHART_COLORS.mutedInk,
      }),
    ],
  });
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
