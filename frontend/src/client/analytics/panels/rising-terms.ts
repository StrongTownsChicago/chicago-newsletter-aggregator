// Rising terms panel: terms more wards mentioned in the latest month than in a typical one (city-wide).
import { formatMonth, type RisingTerm } from "../../../lib/analytics/core";
import { pluralize } from "../../../lib/analytics/descriptions";
import { renderRisingTerms } from "../../../lib/analytics/charts/terms";
import type { DashboardState } from "../dashboard-state";
import { chartWidth, emptyMessage, panel, replaceContent, setTable } from "../dom";

export function renderRisingPanel(state: DashboardState): void {
  const { chart, caption, table } = panel("rising-terms");
  const rising = state.data.rising;
  if (!rising.latest_month) {
    caption.textContent = "No complete month yet.";
    replaceContent(chart, emptyMessage("No rising terms."));
    replaceContent(table, emptyMessage("No rows."));
    return;
  }
  const baselineSpan = `${formatMonth(rising.baseline_months[0])} – ${formatMonth(rising.baseline_months[rising.baseline_months.length - 1])}`;
  const latest = formatMonth(rising.latest_month);
  caption.textContent =
    `${latest}: ${pluralize(rising.latest_active_wards, "ward")} sent newsletters ` +
    `(${rising.baseline_active_wards.join(", ")} in ${baselineSpan}).`;
  if (!chart) return;
  replaceContent(
    chart,
    rising.terms.length
      ? renderRisingTerms(
          rising.terms,
          rising.latest_active_wards,
          { baseline: `Typical month (median, ${baselineSpan})`, latest },
          chartWidth(chart),
        )
      : emptyMessage("No rising terms."),
  );
  const hasSeasonalFlags = rising.terms.some((item) => item.seasonal !== undefined);
  setTable(
    table,
    [
      { label: "Term", value: (item) => item.term },
      ...(hasSeasonalFlags
        ? [{ label: "Seasonal", value: (item: RisingTerm) => (item.seasonal ? "Yes" : "") }]
        : []),
      { label: `Wards in ${latest}`, value: (item) => `${item.latest_wards} of ${rising.latest_active_wards}`, numeric: true },
      { label: "Wards in a typical month (median)", value: (item) => item.baseline_wards, numeric: true },
      { label: "Wards by baseline month", value: (item) => item.baseline_month_wards.join(", "), numeric: true },
      { label: "Gain in wards", value: (item) => `+${item.ward_gain}`, numeric: true },
      { label: `Newsletters in ${latest}`, value: (item) => item.latest_newsletters, numeric: true },
    ],
    rising.terms,
  );
}
