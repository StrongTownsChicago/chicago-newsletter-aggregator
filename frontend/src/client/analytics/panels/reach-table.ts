// Ward reach table columns, shared by the civic calendar and topic detail panels.
import { formatPercent } from "../../../lib/analytics/format";
import { isReachFaded, type LensReachCell } from "../../../lib/analytics/reach";
import type { TableColumn } from "../../../lib/analytics/table";
import { lensLabel, type DashboardState } from "../dashboard-state";

export function reachColumns(state: DashboardState, minActiveWards: number): TableColumn<LensReachCell>[] {
  return [
    { label: "Topic", value: (cell) => lensLabel(state, cell.lens) },
    { label: "Month", value: (cell) => cell.month },
    { label: "Wards mentioning", value: (cell) => cell.wardsMentioning, numeric: true },
    { label: "Active wards", value: (cell) => cell.activeWards, numeric: true },
    { label: "Share", value: (cell) => (cell.share === null ? "–" : formatPercent(cell.share)), numeric: true },
    { label: "Note", value: (cell) => (isReachFaded(cell, minActiveWards) ? "Few wards (faded)" : "") },
  ];
}
