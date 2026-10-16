// Civic calendar panel: every topic's ward reach by month, and the topic trend table.
import { formatMonth, type AnalyticsFilters } from "../../../lib/analytics/core";
import { formatPercent } from "../../../lib/analytics/format";
import { isReachFaded, type LensReachCell } from "../../../lib/analytics/reach";
import {
  describeSparkline,
  describeTopicReach,
  formatLatestReach,
  formatPointChange,
  formatPoints,
  isPartialMonth,
  orderBySwing,
  tightShareDomain,
  type TopicTrend,
} from "../../../lib/analytics/topic-trends";
import { EXPORT_TEXT_ATTRIBUTE } from "../../../lib/analytics/charts/export";
import { renderCivicCalendar, renderSparkline } from "../../../lib/analytics/charts/topic-reach";
import { lensLabel, type DashboardState, type TopicOverview } from "../dashboard-state";
import {
  chartWidth,
  emptyMessage,
  exportText,
  panel,
  replaceContent,
  requireElement,
  setTable,
  tableHeading,
} from "../dom";
import { reachColumns } from "./reach-table";

/** One row per topic: a button that selects it, a sparkline, the last full month and its change. */
function buildTopicTrendTable(
  state: DashboardState,
  trends: TopicTrend[],
  latestMonth: string | undefined,
  selectedLens: string | null,
): HTMLElement {
  const tableElement = document.createElement("table");
  tableElement.className = "text-sm";
  const head = tableElement.createTHead().insertRow();
  const headClass = "text-left text-xs font-semibold text-gray-600 pb-1 pr-4";
  head.append(
    exportText("th", "Topic", headClass),
    exportText("th", "Trend", headClass),
    exportText("th", latestMonth ? formatMonth(latestMonth) : "Latest", `${headClass} text-right`),
    exportText("th", "vs average", `${headClass} text-right hidden sm:table-cell`),
  );
  const body = tableElement.createTBody();
  for (const trend of trends) {
    const label = lensLabel(state, trend.lens);
    const row = body.insertRow();
    row.className = trend.lens === selectedLens ? "bg-blue-50" : "";
    const topicCell = row.insertCell();
    topicCell.className = "pr-4 py-0.5";
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.topic = trend.lens;
    button.setAttribute("aria-pressed", String(trend.lens === selectedLens));
    button.setAttribute(EXPORT_TEXT_ATTRIBUTE, "");
    button.className =
      "text-left text-blue-700 hover:underline sm:whitespace-nowrap rounded focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-blue-600";
    button.textContent = label;
    topicCell.append(button);
    const sparkCell = row.insertCell();
    sparkCell.className = "pr-2 sm:pr-4 py-0.5";
    const shares = trend.points.flatMap((point) => (point.share === null ? [] : [point.share]));
    sparkCell.append(renderSparkline(trend.points, tightShareDomain(shares), describeSparkline(label, trend.points)));
    const change = trend.latestChange === null ? "–" : formatPointChange(trend.latestChange);
    // Narrow screens fold the change under the month's count instead of a fourth column.
    const latestCell = row.insertCell();
    latestCell.className = "sm:pr-4 text-right tabular-nums whitespace-nowrap";
    latestCell.append(
      exportText("span", formatLatestReach(trend), "block"),
      exportText(
        "span",
        trend.latestChange === null ? change : `${change} vs avg.`,
        "block text-xs text-gray-500 sm:hidden",
      ),
    );
    row.append(exportText("td", change, "text-right tabular-nums whitespace-nowrap hidden sm:table-cell"));
  }
  return tableElement;
}

export function renderCivicCalendarPanel(
  state: DashboardState,
  filters: AnalyticsFilters,
  overview: TopicOverview,
  months: string[],
  selectTopic: (lensId: string) => void,
): void {
  const { section, chart, caption, table } = panel("civic-calendar");
  const { cells, fullMonths, threshold } = overview;
  const trends = orderBySwing(overview.trends);
  const lastDate = state.data.metadata.last_date;
  const isPartial = (month: string) => isPartialMonth(month, state.asOfMonth);
  const fadeReason = (cell: LensReachCell): string | null =>
    isReachFaded(cell, threshold)
      ? `Faded: fewer than ${threshold} wards sent newsletters`
      : isPartial(cell.month)
        ? `Faded: month in progress, newsletters through ${lastDate}`
        : null;
  const shownCells = cells.filter((cell) => cell.share !== null);
  const fadedReasons = [
    ...(shownCells.some((cell) => isPartial(cell.month)) ? ["month in progress"] : []),
    ...(shownCells.some((cell) => isReachFaded(cell, threshold)) ? [`fewer than ${threshold} wards sending`] : []),
  ];
  caption.textContent = fadedReasons.length ? `Faded: ${fadedReasons.join(" or ")}.` : "";
  if (!chart) return;
  const lenses = trends.map((trend) => ({ id: trend.lens, label: lensLabel(state, trend.lens) }));
  replaceContent(
    chart,
    months.length && lenses.length
      ? renderCivicCalendar(
          cells,
          {
            lenses,
            months,
            averageByLens: new Map(trends.map((trend) => [trend.lens, trend.averageShare])),
            selectedLens: filters.lens,
            fadeReason,
            onSelectTopic: selectTopic,
          },
          chartWidth(chart),
        )
      : emptyMessage("Nothing in these dates."),
  );
  requireElement<HTMLElement>("#civic-calendar-scroll-hint", section).hidden = chart.scrollWidth <= chart.clientWidth;
  replaceContent(
    requireElement<HTMLElement>("#topic-trends", section),
    fullMonths.length ? buildTopicTrendTable(state, trends, fullMonths.at(-1), filters.lens) : emptyMessage("No full month in these dates."),
  );
  const reachTable = document.createElement("div");
  setTable(reachTable, reachColumns(state, threshold), cells);
  const trendTable = document.createElement("div");
  setTable(
    trendTable,
    [
      { label: "Topic", value: (trend) => lensLabel(state, trend.lens) },
      {
        label: "Average",
        value: (trend) => (trend.averageShare === null ? "–" : formatPercent(trend.averageShare)),
        numeric: true,
      },
      { label: "Swing", value: (trend) => formatPoints(trend.swing), numeric: true },
      { label: "Last full month", value: (trend) => describeTopicReach(trend) || "–", numeric: true },
      {
        label: "vs average",
        value: (trend) => (trend.latestChange === null ? "–" : formatPointChange(trend.latestChange)),
        numeric: true,
      },
    ],
    trends,
  );
  replaceContent(table, tableHeading("By topic"), trendTable, tableHeading("By topic and month"), reachTable);
}
