// Ward profile panel: one ward's cadence, gaps, topics and vocabulary against its own history.
import { formatDay, type NewsletterFact } from "../../../lib/analytics/core";
import { findLongestGaps } from "../../../lib/analytics/coverage";
import { pluralize } from "../../../lib/analytics/descriptions";
import {
  COVERAGE_STATUS_LABELS,
  formatMedian,
  formatPercent,
  formatWard,
} from "../../../lib/analytics/format";
import type { TableColumn } from "../../../lib/analytics/table";
import {
  MIN_WARD_MONTHS_FOR_SHARES,
  MIN_WARD_NEWSLETTERS_FOR_SHARES,
  type WardProfile,
} from "../../../lib/analytics/ward-profile";
import { EXPORT_TEXT_ATTRIBUTE } from "../../../lib/analytics/charts/export";
import { renderWardTopicGrid } from "../../../lib/analytics/charts/ward-grids";
import {
  renderDistinctiveTerms,
  renderWardCadence,
  renderWardTopicComparison,
} from "../../../lib/analytics/charts/ward-profile";
import { lensLabel, type DashboardRender, type DashboardState } from "../dashboard-state";
import {
  chartWidth,
  emptyMessage,
  panel,
  replaceContent,
  requireElement,
  setTable,
  tableHeading,
} from "../dom";

const WARD_GAP_LIMIT = 3;

/** The ward's typical gap and its longest gaps in these dates. */
function renderWardGaps(section: HTMLElement, profile: WardProfile, wardFacts: NewsletterFact[]): void {
  const { cadence, archiveCadence } = profile;
  const gaps = findLongestGaps(wardFacts, WARD_GAP_LIMIT);
  requireElement<HTMLElement>("#profile-gap-typical", section).textContent =
    cadence.medianDaysBetween === null
      ? "Fewer than two newsletters in these dates."
      : `Median ${formatMedian(cadence.medianDaysBetween)} days apart (all dates ${formatMedian(archiveCadence.medianDaysBetween)}). Longest:`;
  const namesAlderman = profile.aldermen.length > 1;
  requireElement<HTMLElement>("#profile-gaps", section).replaceChildren(
    ...gaps.map((gap) => {
      const item = document.createElement("li");
      item.setAttribute(EXPORT_TEXT_ATTRIBUTE, "");
      const alderman = namesAlderman && gap.alder ? ` · ${gap.alder}` : "";
      item.textContent = `${pluralize(gap.days, "day")}: ${formatDay(gap.from)} – ${formatDay(gap.to)}${alderman}`;
      return item;
    }),
  );
}

function wardProfileColumns(state: DashboardState): TableColumn<WardProfile["topics"][number]>[] {
  return [
    { label: "Topic", value: (topic) => lensLabel(state, topic.lens) },
    { label: "Months mentioning", value: (topic) => topic.monthsMentioning, numeric: true },
    { label: "Months with newsletters", value: (topic) => topic.monthsChecked, numeric: true },
    { label: "Newsletters mentioning", value: (topic) => topic.newslettersMentioning, numeric: true },
    { label: "Share of months", value: (topic) => (topic.wardShare === null ? "–" : formatPercent(topic.wardShare)), numeric: true },
    {
      label: "All wards (average)",
      value: (topic) => (topic.cityShare === null ? "–" : formatPercent(topic.cityShare)),
      numeric: true,
    },
  ];
}

/** The focused ward over the window's months; the chosen topic is outlined. */
export function renderWardProfilePanel({ state, filters, profile, factsIgnoringLens, months }: DashboardRender): void {
  const { section, caption, table } = panel("ward-profile");
  const message = requireElement<HTMLElement>("#profile-message", section);
  const content = requireElement<HTMLElement>("#profile-content", section);
  const tableView = requireElement<HTMLElement>("[data-table-view]", section);
  if (!profile) return;
  const { ward } = profile;
  const showMessage = (text: string) => {
    message.textContent = text;
    message.hidden = false;
    content.hidden = true;
    tableView.hidden = true;
    caption.textContent = "";
  };
  const lenses = state.data.lenses.lenses;
  if (profile.archiveNewsletters === 0) {
    showMessage(`No ${formatWard(ward)} newsletters in the archive yet.`);
    return;
  }
  message.hidden = true;
  content.hidden = false;
  tableView.hidden = false;
  const aldermen = profile.aldermen.join(", ");
  requireElement<HTMLElement>("#profile-heading", section).textContent = aldermen
    ? `${formatWard(ward)} · ${aldermen}`
    : formatWard(ward);
  caption.textContent = "";

  const cadenceChart = requireElement<HTMLElement>("#profile-cadence", section);
  replaceContent(
    cadenceChart,
    months.length ? renderWardCadence(profile.months, months, chartWidth(cadenceChart)) : emptyMessage("Nothing in these dates."),
  );
  renderWardGaps(section, profile, factsIgnoringLens);
  const topicsChart = requireElement<HTMLElement>("#profile-topics", section);
  replaceContent(
    topicsChart,
    months.length
      ? renderWardTopicGrid(profile.topicCells, lenses, months, ward, filters.lens, chartWidth(topicsChart))
      : emptyMessage("Nothing in these dates."),
  );

  const comparisonChart = requireElement<HTMLElement>("#profile-comparison", section);
  replaceContent(
    comparisonChart,
    profile.sharesShown
      ? renderWardTopicComparison(profile.topics, lenses, ward, chartWidth(comparisonChart))
      : emptyMessage(`Needs ${MIN_WARD_NEWSLETTERS_FOR_SHARES} newsletters across ${MIN_WARD_MONTHS_FOR_SHARES} months.`),
  );

  const distinctiveChart = requireElement<HTMLElement>("#profile-distinctive", section);
  const terms = state.data.distinctiveByWard[ward] ?? [];
  replaceContent(
    distinctiveChart,
    terms.length
      ? renderDistinctiveTerms(terms, ward, profile.archiveNewsletters, chartWidth(distinctiveChart))
      : emptyMessage("Too few newsletters."),
  );

  const topicTable = document.createElement("div");
  setTable(topicTable, wardProfileColumns(state), profile.topics);
  const monthTable = document.createElement("div");
  setTable(
    monthTable,
    [
      { label: "Month", value: (cell) => cell.month },
      { label: "Status", value: (cell) => COVERAGE_STATUS_LABELS[cell.status] },
      { label: "Newsletters", value: (cell) => cell.newsletters, numeric: true },
    ],
    profile.months,
  );
  const topicMonthTable = document.createElement("div");
  setTable(
    topicMonthTable,
    [
      { label: "Topic", value: (cell) => lensLabel(state, cell.lens) },
      { label: "Month", value: (cell) => cell.month },
      { label: "Newsletters mentioning", value: (cell) => cell.mentioning, numeric: true },
      { label: "Newsletters", value: (cell) => cell.newsletters, numeric: true },
      { label: "Share", value: (cell) => (cell.share === null ? "–" : formatPercent(cell.share)), numeric: true },
    ],
    profile.topicCells.filter((cell) => cell.share !== null),
  );
  const termTable = document.createElement("div");
  setTable(
    termTable,
    [
      { label: "Term", value: (item) => item.term },
      { label: "Ward newsletters", value: (item) => item.ward_newsletters, numeric: true },
      { label: "Ward share", value: (item) => formatPercent(item.ward_share), numeric: true },
      { label: "Rest of city share", value: (item) => formatPercent(item.rest_share), numeric: true },
      { label: "Related terms", value: (item) => item.related_terms ?? 0, numeric: true },
    ],
    terms,
  );
  replaceContent(
    table,
    tableHeading("Topics"),
    topicTable,
    tableHeading("Newsletters by month"),
    monthTable,
    tableHeading("Topics by month"),
    topicMonthTable,
    tableHeading("Distinctive vocabulary (all dates)"),
    termTable,
  );
}
