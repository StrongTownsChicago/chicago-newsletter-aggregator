// Topic ward-reach charts: the civic calendar, the topic trend and its sparklines.
import * as Plot from "@observablehq/plot";
import { formatMonth } from "../core";
import { describeWardReach, formatPercent } from "../format";
import type { LensReachCell } from "../reach";
import { formatPointChange, reachDeviation, type TopicTrendPoint } from "../topic-trends";
import {
  AXIS_BAND,
  baseOptions,
  CHART_COLORS,
  longestLabelMargin,
  monthAxis,
  TOP_AXIS_MARGIN,
  withColorLegend,
} from "./common";

/** Civic calendar columns never get narrower than this, so ward counts fit; wider calendars scroll. */
const MIN_CALENDAR_CELL_WIDTH = 32;
const CALENDAR_ROW_HEIGHT = 26;
/** Calendar labels switch to light ink beyond this fraction of the largest deviation. */
const CALENDAR_DARK_CELL_FRACTION = 0.55;
/** The calendar's color scale spans at least ±this deviation, so tiny wobbles stay pale. */
const MIN_CALENDAR_DEVIATION = 0.1;
/** Opacity of calendar cells resting on too few wards or a partial month. */
const FADED_OPACITY = 0.35;
const SPARKLINE_WIDTH = 120;
const SPARKLINE_HEIGHT = 28;
const TREND_HEIGHT = 200;

/** One topic's monthly ward reach on a tight y scale, with its average as a dashed rule. */
export function renderReachTrend(
  points: LensReachCell[],
  { months, domain }: { months: string[]; domain: [number, number] },
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
  const sparkline = Plot.plot({
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
  // Read as one image with its label, not as a tree of unnamed marks.
  sparkline.setAttribute("role", "img");
  return sparkline;
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
  makeTopicsClickable(plot, lenses, selectedLens, onSelectTopic);
  return withColorLegend(plot);
}

/**
 * Row labels and cells select their topic; `plot.value` is the cell under the
 * pointer. Row labels are also keyboard buttons, so every topic is reachable
 * without a pointer.
 */
function makeTopicsClickable(
  plot: ReturnType<typeof Plot.plot>,
  lenses: { id: string; label: string }[],
  selectedLens: string | null,
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
    label.setAttribute("tabindex", "0");
    label.setAttribute("role", "button");
    label.setAttribute("aria-label", `Show ${lens.label} detail`);
    label.setAttribute("aria-pressed", String(lens.id === selectedLens));
    label.addEventListener("click", (event) => {
      event.stopPropagation();
      onSelectTopic(lens.id);
    });
    label.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      onSelectTopic(lens.id);
    });
  });
}
