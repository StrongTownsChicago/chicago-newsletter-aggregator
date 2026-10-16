// Observable Plot chart builders for the /analytics dashboard (browser only).
// Colors follow the dataviz reference palette: one blue hue for magnitude,
// blue/red around a gray midpoint for above/below average, gray for context.
import * as Plot from "@observablehq/plot";
import {
  buildSearchUrl,
  formatMonth,
  monthDateRange,
  monthTickLabeler,
  type CoverageCell,
  type DistinctiveTerm,
  type LensReachCell,
  type LensWardCell,
  type RisingTerm,
  type SearchLinkParams,
  type SourceCoverage,
  type TermMonthPoint,
  type TermWardRow,
} from "./analytics";
import { EXPORT_SWATCH_ATTRIBUTE, EXPORT_TEXT_ATTRIBUTE } from "./chart-export";
import { formatPointChange, reachDeviation, type TopicTrendPoint } from "./analytics-topic-trends";
import type { WardTopicMonthCell, WardTopicSummary } from "./analytics-ward-profile";

export const CHART_COLORS = {
  series: "#2a78d6",
  seriesLight: "#86b6ef",
  seriesDark: "#1c5cab",
  sequentialLow: "#e6eefa",
  sequentialHigh: "#104281",
  divergingBelow: "#b3322f",
  divergingMidpoint: "#f0efec",
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
/** Civic calendar columns never get narrower than this, so ward counts fit; wider calendars scroll. */
const MIN_CALENDAR_CELL_WIDTH = 32;
/** Approximate width of one 12px label character, for sizing label margins. */
const LABEL_CHARACTER_WIDTH = 6.5;
/** Space between a y-axis label and the plot, including the tick. */
const AXIS_TICK_ROOM = 14;
const CALENDAR_ROW_HEIGHT = 26;
/** Calendar labels switch to light ink beyond this fraction of the largest deviation. */
const CALENDAR_DARK_CELL_FRACTION = 0.55;
/** The calendar's color scale spans at least ±this deviation, so tiny wobbles stay pale. */
const MIN_CALENDAR_DEVIATION = 0.1;
/** Opacity of calendar cells resting on too few wards or a partial month. */
const FADED_OPACITY = 0.35;
/** Coverage grid rows, compact: the grid is reference, not a headline. */
const COVERAGE_ROW_HEIGHT = 11;
const COVERAGE_FONT_SIZE = "10px";
const SPARKLINE_WIDTH = 120;
const SPARKLINE_HEIGHT = 28;
const TREND_HEIGHT = 200;
/** Right margin of the rising terms chart when a "seasonal" tag may sit past the last dot. */
const SEASONAL_TAG_MARGIN = 64;

export const formatPercent = (value: number): string => `${(value * 100).toFixed(1)}%`;
export const formatWard = (ward: string): string => `Ward ${ward}`;
export const formatOptionalShare = (share: number | null): string =>
  share === null ? "too few newsletters that month for a share" : formatPercent(share);
/** Lifts against near-zero baselines are unstable; above this, just say "over". */
const MAX_DISPLAYED_LIFT = 100;
export const formatLift = (lift: number): string =>
  lift > MAX_DISPLAYED_LIFT ? `>${MAX_DISPLAYED_LIFT}×` : `${lift.toFixed(1)}×`;

/** A band x axis of consecutive months, labeled to fit the plot's inner width. */
function monthAxis(months: string[], width: number, marginLeft: number, marginRight: number): Plot.ScaleOptions {
  return {
    type: "band",
    domain: months,
    label: null,
    tickFormat: monthTickLabeler(months, width - marginLeft - marginRight),
  };
}

export function sourceLabel(source: Pick<SourceCoverage, "name" | "ward">): string {
  return source.ward ? `${source.name} (Ward ${source.ward})` : source.name;
}

function baseOptions(width: number, fontSize = "12px"): Plot.PlotOptions {
  // maxWidth none: wide charts scroll inside their container instead of shrinking illegibly.
  return { width, style: { fontFamily: FONT, fontSize, color: CHART_COLORS.mutedInk, maxWidth: "none" } };
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
    swatch.setAttribute(EXPORT_SWATCH_ATTRIBUTE, item.outline ?? "");
    const label = document.createElement("span");
    label.setAttribute(EXPORT_TEXT_ATTRIBUTE, "");
    label.textContent = item.label;
    entry.append(swatch, label);
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
  const marginLeft = 48;
  const marginRight = 20;
  return Plot.plot({
    ...baseOptions(width),
    height: 260 + AXIS_BAND,
    marginLeft,
    marginRight,
    marginBottom: AXIS_BAND,
    x: monthAxis(points.map((point) => point.month), width, marginLeft, marginRight),
    y: { label: "Share of newsletters (%)", percent: true, grid: true, nice: true },
    marks: monthlyShareMarks(
      points,
      (point) =>
        `${point.month}\n${point.mentions} of ${point.newsletters} newsletters (${formatOptionalShare(point.share)})`,
    ),
  });
}

/** "14 of 38 wards (37%)": a ward-reach cell with its denominator. */
export function describeWardReach(cell: LensReachCell): string {
  return cell.share === null
    ? "no ward sent newsletters"
    : `${cell.wardsMentioning} of ${cell.activeWards} wards (${formatPercent(cell.share)})`;
}

/** One topic's monthly ward reach on a tight y scale, with its average as a dashed rule. */
export function renderReachTrend(
  points: LensReachCell[],
  months: string[],
  domain: [number, number],
  averageShare: number | null,
  width: number,
): Element {
  const marginLeft = 40;
  const marginRight = 20;
  return Plot.plot({
    ...baseOptions(width),
    height: TREND_HEIGHT + AXIS_BAND,
    marginLeft,
    marginRight,
    marginBottom: AXIS_BAND,
    x: monthAxis(months, width, marginLeft, marginRight),
    y: {
      label: null,
      percent: true,
      domain: domain.map((value) => value * 100),
      ticks: 4,
      grid: true,
      tickFormat: (value: number) => `${value}%`,
    },
    marks: [
      ...(averageShare === null
        ? []
        : [Plot.ruleY([averageShare], { stroke: CHART_COLORS.mutedInk, strokeDasharray: "4,3" })]),
      Plot.lineY(points, { x: "month", y: "share", stroke: CHART_COLORS.series, strokeWidth: 2 }),
      Plot.dot(points, { x: "month", y: "share", r: 3, fill: CHART_COLORS.series }),
      Plot.ruleX(points, Plot.pointerX({ x: "month", stroke: CHART_COLORS.baseline })),
      Plot.tip(
        points,
        Plot.pointerX({
          x: "month",
          y: (point: LensReachCell) => point.share ?? 0,
          title: (point: LensReachCell) => `${formatMonth(point.month)}\n${describeWardReach(point)}`,
        }),
      ),
    ],
  });
}

/** A tiny line of monthly ward reach on its own tight scale, ending in a dot. */
export function renderSparkline(points: TopicTrendPoint[], domain: [number, number], ariaLabel: string): Element {
  const shown = points.filter((point) => point.share !== null);
  return Plot.plot({
    width: SPARKLINE_WIDTH,
    height: SPARKLINE_HEIGHT,
    margin: 4,
    ariaLabel,
    style: { maxWidth: "none" },
    x: { type: "point", domain: points.map((point) => point.month), axis: null },
    y: { domain, axis: null },
    marks: [
      Plot.lineY(points, { x: "month", y: "share", stroke: CHART_COLORS.series, strokeWidth: 1.5 }),
      Plot.dot(shown.slice(-1), { x: "month", y: "share", r: 2.5, fill: CHART_COLORS.series }),
    ],
  });
}

export interface CivicCalendarOptions {
  /** Topics in row order. */
  lenses: { id: string; label: string }[];
  months: string[];
  averageByLens: Map<string, number | null>;
  selectedLens: string | null;
  /** Why a cell is faded (too few wards, partial month), or null. */
  fadeReason: (cell: LensReachCell) => string | null;
  /** Called with a topic id when its row label or a cell is clicked. */
  onSelectTopic: (lensId: string) => void;
}

/**
 * The civic calendar: topic × month cells shaded by how far the month's ward
 * reach sits above (blue) or below (red) the topic's own average, labeled
 * with the ward count.
 */
export function renderCivicCalendar(cells: LensReachCell[], options: CivicCalendarOptions, width: number): Element {
  const { lenses, months, averageByLens, selectedLens, fadeReason, onSelectTopic } = options;
  const marginLeft = longestLabelMargin(lenses.map((lens) => lens.label));
  const marginRight = 10;
  const plotWidth = Math.max(width, months.length * MIN_CALENDAR_CELL_WIDTH + marginLeft + marginRight);
  const labelOf = new Map(lenses.map((lens) => [lens.id, lens.label]));
  const rows = cells
    .filter((cell) => cell.share !== null)
    .map((cell) => ({
      ...cell,
      deviation: reachDeviation(cell, averageByLens.get(cell.lens) ?? null),
      fade: fadeReason(cell),
    }));
  type CalendarRow = (typeof rows)[number];
  const largestDeviation = Math.max(
    MIN_CALENDAR_DEVIATION,
    ...rows.filter((row) => !row.fade).map((row) => Math.abs(row.deviation ?? 0)),
  );
  const isDark = (row: CalendarRow) =>
    !row.fade && Math.abs(row.deviation ?? 0) >= largestDeviation * CALENDAR_DARK_CELL_FRACTION;
  const describe = (row: CalendarRow) => {
    const average = averageByLens.get(row.lens) ?? null;
    const comparison =
      row.deviation === null || average === null
        ? ""
        : `\n${formatPointChange(row.deviation)} vs average (${formatPercent(average)})`;
    return `${labelOf.get(row.lens)} · ${formatMonth(row.month)}\n${describeWardReach(row)}${comparison}${row.fade ? `\n${row.fade}` : ""}`;
  };
  const plot = Plot.plot({
    ...baseOptions(plotWidth),
    height: lenses.length * CALENDAR_ROW_HEIGHT + AXIS_BAND + TOP_AXIS_MARGIN,
    marginTop: TOP_AXIS_MARGIN,
    marginLeft,
    marginRight,
    marginBottom: AXIS_BAND,
    padding: 0.06,
    x: { ...monthAxis(months, plotWidth, marginLeft, marginRight), axis: "both" },
    y: {
      label: null,
      domain: lenses.map((lens) => lens.id),
      tickFormat: (id: string) => labelOf.get(id) ?? id,
    },
    color: {
      type: "linear",
      domain: [-largestDeviation, 0, largestDeviation],
      range: [CHART_COLORS.divergingBelow, CHART_COLORS.divergingMidpoint, CHART_COLORS.sequentialHigh],
      clamp: true,
      label: "Share of wards vs the topic's average month",
      tickFormat: (value: number) => formatPointChange(value),
    },
    marks: [
      Plot.cell(rows, {
        x: "month",
        y: "lens",
        fill: (row: CalendarRow) => row.deviation ?? 0,
        fillOpacity: (row: CalendarRow) => (row.fade ? FADED_OPACITY : 1),
        rx: 2,
        title: describe,
        tip: true,
      }),
      Plot.text(rows, {
        x: "month",
        y: "lens",
        text: (row: CalendarRow) => String(row.wardsMentioning),
        fill: (row: CalendarRow) => (isDark(row) ? CHART_COLORS.surface : CHART_COLORS.mutedInk),
        fontSize: 11,
      }),
      ...(selectedLens
        ? [
            Plot.cell(
              months.map((month) => ({ month, lens: selectedLens })),
              { x: "month", y: "lens", fill: "none", stroke: CHART_COLORS.mutedInk, strokeWidth: 1.5 },
            ),
          ]
        : []),
    ],
  });
  makeTopicsClickable(plot, lenses, onSelectTopic);
  return withColorLegend(plot);
}

/** Row labels and cells select their topic; `plot.value` is the cell under the pointer. */
function makeTopicsClickable(
  plot: ReturnType<typeof Plot.plot>,
  lenses: { id: string }[],
  onSelectTopic: (lensId: string) => void,
): void {
  plot.querySelectorAll<SVGElement>('[aria-label="cell"]').forEach((cells) => {
    cells.style.cursor = "pointer";
  });
  plot.addEventListener("click", () => {
    const pointed = plot.value as { lens?: string } | null;
    if (pointed?.lens) onSelectTopic(pointed.lens);
  });
  plot.querySelectorAll<SVGTextElement>('[aria-label="y-axis tick label"] text').forEach((label, index) => {
    const lens = lenses[index];
    if (!lens) return;
    label.style.cursor = "pointer";
    label.addEventListener("click", (event) => {
      event.stopPropagation();
      onSelectTopic(lens.id);
    });
  });
}

const LENS_WARD_COLORS: Record<LensWardCell["status"], { fill: string; stroke?: string }> = {
  mentioned: { fill: CHART_COLORS.series },
  not_mentioned: { fill: CHART_COLORS.surface, stroke: CHART_COLORS.baseline },
  no_newsletter: { fill: CHART_COLORS.untracked },
};

export const LENS_WARD_STATUS_LABELS: Record<LensWardCell["status"], string> = {
  mentioned: "Mentioned it",
  not_mentioned: "Didn't mention it",
  no_newsletter: "No newsletter",
};

interface MentionGridOptions<T extends Pick<LensWardCell, "month" | "status" | "mentioning" | "newsletters">> {
  /** Field holding each cell's row key. */
  row: keyof T & string;
  rows: string[];
  rowLabel: (row: string) => string;
  /** Tooltip heading for a cell, e.g. "Ward 5 · Mar 2026". */
  describeCell: (cell: T) => string;
  /** What a mention is of, for the tooltip: "Public safety". */
  subjectLabel: (cell: T) => string;
  marginLeft: number;
}

/** Row × month grid of mention statuses: mentioned, sent newsletters without mentioning, or no newsletter. */
function renderMentionGrid<T extends Pick<LensWardCell, "month" | "status" | "mentioning" | "newsletters">>(
  cells: T[],
  months: string[],
  options: MentionGridOptions<T>,
  width: number,
): Element {
  const marginRight = 10;
  const plotWidth = Math.max(width, months.length * MIN_COVERAGE_CELL_WIDTH + options.marginLeft + marginRight);
  const statuses = Object.keys(LENS_WARD_COLORS) as LensWardCell["status"][];
  const plot = Plot.plot({
    ...baseOptions(plotWidth),
    height: options.rows.length * ROW_HEIGHT + AXIS_BAND + TOP_AXIS_MARGIN,
    marginTop: TOP_AXIS_MARGIN,
    marginLeft: options.marginLeft,
    marginRight,
    marginBottom: AXIS_BAND,
    padding: 0.08,
    x: { ...monthAxis(months, plotWidth, options.marginLeft, marginRight), axis: "both" },
    y: { label: null, domain: options.rows, tickFormat: options.rowLabel },
    marks: statuses.map((status) =>
      Plot.cell(
        cells.filter((cell) => cell.status === status),
        {
          x: "month",
          y: options.row,
          fill: LENS_WARD_COLORS[status].fill,
          stroke: LENS_WARD_COLORS[status].stroke,
          inset: LENS_WARD_COLORS[status].stroke ? 0.5 : 0,
          rx: 2,
          title: (cell: T) =>
            `${options.describeCell(cell)}\n${LENS_WARD_STATUS_LABELS[status]}` +
            (cell.newsletters
              ? `\n${cell.mentioning} of ${cell.newsletters} newsletter${cell.newsletters === 1 ? "" : "s"} mentioned ${options.subjectLabel(cell)}`
              : ""),
          tip: true,
        },
      ),
    ),
  });
  return wrap(
    renderKey(
      statuses.map((status) => ({
        label: LENS_WARD_STATUS_LABELS[status],
        color: LENS_WARD_COLORS[status].fill,
        outline: LENS_WARD_COLORS[status].stroke,
      })),
      "square",
    ),
    plot,
  );
}

/** Ward × month grid for one lens: which wards' newsletters mentioned it each month. */
export function renderLensWardGrid(
  cells: LensWardCell[],
  wards: string[],
  months: string[],
  lensLabel: string,
  width: number,
): Element {
  return renderMentionGrid(
    cells,
    months,
    {
      row: "ward",
      rows: wards,
      rowLabel: formatWard,
      describeCell: (cell) => `${formatWard(cell.ward)} · ${formatMonth(cell.month)}`,
      subjectLabel: () => lensLabel,
      marginLeft: 70,
    },
    width,
  );
}

/**
 * Topic × month grid for one ward, shaded by the share of that month's
 * newsletters mentioning each topic, so a prolific ward isn't solid blue.
 */
export function renderWardTopicGrid(
  cells: WardTopicMonthCell[],
  lenses: { id: string; label: string }[],
  months: string[],
  ward: string,
  width: number,
): Element {
  const labelOf = new Map(lenses.map((lens) => [lens.id, lens.label]));
  const marginLeft = longestLabelMargin(lenses.map((lens) => lens.label));
  const marginRight = 10;
  const plotWidth = Math.max(width, months.length * MIN_COVERAGE_CELL_WIDTH + marginLeft + marginRight);
  const heading = (cell: WardTopicMonthCell) =>
    `${labelOf.get(cell.lens) ?? cell.lens} · ${formatWard(ward)} · ${formatMonth(cell.month)}`;
  const plot = Plot.plot({
    ...baseOptions(plotWidth),
    height: lenses.length * ROW_HEIGHT + AXIS_BAND + TOP_AXIS_MARGIN,
    marginTop: TOP_AXIS_MARGIN,
    marginLeft,
    marginRight,
    marginBottom: AXIS_BAND,
    padding: 0.08,
    x: { ...monthAxis(months, plotWidth, marginLeft, marginRight), axis: "both" },
    y: { label: null, domain: lenses.map((lens) => lens.id), tickFormat: (id: string) => labelOf.get(id) ?? id },
    color: {
      type: "linear",
      domain: [0, 100],
      range: [CHART_COLORS.sequentialLow, CHART_COLORS.sequentialHigh],
      percent: true,
      label: "Share of the month's newsletters mentioning it (%)",
    },
    marks: [
      Plot.cell(
        cells.filter((cell) => cell.share === null),
        {
          x: "month",
          y: "lens",
          fill: CHART_COLORS.untracked,
          rx: 2,
          title: (cell: WardTopicMonthCell) => `${heading(cell)}\nNo newsletter`,
          tip: true,
        },
      ),
      Plot.cell(
        cells.filter((cell) => cell.share !== null),
        {
          x: "month",
          y: "lens",
          fill: "share",
          rx: 2,
          title: (cell: WardTopicMonthCell) =>
            `${heading(cell)}\n${cell.mentioning} of ${cell.newsletters} newsletter${cell.newsletters === 1 ? "" : "s"} (${formatPercent(cell.share ?? 0)})`,
          tip: true,
        },
      ),
    ],
  });
  return wrap(
    renderKey([{ label: "No newsletter", color: CHART_COLORS.untracked }], "square"),
    withColorLegend(plot),
  );
}

/** Room for the longest y-axis label; narrow screens scroll the chart rather than clip names. */
function longestLabelMargin(labels: string[]): number {
  return Math.max(...labels.map((label) => label.length), 0) * LABEL_CHARACTER_WIDTH + AXIS_TICK_ROOM;
}

const CADENCE_HEIGHT = 160;

/**
 * One ward's newsletters per month: bars where newsletters arrived, a hollow
 * dot at zero for tracked months with none, and a gray band before the ward
 * was tracked.
 */
export function renderWardCadence(cells: CoverageCell[], months: string[], width: number): Element {
  const marginLeft = 40;
  const marginRight = 20;
  const plotWidth = Math.max(width, months.length * MIN_COVERAGE_CELL_WIDTH + marginLeft + marginRight);
  const maxCount = Math.max(1, ...cells.map((cell) => cell.newsletters));
  const label = (cell: CoverageCell) => `${formatWard(cell.ward)} · ${formatMonth(cell.month)}`;
  const plot = Plot.plot({
    ...baseOptions(plotWidth),
    height: CADENCE_HEIGHT + AXIS_BAND,
    marginLeft,
    marginRight,
    marginBottom: AXIS_BAND,
    x: { ...monthAxis(months, plotWidth, marginLeft, marginRight), padding: 0.2 },
    y: { label: "Newsletters", grid: true, domain: [0, maxCount], nice: true },
    marks: [
      Plot.barY(
        cells.filter((cell) => cell.status === "untracked"),
        {
          x: "month",
          y: () => maxCount,
          fill: CHART_COLORS.untracked,
          title: (cell: CoverageCell) => `${label(cell)}\nNot tracked yet`,
          tip: true,
        },
      ),
      Plot.barY(
        cells.filter((cell) => cell.status === "received"),
        {
          x: "month",
          y: "newsletters",
          fill: CHART_COLORS.series,
          rx: 2,
          title: (cell: CoverageCell) =>
            `${label(cell)}\n${cell.newsletters} newsletter${cell.newsletters === 1 ? "" : "s"}`,
          tip: true,
        },
      ),
      Plot.dot(
        cells.filter((cell) => cell.status === "silent"),
        {
          x: "month",
          y: () => 0,
          r: 3,
          fill: CHART_COLORS.surface,
          stroke: CHART_COLORS.mutedInk,
          title: (cell: CoverageCell) => `${label(cell)}\nNone received`,
          tip: true,
        },
      ),
      Plot.ruleY([0], { stroke: CHART_COLORS.baseline }),
    ],
  });
  return wrap(
    renderKey(
      [
        { label: "Newsletters received", color: CHART_COLORS.series },
        { label: "None received", color: CHART_COLORS.surface, outline: CHART_COLORS.mutedInk },
        { label: "Not tracked yet", color: CHART_COLORS.untracked },
      ],
      "square",
    ),
    plot,
  );
}

/**
 * For each topic: the share of the ward's months that mentioned it (dark dot)
 * beside the average share of active wards mentioning it in those months
 * (light dot). Topics keep their usual order, so the chart is a profile, not
 * a ranking.
 */
export function renderWardTopicComparison(
  topics: WardTopicSummary[],
  lenses: { id: string; label: string }[],
  ward: string,
  width: number,
): Element {
  const labelOf = new Map(lenses.map((lens) => [lens.id, lens.label]));
  const rows = topics.filter((topic) => topic.wardShare !== null && topic.cityShare !== null);
  const marginLeft = longestLabelMargin(lenses.map((lens) => lens.label));
  const describe = (topic: WardTopicSummary) =>
    `${labelOf.get(topic.lens) ?? topic.lens}\n${formatWard(ward)}: ${topic.monthsMentioning} of ${topic.monthsChecked} months ` +
    `(${formatPercent(topic.wardShare ?? 0)})\nAll active wards, same months: ${formatPercent(topic.cityShare ?? 0)} on average`;
  const plot = Plot.plot({
    ...baseOptions(width),
    height: rows.length * BAR_ROW_HEIGHT + AXIS_BAND + TOP_AXIS_MARGIN,
    marginTop: TOP_AXIS_MARGIN,
    marginLeft,
    marginRight: 30,
    x: { label: "Share of months (%)", domain: [0, 100], percent: true, grid: true, axis: "both" },
    y: { label: null, domain: rows.map((topic) => topic.lens), tickFormat: (id: string) => labelOf.get(id) ?? id },
    marks: [
      Plot.link(rows, {
        x1: "cityShare",
        x2: "wardShare",
        y1: "lens",
        y2: "lens",
        stroke: CHART_COLORS.seriesLight,
        strokeWidth: 2,
      }),
      Plot.dot(rows, {
        x: "cityShare",
        y: "lens",
        r: 4,
        fill: CHART_COLORS.seriesLight,
        stroke: CHART_COLORS.surface,
        strokeWidth: 2,
      }),
      Plot.dot(rows, {
        x: "wardShare",
        y: "lens",
        r: 5,
        fill: CHART_COLORS.seriesDark,
        stroke: CHART_COLORS.surface,
        strokeWidth: 2,
        title: describe,
        tip: true,
      }),
    ],
  });
  return wrap(
    renderKey([
      { label: `${formatWard(ward)}: share of months`, color: CHART_COLORS.seriesDark },
      { label: "All active wards (average)", color: CHART_COLORS.seriesLight },
    ]),
    plot,
  );
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

/**
 * A ward's distinctive terms as the share of its newsletters using each, in
 * distinctiveness order, labeled with the count and the rest of the city's share.
 */
export function renderDistinctiveTerms(
  terms: DistinctiveTerm[],
  ward: string,
  wardNewsletters: number,
  width: number,
): Element {
  const label = (item: DistinctiveTerm) =>
    `${item.ward_newsletters} of ${wardNewsletters} · ${formatPercent(item.rest_share)} elsewhere`;
  return Plot.plot({
    ...baseOptions(width),
    height: terms.length * BAR_ROW_HEIGHT + AXIS_BAND,
    marginLeft: 170,
    marginRight: 150,
    x: { label: "Share of this ward's newsletters (%)", percent: true, grid: true },
    y: { label: null, domain: terms.map((item) => item.term), padding: 1 - MAX_BAR_THICKNESS },
    marks: [
      Plot.barX(terms, {
        x: "ward_share",
        y: "term",
        fill: CHART_COLORS.series,
        rx: 4,
        href: (item: DistinctiveTerm) => buildSearchUrl({ q: item.term, ward }),
        title: (item: DistinctiveTerm) =>
          `"${item.term}" in ${item.ward_newsletters} of ${wardNewsletters} ${formatWard(ward)} newsletters (${formatPercent(item.ward_share)})\n` +
          `Rest of city: ${formatPercent(item.rest_share)} · ${formatLift(item.lift)} as likely here\nClick to search`,
        tip: true,
      }),
      Plot.text(terms, {
        x: "ward_share",
        y: "term",
        text: label,
        textAnchor: "start",
        dx: 6,
        fill: CHART_COLORS.mutedInk,
      }),
      Plot.ruleX([0], { stroke: CHART_COLORS.baseline }),
    ],
  });
}

/**
 * Dot plot of rising terms: wards mentioning each term in a typical baseline
 * month (light) and in the latest month (dark), on an axis running to the
 * number of wards active in the latest month.
 */
export function renderRisingTerms(
  terms: RisingTerm[],
  activeWards: number,
  baselineLabel: string,
  latestLabel: string,
  width: number,
): Element {
  const marginLeft = longestLabelMargin(terms.map((item) => item.term));
  const seasonalTerms = terms.filter((item) => item.seasonal === true);
  const plot = Plot.plot({
    ...baseOptions(width),
    height: terms.length * BAR_ROW_HEIGHT + AXIS_BAND + TOP_AXIS_MARGIN,
    marginTop: TOP_AXIS_MARGIN,
    marginLeft,
    marginRight: seasonalTerms.length ? SEASONAL_TAG_MARGIN : 30,
    x: { label: `Wards mentioning it (of ${activeWards} active)`, domain: [0, activeWards], grid: true, axis: "both" },
    y: { label: null, domain: terms.map((item) => item.term) },
    marks: [
      Plot.link(terms, {
        x1: "baseline_wards",
        x2: "latest_wards",
        y1: "term",
        y2: "term",
        stroke: CHART_COLORS.seriesLight,
        strokeWidth: 2,
      }),
      Plot.dot(terms, {
        x: "baseline_wards",
        y: "term",
        r: 4,
        fill: CHART_COLORS.seriesLight,
        stroke: CHART_COLORS.surface,
        strokeWidth: 2,
      }),
      Plot.dot(terms, {
        x: "latest_wards",
        y: "term",
        r: 5,
        fill: CHART_COLORS.seriesDark,
        stroke: CHART_COLORS.surface,
        strokeWidth: 2,
        href: (item: RisingTerm) => buildSearchUrl({ q: item.term }),
        title: (item: RisingTerm) =>
          `"${item.term}"\n${latestLabel}: ${item.latest_wards} of ${activeWards} wards (${item.latest_newsletters} newsletters)\n` +
          `${baselineLabel}: ${item.baseline_wards} wards (median; ${item.baseline_month_wards.join(", ")} by month)` +
          `${item.seasonal ? "\nSeasonal" : ""}\nClick to search`,
        tip: true,
      }),
      Plot.text(seasonalTerms, {
        x: "latest_wards",
        y: "term",
        text: () => "seasonal",
        textAnchor: "start",
        dx: 10,
        fontSize: 10,
        fill: CHART_COLORS.mutedInk,
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

/**
 * Ward × month coverage grid. `wardsNeverArchived` (wards with no newsletter in
 * the whole archive) get a text label, since an all-gray row in a short window
 * can also mean the ward simply joined later.
 */
export function renderCoverageGrid(
  cells: CoverageCell[],
  wards: string[],
  months: string[],
  wardsNeverArchived: string[],
  searchScope: SearchLinkParams,
  width: number,
): Element {
  const marginLeft = 70;
  const marginRight = 10;
  const cellsByStatus = (status: CoverageCell["status"]) => cells.filter((cell) => cell.status === status);
  const plotWidth = Math.max(width, months.length * MIN_COVERAGE_CELL_WIDTH + marginLeft + marginRight);
  const plot = Plot.plot({
    ...baseOptions(plotWidth, COVERAGE_FONT_SIZE),
    height: wards.length * COVERAGE_ROW_HEIGHT + AXIS_BAND + TOP_AXIS_MARGIN,
    marginTop: TOP_AXIS_MARGIN,
    marginLeft,
    marginRight,
    marginBottom: AXIS_BAND,
    padding: 0.08,
    x: { ...monthAxis(months, plotWidth, marginLeft, marginRight), axis: "both" },
    y: { label: null, domain: wards, tickFormat: formatWard },
    color: {
      // Square-root scale starting at a clearly blue tint: one newsletter must not
      // read as the gray "not tracked" state, and one prolific ward must not wash
      // out every other ward's counts.
      type: "sqrt",
      range: [CHART_COLORS.seriesLight, CHART_COLORS.sequentialHigh],
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
          `${formatWard(cell.ward)} · ${formatMonth(cell.month)}\nNone received`,
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
      Plot.text(wardsNeverArchived, {
        x: () => months[0],
        y: (ward: string) => ward,
        text: () => "No newsletters",
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
        { label: "Not tracked yet", color: CHART_COLORS.untracked },
        { label: "None received", color: CHART_COLORS.surface, outline: CHART_COLORS.baseline },
      ],
      "square",
    ),
    withColorLegend(plot),
  );
}
