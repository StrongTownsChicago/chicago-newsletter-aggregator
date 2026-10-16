// Topic detail panel: the chosen topic's ward-reach trend and its ward × month grid.
import { formatMonth, listWards } from "../../../lib/analytics";
import { formatPercent, LENS_WARD_STATUS_LABELS } from "../../../lib/analytics-format";
import { buildLensWardGrid, isReachFaded } from "../../../lib/analytics-reach";
import { describeTopicReach, formatPointChange, tightShareDomain } from "../../../lib/analytics-topic-trends";
import { renderReachTrend } from "../../../lib/charts/topic-reach";
import { renderLensWardGrid } from "../../../lib/charts/ward-grids";
import { lensLabel, type DashboardRender } from "../dashboard-state";
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

/** The chosen topic's ward-reach trend and its ward × month grid. */
export function renderTopicDetailPanel({ state, filters, overview, factsIgnoringLens: scopeFacts, months }: DashboardRender): void {
  const { section, caption, table } = panel("topic-detail");
  const lens = filters.lens;
  if (!lens) return;
  const label = lensLabel(state, lens);
  const trend = overview.trends.find((item) => item.lens === lens);
  requireElement<HTMLElement>("#topic-detail-heading", section).textContent = label;

  const fullMonths = new Set(overview.fullMonths);
  const points = overview.cells
    .filter((cell) => cell.lens === lens && fullMonths.has(cell.month))
    .map((cell) => (isReachFaded(cell, overview.threshold) ? { ...cell, share: null } : cell));
  const shares = points.flatMap((point) => (point.share === null ? [] : [point.share]));
  const latestMonth = overview.fullMonths.at(-1);
  caption.textContent =
    trend?.latest && latestMonth && trend.latestChange !== null && trend.averageShare !== null
      ? `${formatMonth(latestMonth)}: ${describeTopicReach(trend)}, ${formatPointChange(trend.latestChange)} vs its average (${formatPercent(trend.averageShare)}, dashed).`
      : "";
  const trendChart = requireElement<HTMLElement>("#topic-detail-trend", section);
  replaceContent(
    trendChart,
    shares.length
      ? renderReachTrend(
          points,
          overview.fullMonths,
          tightShareDomain(shares),
          trend?.averageShare ?? null,
          chartWidth(trendChart),
        )
      : emptyMessage("Too few wards sent newsletters in these dates."),
  );

  const wards = listWards(state.data.newsletters).filter((ward) => !filters.wards.length || filters.wards.includes(ward));
  const wardCells = buildLensWardGrid(scopeFacts, lens, wards, months);
  const wardChart = requireElement<HTMLElement>("#topic-detail-wards", section);
  replaceContent(
    wardChart,
    wards.length && months.length
      ? renderLensWardGrid(wardCells, wards, months, label, chartWidth(wardChart))
      : emptyMessage("Nothing in these dates."),
  );

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
