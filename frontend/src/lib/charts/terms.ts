// Term charts: a term's monthly share and wards, and the rising terms dot plot.
import * as Plot from "@observablehq/plot";
import type { RisingTerm } from "../analytics";
import { formatOptionalShare, formatPercent, formatWard } from "../analytics-format";
import { buildSearchUrl, type SearchLinkParams } from "../analytics-search-links";
import type { TermMonthPoint, TermWardRow } from "../analytics-terms";
import {
  AXIS_BAND,
  BAR_ROW_HEIGHT,
  baseOptions,
  CHART_COLORS,
  longestLabelMargin,
  MAX_BAR_THICKNESS,
  monthAxis,
  renderKey,
  TOP_AXIS_MARGIN,
  wrap,
} from "./common";

/** Right margin of the rising terms chart when a "seasonal" tag may sit past the last dot. */
const SEASONAL_TAG_MARGIN = 64;

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
