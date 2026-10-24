// Topic detail panel: the chosen topic's ward-reach trend and its ward × month grid.
import { listWards } from "../../../lib/analytics/core";
import { LENS_WARD_STATUS_LABELS } from "../../../lib/analytics/format";
import { buildLensWardGrid, isReachFaded, type LensReachCell, type LensWardCell } from "../../../lib/analytics/reach";
import { describeLatestVsAverage, tightShareDomain } from "../../../lib/analytics/topic-trends";
import { renderReachTrend } from "../../../lib/analytics/charts/topic-reach";
import { renderLensWardGrid } from "../../../lib/analytics/charts/ward-grids";
import { lensLabel, type DashboardRender, type TopicOverview } from "../dashboard-state";
import {
  chartWidth,
  emptyMessage,
  panel,
  replaceContent,
  requireElement,
  setTable,
  tableHeading,
} from "../dom";
import { reachColumns } from "./reach-table";

/** The topic's full-month reach, with faded months' shares hidden. */
function trendPoints(overview: TopicOverview, lens: string): LensReachCell[] {
  const fullMonths = new Set(overview.fullMonths);
  return overview.cells
    .filter((cell) => cell.lens === lens && fullMonths.has(cell.month))
    .map((cell) => (isReachFaded(cell, overview.threshold) ? { ...cell, share: null } : cell));
}

function renderTrend(section: HTMLElement, caption: HTMLElement, overview: TopicOverview, lens: string): void {
  const trend = overview.trends.find((item) => item.lens === lens);
  const points = trendPoints(overview, lens);
  const shares = points.flatMap((point) => (point.share === null ? [] : [point.share]));
  caption.textContent = describeLatestVsAverage(trend, overview.fullMonths.at(-1));
  const trendChart = requireElement<HTMLElement>("#topic-detail-trend", section);
  replaceContent(
    trendChart,
    shares.length
      ? renderReachTrend(
          points,
          { months: overview.fullMonths, domain: tightShareDomain(shares) },
          trend?.averageShare ?? null,
          chartWidth(trendChart),
        )
      : emptyMessage("Too few wards sent newsletters in these dates."),
  );
}

/** Draws the ward × month grid and returns its cells. */
function renderWardGrid(
  section: HTMLElement,
  { state, filters, factsIgnoringLens, months }: DashboardRender,
  lens: string,
): LensWardCell[] {
  const wards = listWards(state.data.newsletters).filter((ward) => !filters.wards.length || filters.wards.includes(ward));
  const wardCells = buildLensWardGrid(factsIgnoringLens, lens, wards, months);
  const wardChart = requireElement<HTMLElement>("#topic-detail-wards", section);
  replaceContent(
    wardChart,
    wards.length && months.length
      ? renderLensWardGrid(wardCells, { wards, months }, lensLabel(state, lens), chartWidth(wardChart))
      : emptyMessage("Nothing in these dates."),
  );
  return wardCells;
}

function renderTables(
  table: HTMLElement | null,
  { state, overview }: Pick<DashboardRender, "state" | "overview">,
  lens: string,
  wardCells: LensWardCell[],
): void {
  const reachTable = document.createElement("div");
  setTable(
    reachTable,
    reachColumns(state, overview.threshold),
    overview.cells.filter((cell) => cell.lens === lens),
  );
  const wardTable = document.createElement("div");
  setTable(
    wardTable,
    [
      { label: "Ward", value: (cell) => cell.ward },
      { label: "Month", value: (cell) => cell.month },
      { label: "Status", value: (cell) => LENS_WARD_STATUS_LABELS[cell.status] },
      { label: "Newsletters mentioning", value: (cell) => cell.mentioning, numeric: true },
      { label: "Newsletters", value: (cell) => cell.newsletters, numeric: true },
    ],
    wardCells.filter((cell) => cell.status !== "no_newsletter"),
  );
  replaceContent(table, tableHeading("Ward reach"), reachTable, tableHeading("Wards by month"), wardTable);
}

/** The chosen topic's ward-reach trend and its ward × month grid. */
export function renderTopicDetailPanel(render: DashboardRender): void {
  const { section, caption, table } = panel("topic-detail");
  const { state, filters, overview } = render;
  const lens = filters.lens;
  if (!lens) return;
  requireElement<HTMLElement>("#topic-detail-heading", section).textContent = lensLabel(state, lens);
  renderTrend(section, caption, overview, lens);
  const wardCells = renderWardGrid(section, render, lens);
  renderTables(table, render, lens, wardCells);
}
