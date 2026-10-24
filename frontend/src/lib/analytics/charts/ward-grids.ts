// Ward × month and topic × month grids: archive coverage, one topic by ward, one ward by topic.
import * as Plot from "@observablehq/plot";
import { formatMonth } from "../core";
import type { CoverageCell } from "../coverage";
import { formatPercent, formatWard, LENS_WARD_STATUS_LABELS } from "../format";
import type { LensWardCell } from "../reach";
import { buildSearchUrl, monthDateRange, type SearchLinkParams } from "../search-links";
import type { WardTopicMonthCell } from "../ward-profile";
import {
  AXIS_BAND,
  baseOptions,
  CHART_COLORS,
  longestLabelMargin,
  MIN_COVERAGE_CELL_WIDTH,
  monthAxis,
  renderKey,
  ROW_HEIGHT,
  TOP_AXIS_MARGIN,
  withColorLegend,
  wrap,
} from "./common";

/** Ward × month grids (coverage, topic detail), compact: reference, not a headline. */
const COVERAGE_ROW_HEIGHT = 11;
const COVERAGE_FONT_SIZE = "10px";

const LENS_WARD_COLORS: Record<LensWardCell["status"], { fill: string; stroke?: string }> = {
  mentioned: { fill: CHART_COLORS.series },
  not_mentioned: { fill: CHART_COLORS.surface, stroke: CHART_COLORS.baseline },
  no_newsletter: { fill: CHART_COLORS.untracked },
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
  /** Row height in pixels; defaults to ROW_HEIGHT. */
  rowHeight?: number;
  fontSize?: string;
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
    ...baseOptions(plotWidth, options.fontSize),
    height: options.rows.length * (options.rowHeight ?? ROW_HEIGHT) + AXIS_BAND + TOP_AXIS_MARGIN,
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
  { wards, months }: { wards: string[]; months: string[] },
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
      marginLeft: 60,
      rowHeight: COVERAGE_ROW_HEIGHT,
      fontSize: COVERAGE_FONT_SIZE,
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
  { lenses, months }: { lenses: { id: string; label: string }[]; months: string[] },
  { ward, selectedLens }: { ward: string; selectedLens: string | null },
  width: number,
): Element {
  const labelOf = new Map(lenses.map((lens) => [lens.id, lens.label]));
  const marginLeft = longestLabelMargin(lenses.map((lens) => lens.label));
  const marginRight = 10;
  const plotWidth = Math.max(width, months.length * MIN_COVERAGE_CELL_WIDTH + marginLeft + marginRight);
  const selectedRow = selectedLens ? months.map((month) => ({ month, lens: selectedLens })) : [];
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
      Plot.cell(selectedRow, { x: "month", y: "lens", fill: "none", stroke: CHART_COLORS.mutedInk, strokeWidth: 1.5 }),
    ],
  });
  return wrap(
    renderKey([{ label: "No newsletter", color: CHART_COLORS.untracked }], "square"),
    withColorLegend(plot),
  );
}

/**
 * Ward × month coverage grid. `wardsNeverArchived` (wards with no newsletter in
 * the whole archive) get a text label, since an all-gray row in a short window
 * can also mean the ward simply joined later.
 */
export function renderCoverageGrid(
  { cells, wardsNeverArchived }: { cells: CoverageCell[]; wardsNeverArchived: string[] },
  { wards, months }: { wards: string[]; months: string[] },
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
