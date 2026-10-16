// Coverage panel: which wards sent newsletters each month (the grid draws only while expanded).
import { listWindowMonths, wardsInScope, type AnalyticsFilters } from "../../../lib/analytics";
import { buildCoverageGrid, summarizeWardCoverage } from "../../../lib/analytics-coverage";
import { pluralize } from "../../../lib/analytics-descriptions";
import { COVERAGE_STATUS_LABELS, formatWard } from "../../../lib/analytics-format";
import { searchScopeForFilters } from "../../../lib/analytics-search-links";
import { renderCoverageGrid } from "../../../lib/charts/ward-grids";
import type { DashboardState } from "../dashboard-state";
import {
  chartWidth,
  emptyMessage,
  panel,
  replaceContent,
  requireElement,
  setTable,
  tableHeading,
} from "../dom";

export function renderCoveragePanel(state: DashboardState, filters: AnalyticsFilters): void {
  const { chart, caption, table } = panel("coverage");
  const wards = wardsInScope(state.allWards, filters);
  const months = listWindowMonths(filters, state.dataMonths);
  const coverage = summarizeWardCoverage(state.data.sources, wards);
  const wardsNeverArchived = coverage.filter((ward) => ward.newsletters === 0).map((ward) => ward.ward);
  const archivedWards = wards.length - wardsNeverArchived.length;
  caption.textContent =
    `${archivedWards} of ${pluralize(wards.length, "ward")} have newsletters.` +
    (wardsNeverArchived.length ? ` None yet: ${wardsNeverArchived.map(formatWard).join(", ")}.` : "");
  const cells = buildCoverageGrid(state.data.newsletters, wards, months);
  // Drawn only while expanded, at the width it then has.
  if (chart && requireElement<HTMLDetailsElement>("#coverage-details").open) {
    replaceContent(
      chart,
      wards.length && months.length
        ? renderCoverageGrid(
            cells,
            wards,
            months,
            wardsNeverArchived,
            searchScopeForFilters(filters),
            chartWidth(chart),
          )
        : emptyMessage("Nothing in these dates."),
    );
  }
  const wardTable = document.createElement("div");
  setTable(
    wardTable,
    [
      { label: "Ward", value: (row) => row.ward },
      { label: "Aldermen", value: (row) => row.aldermen.join(", ") },
      { label: "First newsletter", value: (row) => row.firstDate ?? "None" },
      { label: "Latest newsletter", value: (row) => row.lastDate ?? "" },
      { label: "Newsletters (all dates)", value: (row) => row.newsletters, numeric: true },
    ],
    coverage,
  );
  const monthTable = document.createElement("div");
  setTable(
    monthTable,
    [
      { label: "Ward", value: (cell) => cell.ward },
      { label: "Month", value: (cell) => cell.month },
      { label: "Status", value: (cell) => COVERAGE_STATUS_LABELS[cell.status] },
      { label: "Newsletters", value: (cell) => cell.newsletters, numeric: true },
    ],
    cells,
  );
  replaceContent(table, tableHeading("By ward"), wardTable, tableHeading("By ward and month"), monthTable);
}
