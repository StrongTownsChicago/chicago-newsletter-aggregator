// Ward profile charts: sending cadence, topics against all wards, distinctive vocabulary.
import * as Plot from "@observablehq/plot";
import { formatMonth, type DistinctiveTerm } from "../core";
import type { CoverageCell } from "../coverage";
import { formatLift, formatPercent, formatWard } from "../format";
import { buildSearchUrl } from "../search-links";
import type { WardTopicSummary } from "../ward-profile";
import {
  AXIS_BAND,
  BAR_ROW_HEIGHT,
  baseOptions,
  CHART_COLORS,
  longestLabelMargin,
  MAX_BAR_THICKNESS,
  MIN_COVERAGE_CELL_WIDTH,
  monthAxis,
  renderKey,
  TOP_AXIS_MARGIN,
  wrap,
} from "./common";

const CADENCE_HEIGHT = 160;
/** Right margin of the distinctive terms chart when labels end in "+N related". */
const DISTINCTIVE_RELATED_MARGIN = 220;
const DISTINCTIVE_LEFT_MARGIN = 170;
const DISTINCTIVE_RIGHT_MARGIN = 150;
/** Narrow screens scroll the distinctive terms chart sideways rather than squeeze its bars below this. */
const MIN_DISTINCTIVE_BAR_SPAN = 120;

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
    `${item.ward_newsletters} of ${wardNewsletters} · ${formatPercent(item.rest_share)} elsewhere` +
    (item.related_terms ? ` · +${item.related_terms} related` : "");
  const marginRight = terms.some((item) => item.related_terms) ? DISTINCTIVE_RELATED_MARGIN : DISTINCTIVE_RIGHT_MARGIN;
  return Plot.plot({
    ...baseOptions(Math.max(width, DISTINCTIVE_LEFT_MARGIN + marginRight + MIN_DISTINCTIVE_BAR_SPAN)),
    height: terms.length * BAR_ROW_HEIGHT + AXIS_BAND,
    marginLeft: DISTINCTIVE_LEFT_MARGIN,
    marginRight,
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
          `Rest of city: ${formatPercent(item.rest_share)} · ${formatLift(item.lift)} as likely here` +
          (item.related_terms
            ? `\n+${item.related_terms} related term${item.related_terms === 1 ? "" : "s"} from the same newsletters`
            : "") +
          "\nClick to search",
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
