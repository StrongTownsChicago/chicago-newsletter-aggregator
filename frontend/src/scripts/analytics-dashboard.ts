// Client wiring for /analytics: reads the filters, recomputes each panel with
// the pure functions in lib/, renders the charts, and mirrors the view in the URL.
import {
  buildCoverageGrid,
  describeDataAsOf,
  buildLensWardGrid,
  classifyDateWindow,
  computeLensWardReach,
  EMPTY_FILTERS,
  expandTermPostings,
  filterFacts,
  findBroadCoverageWindow,
  daysBetween,
  findLongestGaps,
  formatDay,
  formatMonth,
  isReachFaded,
  listSourceWards,
  listWards,
  listWindowMonths,
  MIN_ACTIVE_WARDS_FOR_REACH,
  MIN_MONTH_NEWSLETTERS_FOR_SHARES,
  monthOf,
  normalizeTermQuery,
  resolveIndexedTerm,
  searchScopeForFilters,
  suggestTerms,
  summarizeWardCounts,
  summarizeWardCoverage,
  termMentionsByMonth,
  termMentionsByWard,
  trimSparseEdges,
  wardsInScope,
  type AnalyticsDataset,
  type AnalyticsFilters,
  type BroadCoverageWindow,
  type CoverageStatus,
  type LensDefinition,
  type LensReachCell,
  type NewsletterFact,
  type RisingTerm,
  type TermIndex,
} from "../lib/analytics";
import {
  formatOptionalShare,
  formatPercent,
  formatWard,
  LENS_WARD_STATUS_LABELS,
  renderCivicCalendar,
  renderCoverageGrid,
  renderDistinctiveTerms,
  renderLensWardGrid,
  renderReachTrend,
  renderRisingTerms,
  renderSparkline,
  renderTermTimeline,
  renderTermWards,
  renderWardCadence,
  renderWardTopicComparison,
  renderWardTopicGrid,
  sourceLabel,
} from "../lib/analytics-charts";
import { createLazyLoader, fetchTermIndex } from "../lib/analytics-data";
import { renderTable, type TableColumn } from "../lib/analytics-table";
import {
  describeBroadCoverageRule,
  describeTopicDefinition,
  describeTopicMatching,
  pluralize,
} from "../lib/analytics-descriptions";
import {
  buildCanonicalViewUrl,
  chooseHistoryMode,
  parseDashboardUrlState,
  reconcileDateWindow,
  serializeDashboardUrlState,
  type DashboardUrlContext,
  type DashboardViewState,
} from "../lib/analytics-url-state";
import {
  buildWardProfile,
  MIN_WARD_MONTHS_FOR_SHARES,
  MIN_WARD_NEWSLETTERS_FOR_SHARES,
  type WardProfile,
} from "../lib/analytics-ward-profile";
import {
  describeSparkline,
  findAsOfMonth,
  findLargestChangeTopic,
  findPeakPoint,
  findWidestReachTopic,
  formatPointChange,
  formatPoints,
  isPartialMonth,
  listFullMonths,
  orderBySwing,
  summarizeTopicTrends,
  tightShareDomain,
  type TopicTrend,
} from "../lib/analytics-topic-trends";
import {
  clearViewSelection,
  DASHBOARD_PANEL_IDS,
  describeDashboardView,
  focusedWard,
  selectDashboardView,
  VIEW_PANELS,
  type DashboardPanelId,
  type DashboardView,
} from "../lib/analytics-views";
import { downloadChartPng, EXPORT_TEXT_ATTRIBUTE } from "../lib/chart-export";
import { SITE_NAME } from "../lib/seo";

const TERM_WARD_LIMIT = 15;
const TERM_SUGGESTION_LIMIT = 8;
const GAP_LIMIT = 10;
const WARD_GAP_LIMIT = 3;
const COVERAGE_STATUS_LABELS: Record<CoverageStatus, string> = {
  untracked: "Not tracked yet",
  silent: "None received",
  received: "Received",
};
const RESIZE_DEBOUNCE_MS = 200;
const EXPORT_FAILURE_MESSAGE_MS = 3000;
const numberFormat = new Intl.NumberFormat("en-US");

interface DashboardState {
  data: AnalyticsDataset;
  wardBySource: Map<number, string | null>;
  lensById: Map<string, LensDefinition>;
  /** Every ward with a source, including wards with no newsletters archived. */
  allWards: string[];
  /** Every month from the first to the latest newsletter. */
  dataMonths: string[];
  /** The month the data was generated in; it and later months are partial. */
  asOfMonth: string | null;
  broadWindow: BroadCoverageWindow | null;
  /** The values a shared URL may choose from. */
  urlContext: DashboardUrlContext;
  term: string;
  /** Null until the term explorer first needs it. */
  terms: TermIndex | null;
  termsError: string | null;
  /** The view whose panel layout is on the page; null before the first render. */
  view: DashboardView | null;
}

// Shared by every request so concurrent triggers fetch terms.json once.
const loadTermIndex = createLazyLoader(() => fetchTermIndex());

function requireElement<T extends Element>(selector: string, root: ParentNode = document): T {
  const element = root.querySelector<T>(selector);
  if (!element) throw new Error(`Analytics dashboard element not found: ${selector}`);
  return element;
}

function panel(id: string) {
  const section = requireElement<HTMLElement>(`#${id}`);
  return {
    section,
    chart: section.querySelector<HTMLElement>("[data-chart]"),
    caption: requireElement<HTMLElement>("[data-caption]", section),
    table: section.querySelector<HTMLElement>("[data-table]"),
  };
}

function chartWidth(container: HTMLElement): number {
  return Math.max(container.clientWidth, 320);
}

function replaceContent(container: HTMLElement | null, ...nodes: Node[]): void {
  container?.replaceChildren(...nodes);
}

function emptyMessage(text: string): HTMLElement {
  const message = document.createElement("p");
  message.className = "text-sm text-gray-500 py-6 text-center";
  message.textContent = text;
  return message;
}

function setTable<T>(container: HTMLElement | null, columns: TableColumn<T>[], rows: T[]): void {
  replaceContent(container, rows.length ? renderTable(columns, rows) : emptyMessage("No rows."));
}

function tableHeading(text: string): HTMLElement {
  const heading = document.createElement("h3");
  heading.className = "text-sm font-semibold text-gray-700 mt-3 mb-1";
  heading.textContent = text;
  return heading;
}

function describeMonthSpan(months: string[]): string {
  return months.length ? `${formatMonth(months[0])} – ${formatMonth(months[months.length - 1])}` : "–";
}

// ---------------------------------------------------------------------------
// Filters

function readFilters(form: HTMLFormElement): AnalyticsFilters {
  const formData = new FormData(form);
  const wards = [...form.querySelectorAll<HTMLInputElement>('input[name="ward"]:checked')].map(
    (input) => input.value,
  );
  return {
    wards,
    lens: (formData.get("lens") as string) || null,
    fromMonth: (formData.get("from") as string) || null,
    toMonth: (formData.get("to") as string) || null,
  };
}

function populateFilterOptions(
  form: HTMLFormElement,
  wards: string[],
  months: string[],
  lenses: LensDefinition[],
  defaultFromMonth: string | null,
): void {
  requireElement<HTMLSelectElement>('select[name="lens"]', form).append(
    ...lenses.map((lens) => new Option(lens.label, lens.id)),
  );
  const wardOptions = requireElement<HTMLElement>("#ward-options");
  wardOptions.replaceChildren(
    ...wards.map((ward) => {
      const label = document.createElement("label");
      label.className = "flex items-center gap-1 text-sm text-gray-700 px-1 py-0.5 rounded hover:bg-gray-50";
      const input = document.createElement("input");
      input.type = "checkbox";
      input.name = "ward";
      input.value = ward;
      input.setAttribute("aria-label", formatWard(ward));
      label.append(input, ward);
      return label;
    }),
  );
  for (const name of ["from", "to"]) {
    const select = requireElement<HTMLSelectElement>(`select[name="${name}"]`, form);
    select.append(...months.map((month) => new Option(formatMonth(month), month)));
  }
  // Start on the broad-coverage window. defaultSelected makes "Reset filters" return to it.
  const defaultOption = [...requireElement<HTMLSelectElement>('select[name="from"]', form).options].find(
    (option) => option.value === defaultFromMonth,
  );
  if (defaultOption) {
    defaultOption.defaultSelected = true;
    defaultOption.selected = true;
  }
}

/** Open-ended date window starting at fromMonth (null = the start of the archive). */
function setDateWindow(form: HTMLFormElement, fromMonth: string | null): void {
  requireElement<HTMLSelectElement>('select[name="from"]', form).value = fromMonth ?? "";
  requireElement<HTMLSelectElement>('select[name="to"]', form).value = "";
}

function updateWardSummary(filters: AnalyticsFilters): void {
  const summary = requireElement<HTMLElement>("#ward-summary");
  summary.textContent =
    filters.wards.length === 0
      ? "All wards"
      : filters.wards.length <= 3
        ? filters.wards.map(formatWard).join(", ")
        : `${filters.wards.length} wards`;
}

function renderDateWindowStatus(state: DashboardState, filters: AnalyticsFilters): void {
  const status = requireElement<HTMLElement>("#date-window-status");
  const toggle = requireElement<HTMLButtonElement>("#date-window-toggle");
  const broadWindow = state.broadWindow;
  const kind = classifyDateWindow(filters, broadWindow);
  const span = describeMonthSpan(listWindowMonths(filters, state.dataMonths));
  toggle.hidden = !broadWindow;
  toggle.textContent = kind === "full" ? "Show default dates" : "Show all dates";
  if (broadWindow && kind === "broad") {
    status.textContent = `${span}: months when ${describeBroadCoverageRule(broadWindow)}.`;
  } else if (broadWindow && kind === "full") {
    status.textContent =
      `${span}. Before ${formatMonth(broadWindow.startMonth)}, at most ` +
      `${pluralize(broadWindow.maxActiveWardsBefore, "ward")} a month sent newsletters.`;
  } else {
    status.textContent = `${span}.`;
  }
}

// ---------------------------------------------------------------------------
// Panels

/** City-wide views fade thin months; a ward selection is small by design. */
function reachFadeThreshold(filters: AnalyticsFilters): number {
  return filters.wards.length ? 0 : MIN_ACTIVE_WARDS_FOR_REACH;
}

function lensLabel(state: DashboardState, lensId: string): string {
  return state.lensById.get(lensId)?.label ?? lensId;
}

/** Ward reach for every topic in the window, and each topic's trend over its full months. */
interface TopicOverview {
  cells: LensReachCell[];
  /** In the lens file's order. */
  trends: TopicTrend[];
  fullMonths: string[];
  threshold: number;
}

function buildTopicOverview(
  state: DashboardState,
  filters: AnalyticsFilters,
  scopeFacts: NewsletterFact[],
  months: string[],
): TopicOverview {
  const lensIds = state.data.lenses.lenses.map((lens) => lens.id);
  const cells = computeLensWardReach(scopeFacts, lensIds, months);
  const fullMonths = listFullMonths(months, state.asOfMonth);
  const threshold = reachFadeThreshold(filters);
  return { cells, trends: summarizeTopicTrends(cells, lensIds, fullMonths, threshold), fullMonths, threshold };
}

/** The last full month's reach cell, or null when no ward sent newsletters then. */
function latestReachCell(trend: TopicTrend): LensReachCell | null {
  return trend.latest && trend.latest.activeWards > 0 ? trend.latest : null;
}

/** "28 of 37": wards mentioning a topic in the last full month, of wards sending. */
function formatLatestReach(trend: TopicTrend): string {
  const latest = latestReachCell(trend);
  return latest ? `${latest.wardsMentioning} of ${latest.activeWards}` : "–";
}

/** "28 of 37 wards". */
function describeTopicReach(trend: TopicTrend): string {
  return latestReachCell(trend) ? `${formatLatestReach(trend)} wards` : "";
}

/** Everything one render of the dashboard needs, computed once. */
interface DashboardRender {
  state: DashboardState;
  filters: AnalyticsFilters;
  facts: NewsletterFact[];
  factsIgnoringLens: NewsletterFact[];
  months: string[];
  overview: TopicOverview;
  /** The focused ward's profile in the ward view, else null. */
  profile: WardProfile | null;
  selectTopic: (lensId: string) => void;
}

interface SummaryTile {
  label: string;
  value: string;
  detail: string;
}

function buildTile({ label, value, detail }: SummaryTile): HTMLElement {
  const tile = document.createElement("div");
  tile.className = "bg-white rounded-lg shadow-md p-4 border border-gray-200";
  const parts: [string, string, string][] = [
    [label, "tileLabel", "text-sm text-gray-600"],
    [value, "tileValue", "text-xl sm:text-2xl font-semibold text-gray-900 mt-1"],
    [detail, "tileDetail", "text-xs text-gray-500 mt-1"],
  ];
  tile.append(
    ...parts.map(([text, dataKey, className]) => {
      const line = document.createElement("p");
      line.className = className;
      line.dataset[dataKey] = "";
      line.textContent = text;
      return line;
    }),
  );
  return tile;
}

/** ", Mar 2026": the last full month, for tile labels. */
function inLatestFullMonth(overview: TopicOverview): string {
  const latestMonth = overview.fullMonths.at(-1);
  return latestMonth ? `, ${formatMonth(latestMonth)}` : "";
}

function newslettersTile({ state, filters, facts }: DashboardRender): SummaryTile {
  const span = describeMonthSpan(listWindowMonths(filters, state.dataMonths));
  return {
    label: "Newsletters",
    value: numberFormat.format(facts.length),
    detail: filters.lens ? `${span} · mentioning ${lensLabel(state, filters.lens)}` : span,
  };
}

function wardsSendingTile({ state, filters, factsIgnoringLens }: DashboardRender): SummaryTile {
  const wardCounts = summarizeWardCounts(wardsInScope(state.allWards, filters), factsIgnoringLens, state.data.newsletters);
  const neverArchived = wardCounts.wardsNeverArchived;
  return {
    label: "Wards sending",
    value: `${wardCounts.wardsWithNewsletters} of ${wardCounts.scopeWards}`,
    detail: neverArchived.length ? `None archived: ${neverArchived.join(", ")}` : "",
  };
}

function buildOverviewTiles(render: DashboardRender): SummaryTile[] {
  const { state, overview } = render;
  const widest = findWidestReachTopic(overview.trends);
  const largestChange = findLargestChangeTopic(overview.trends);
  return [
    newslettersTile(render),
    wardsSendingTile(render),
    {
      label: `Most mentioned topic${inLatestFullMonth(overview)}`,
      value: widest ? lensLabel(state, widest.lens) : "–",
      detail: widest ? describeTopicReach(widest) : "",
    },
    {
      label: `Biggest change${inLatestFullMonth(overview)}`,
      value: largestChange ? lensLabel(state, largestChange.lens) : "–",
      detail:
        largestChange?.latestChange != null
          ? `${describeTopicReach(largestChange)}, ${formatPointChange(largestChange.latestChange)} vs average`
          : "",
    },
  ];
}

function buildTopicTiles(render: DashboardRender): SummaryTile[] {
  const { filters, overview } = render;
  const trend = overview.trends.find((item) => item.lens === filters.lens) ?? null;
  const peak = trend ? findPeakPoint(trend) : null;
  const peakCell = peak ? overview.cells.find((cell) => cell.lens === filters.lens && cell.month === peak.month) : null;
  return [
    newslettersTile(render),
    wardsSendingTile(render),
    {
      label: `Wards mentioning it${inLatestFullMonth(overview)}`,
      value: trend ? formatLatestReach(trend) : "–",
      detail: trend?.latestChange != null ? `${formatPointChange(trend.latestChange)} vs its average` : "",
    },
    {
      label: "Peak month",
      value: peak ? formatMonth(peak.month) : "–",
      detail: peakCell ? `${peakCell.wardsMentioning} of ${peakCell.activeWards} wards` : "",
    },
  ];
}

/** "Newest in the archive", "12 days before the archive's newest". */
function describeRecency(date: string, archiveLastDate: string | null): string {
  if (!archiveLastDate) return "";
  const days = daysBetween(date, archiveLastDate);
  return days <= 0 ? "Newest in the archive" : `${pluralize(days, "day")} before the archive's newest`;
}

function buildWardTiles({ state, filters, profile }: DashboardRender): SummaryTile[] {
  if (!profile) return [];
  const { cadence, archiveCadence } = profile;
  const span = describeMonthSpan(listWindowMonths(filters, state.dataMonths));
  const topic = filters.lens ? profile.topics.find((item) => item.lens === filters.lens) : undefined;
  return [
    {
      label: "Newsletters a month",
      value: formatMedian(cadence.medianPerTrackedMonth),
      detail: `All wards ${formatMedian(profile.cityMedianPerTrackedMonth)} · all dates ${formatMedian(archiveCadence.medianPerTrackedMonth)}`,
    },
    {
      label: "Last newsletter",
      value: profile.lastDate ? formatDay(profile.lastDate) : "–",
      detail: profile.lastDate ? describeRecency(profile.lastDate, state.data.metadata.last_date) : "None archived",
    },
    {
      label: "Newsletters",
      value: numberFormat.format(profile.windowNewsletters),
      detail: topic
        ? `${span} · ${numberFormat.format(topic.newslettersMentioning)} mention ${lensLabel(state, topic.lens)}`
        : span,
    },
    {
      label: "Coverage start",
      value: profile.firstDate ? formatDay(profile.firstDate) : "–",
      detail: `${pluralize(profile.archiveNewsletters, "newsletter")}, all dates`,
    },
  ];
}

const VIEW_TILES: Record<DashboardView, (render: DashboardRender) => SummaryTile[]> = {
  overview: buildOverviewTiles,
  topic: buildTopicTiles,
  ward: buildWardTiles,
};

function renderCoveragePanel(state: DashboardState, filters: AnalyticsFilters): void {
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

function renderTermExplorer(state: DashboardState, filters: AnalyticsFilters): void {
  const { section, caption, table } = panel("term-explorer");
  const message = requireElement<HTMLElement>("#term-message", section);
  const results = requireElement<HTMLElement>("#term-results", section);
  const timeline = requireElement<HTMLElement>("#term-timeline", section);
  const wardsChart = requireElement<HTMLElement>("#term-wards", section);
  const suggestions = requireElement<HTMLElement>("#term-suggestions", section);
  const tableView = requireElement<HTMLElement>("[data-table-view]", section);
  const { metadata } = state.data;
  caption.textContent = `${numberFormat.format(metadata.term_count)} terms, each in ${metadata.min_term_newsletters}+ newsletters.`;

  const showResults = (shown: boolean) => {
    results.hidden = !shown;
    tableView.hidden = !shown;
    if (shown) return;
    timeline.replaceChildren();
    wardsChart.replaceChildren();
    table?.replaceChildren();
  };

  const term = normalizeTermQuery(state.term);
  const index = state.terms;
  if (!index) {
    suggestions.replaceChildren();
    showResults(false);
    message.textContent = !term
      ? ""
      : state.termsError
        ? `Couldn't load terms (${state.termsError}). Search again to retry.`
        : "Loading terms…";
    return;
  }
  const suggestionTerms = suggestTerms(index, term, TERM_SUGGESTION_LIMIT);
  suggestions.replaceChildren(
    ...suggestionTerms.map((suggestion) => {
      const button = document.createElement("button");
      button.type = "button";
      button.dataset.term = suggestion;
      button.className = "px-3 py-1 text-sm bg-blue-50 text-blue-700 rounded-full hover:bg-blue-100";
      button.textContent = suggestion;
      return button;
    }),
  );

  if (!term) {
    message.textContent = "";
    showResults(false);
    return;
  }
  const indexedTerm = resolveIndexedTerm(index, term);
  if (indexedTerm === null) {
    message.textContent = `"${term}" isn't indexed: too rare, too common, or longer than two words.`;
    showResults(false);
    return;
  }

  const scopeFacts = filterFacts(state.data.newsletters, filters, { ignoreLens: true });
  const postings = index.terms[indexedTerm];
  const bucketCounts = expandTermPostings(index, postings, state.wardBySource, filters);
  const months = termMentionsByMonth(bucketCounts, scopeFacts);
  const wards = termMentionsByWard(bucketCounts, scopeFacts);
  const totalMentions = months.reduce((total, point) => total + point.mentions, 0);
  // A query can match another written form of the term ("bike lane" finds "bike lanes").
  message.textContent = `"${indexedTerm}" appears in ${numberFormat.format(totalMentions)} of ${pluralize(scopeFacts.length, "newsletter")}.`;

  if (totalMentions === 0) {
    showResults(false);
    return;
  }
  showResults(true);
  const timelinePoints = trimSparseEdges(months);
  timeline.replaceChildren(
    timelinePoints.length
      ? renderTermTimeline(timelinePoints, chartWidth(timeline))
      : emptyMessage(`No month has ${MIN_MONTH_NEWSLETTERS_FOR_SHARES}+ newsletters to chart. See the table.`),
  );
  wardsChart.replaceChildren(
    renderTermWards(
      wards.slice(0, TERM_WARD_LIMIT),
      indexedTerm,
      searchScopeForFilters(filters),
      chartWidth(wardsChart),
    ),
  );
  setTable(
    table,
    [
      { label: "Month", value: (point) => point.month },
      { label: "Newsletters mentioning", value: (point) => point.mentions, numeric: true },
      { label: "All newsletters", value: (point) => point.newsletters, numeric: true },
      { label: "Share", value: (point) => formatOptionalShare(point.share), numeric: true },
    ],
    months,
  );
}

function reachColumns(state: DashboardState, minActiveWards: number): TableColumn<LensReachCell>[] {
  return [
    { label: "Topic", value: (cell) => lensLabel(state, cell.lens) },
    { label: "Month", value: (cell) => cell.month },
    { label: "Wards mentioning", value: (cell) => cell.wardsMentioning, numeric: true },
    { label: "Active wards", value: (cell) => cell.activeWards, numeric: true },
    { label: "Share", value: (cell) => (cell.share === null ? "–" : formatPercent(cell.share)), numeric: true },
    { label: "Note", value: (cell) => (isReachFaded(cell, minActiveWards) ? "Few wards (faded)" : "") },
  ];
}

/** An element whose text the PNG export draws. */
function exportText<K extends "td" | "th" | "span">(tag: K, text: string, className: string): HTMLElementTagNameMap[K] {
  const element = document.createElement(tag);
  element.className = className;
  element.setAttribute(EXPORT_TEXT_ATTRIBUTE, "");
  element.textContent = text;
  return element;
}


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

function renderCivicCalendarPanel(
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

function renderLensDefinitions(state: DashboardState): void {
  const container = requireElement<HTMLElement>("[data-lens-definitions]");
  const summary = state.data.lenses;
  const rules = document.createElement("p");
  rules.textContent =
    `${describeTopicMatching(summary)} Counts are of ${pluralize(summary.readable_newsletters, "newsletter")}, all dates. ` +
    "Strong Towns Chicago focus topics overlap the broader ones.";
  const list = document.createElement("dl");
  list.className = "space-y-2";
  for (const lens of summary.lenses) {
    const { title, body } = describeTopicDefinition(lens, summary.readable_newsletters);
    const term = document.createElement("dt");
    term.className = "font-semibold text-gray-900";
    term.textContent = title;
    const definition = document.createElement("dd");
    definition.textContent = body;
    list.append(term, definition);
  }
  container.replaceChildren(rules, list);
}

/** The chosen topic's ward-reach trend and its ward × month grid. */
function renderTopicDetailPanel({ state, filters, overview, factsIgnoringLens: scopeFacts, months }: DashboardRender): void {
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

const medianFormat = new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 });

function formatMedian(value: number | null): string {
  return value === null ? "–" : medianFormat.format(value);
}

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
function renderWardProfilePanel({ state, filters, profile, factsIgnoringLens, months }: DashboardRender): void {
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

function renderRisingPanel(state: DashboardState): void {
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
          `Typical month (median, ${baselineSpan})`,
          latest,
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

function renderCadencePanel(facts: NewsletterFact[]): void {
  const { section, caption } = panel("sending-cadence");
  caption.textContent = `From ${pluralize(facts.length, "newsletter")}.`;
  setTable(
    requireElement<HTMLElement>("#cadence-gaps", section),
    [
      { label: "Source", value: (gap) => sourceLabel({ name: gap.alder ?? `Source ${gap.sourceId}`, ward: gap.ward }) },
      { label: "From", value: (gap) => gap.from },
      { label: "To", value: (gap) => gap.to },
      { label: "Days", value: (gap) => gap.days, numeric: true },
    ],
    findLongestGaps(facts, GAP_LIMIT),
  );
}


// ---------------------------------------------------------------------------
// PNG export

/** Panels whose numbers ignore the global filters, described as such in the export. */
const CITY_WIDE_PANELS = new Set(["rising-terms"]);

function describeWardScope(filters: AnalyticsFilters): string {
  if (filters.wards.length === 0) return "All wards";
  return filters.wards.length === 1
    ? formatWard(filters.wards[0])
    : `Wards ${filters.wards.join(", ")}`;
}

function describeExportScope(state: DashboardState, panelId: string, view: DashboardViewState): string {
  if (CITY_WIDE_PANELS.has(panelId)) return "City-wide";
  const span = describeMonthSpan(listWindowMonths(view.filters, state.dataMonths));
  return `${span} · ${describeWardScope(view.filters)}`;
}

function describeExportTitle(state: DashboardState, panelId: string, title: string, view: DashboardViewState): string {
  const lens = view.filters.lens ? lensLabel(state, view.filters.lens) : null;
  const ward = focusedWard(view.filters);
  if (panelId === "topic-detail" && lens) return `${title}: ${lens}`;
  if (panelId === "term-explorer" && view.term) return `${title}: "${view.term}"`;
  if (panelId === "ward-profile" && ward) return `${title}: ${formatWard(ward)}`;
  return title;
}

/** The production page URL from the layout's canonical link, so exports never cite a preview or local origin. */
function canonicalPageUrl(): string {
  return document.querySelector<HTMLLinkElement>('link[rel="canonical"]')?.href ?? window.location.href;
}

function exportRegion(section: HTMLElement): HTMLElement | null {
  return section.querySelector<HTMLElement>("[data-export-region]") ?? section.querySelector<HTMLElement>("[data-chart]");
}

/** Show each export button only while its panel shows a chart. */
function refreshExportButtons(): void {
  document.querySelectorAll<HTMLButtonElement>("button[data-export-png]").forEach((button) => {
    const section = button.closest<HTMLElement>("section");
    const hasChart = Boolean(section && exportRegion(section)?.querySelector("svg"));
    button.disabled = !hasChart;
    button.hidden = !hasChart;
  });
}

async function exportPanel(state: DashboardState, button: HTMLButtonElement, view: DashboardViewState): Promise<void> {
  const section = button.closest<HTMLElement>("section");
  const region = section ? exportRegion(section) : null;
  if (!section || !region) return;
  const panelId = button.dataset.exportPng ?? section.id;
  const title = requireElement<HTMLElement>("h2", section).textContent?.trim() ?? "";
  button.disabled = true;
  const label = button.textContent;
  try {
    await downloadChartPng(region, {
      title: describeExportTitle(state, panelId, title, view),
      scope: describeExportScope(state, panelId, view),
      caption: requireElement<HTMLElement>("[data-caption]", section).textContent?.trim() ?? "",
      dataAsOf: describeDataAsOf(state.data.metadata),
      siteName: SITE_NAME,
      pageUrl: buildCanonicalViewUrl(canonicalPageUrl(), serializeDashboardUrlState(view, state.urlContext)),
    });
  } catch (error) {
    console.error("Chart export failed", error);
    button.textContent = "Download failed";
    setTimeout(() => {
      button.textContent = label;
    }, EXPORT_FAILURE_MESSAGE_MS);
  } finally {
    button.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Orchestration

const PANEL_RENDERERS: Record<DashboardPanelId, (render: DashboardRender) => void> = {
  "term-explorer": ({ state, filters }) => renderTermExplorer(state, filters),
  "civic-calendar": ({ state, filters, overview, months, selectTopic }) =>
    renderCivicCalendarPanel(state, filters, overview, months, selectTopic),
  "topic-detail": renderTopicDetailPanel,
  "ward-profile": renderWardProfilePanel,
  "rising-terms": ({ state }) => renderRisingPanel(state),
  "sending-cadence": ({ factsIgnoringLens }) => renderCadencePanel(factsIgnoringLens),
  coverage: ({ state, filters }) => renderCoveragePanel(state, filters),
};

/** Show the view's panels in its order and hide the rest. */
function applyViewLayout(view: DashboardView): void {
  const panels = VIEW_PANELS[view];
  for (const id of DASHBOARD_PANEL_IDS) requireElement<HTMLElement>(`#${id}`).hidden = !panels.includes(id);
  requireElement<HTMLElement>("#dashboard-panels").append(...panels.map((id) => requireElement<HTMLElement>(`#${id}`)));
}

/**
 * Name the view in the heading. `announce` also reads a new view out; it is
 * false when focus moves to a heading that names it, which screen readers read anyway.
 */
function renderViewBar(state: DashboardState, filters: AnalyticsFilters, view: DashboardView, announce: boolean): void {
  // The overview keeps its heading for screen readers only, so the page looks as before.
  requireElement<HTMLElement>("#dashboard-view-bar").classList.toggle("sr-only", view === "overview");
  requireElement<HTMLButtonElement>("#back-to-overview").hidden = view === "overview";
  const heading = requireElement<HTMLElement>("#dashboard-view-heading");
  const text = describeDashboardView(filters, { ward: formatWard, topic: (lensId) => lensLabel(state, lensId) });
  if (heading.textContent === text) return;
  heading.textContent = text;
  // Cleared when not announced, so returning to the same view later is still read out.
  requireElement<HTMLElement>("#dashboard-view-status").textContent = announce ? text : "";
}

function buildRender(state: DashboardState, filters: AnalyticsFilters, selectTopic: (lensId: string) => void): DashboardRender {
  const factsIgnoringLens = filterFacts(state.data.newsletters, filters, { ignoreLens: true });
  const months = listWindowMonths(filters, state.dataMonths);
  const ward = focusedWard(filters);
  return {
    state,
    filters,
    facts: filterFacts(state.data.newsletters, filters),
    factsIgnoringLens,
    months,
    overview: buildTopicOverview(state, filters, factsIgnoringLens, months),
    profile:
      ward === null
        ? null
        : buildWardProfile(
            state.data.newsletters,
            state.data.sources,
            ward,
            months,
            state.dataMonths,
            state.urlContext.lensIds,
          ),
    selectTopic,
  };
}

function renderDashboard(
  state: DashboardState,
  controls: DashboardControls,
  selectTopic: (lensId: string) => void,
  announce: boolean,
): void {
  const filters = readFilters(controls.form);
  const view = selectDashboardView(filters);
  updateWardSummary(filters);
  controls.profileSelect.value = focusedWard(filters) ?? "";
  // Moving panels drops focus inside them, so reorder only when the view changes.
  if (view !== state.view) {
    applyViewLayout(view);
    state.view = view;
  }
  renderViewBar(state, filters, view, announce);
  renderDateWindowStatus(state, filters);
  const render = buildRender(state, filters, selectTopic);
  requireElement<HTMLElement>("#summary-tiles").replaceChildren(...VIEW_TILES[view](render).map(buildTile));
  for (const id of VIEW_PANELS[view]) PANEL_RENDERERS[id](render);
  refreshExportButtons();
}

/** Fetch the term index once, then redraw the term explorer with it (or with the error). */
function requestTermIndex(state: DashboardState, readCurrentFilters: () => AnalyticsFilters): void {
  if (state.terms) return;
  state.termsError = null;
  loadTermIndex()
    .then((terms) => {
      state.terms = terms;
    })
    .catch((error: unknown) => {
      state.termsError = error instanceof Error ? error.message : String(error);
    })
    .finally(() => {
      renderTermExplorer(state, readCurrentFilters());
      refreshExportButtons();
    });
}

function buildDashboardState(data: AnalyticsDataset): DashboardState {
  const factMonths = data.newsletters.map((fact) => monthOf(fact.date)).sort();
  const allWards = listSourceWards(data.sources);
  const dataMonths = listWindowMonths(EMPTY_FILTERS, factMonths);
  const broadWindow = findBroadCoverageWindow(data.newsletters);
  return {
    data,
    wardBySource: new Map(data.sources.map((source) => [source.id, source.ward])),
    lensById: new Map(data.lenses.lenses.map((lens) => [lens.id, lens])),
    allWards,
    dataMonths,
    asOfMonth: findAsOfMonth(data.metadata.generated_at),
    broadWindow,
    urlContext: {
      wards: allWards,
      months: dataMonths,
      lensIds: data.lenses.lenses.map((lens) => lens.id),
      defaultFromMonth: broadWindow?.startMonth ?? null,
    },
    term: "",
    terms: null,
    termsError: null,
    view: null,
  };
}

/** The dashboard's controls, looked up once. */
interface DashboardControls {
  form: HTMLFormElement;
  profileSelect: HTMLSelectElement;
  termInput: HTMLInputElement;
}

function readViewState(state: DashboardState, controls: DashboardControls): DashboardViewState {
  return {
    filters: readFilters(controls.form),
    term: normalizeTermQuery(state.term),
  };
}

function setWardSelection(form: HTMLFormElement, wards: string[]): void {
  form.querySelectorAll<HTMLInputElement>('input[name="ward"]').forEach((input) => {
    input.checked = wards.includes(input.value);
  });
}

/** Set every control to a view (from the URL) without rendering. */
function applyViewState(state: DashboardState, controls: DashboardControls, view: DashboardViewState): void {
  const { form, termInput } = controls;
  setWardSelection(form, view.filters.wards);
  requireElement<HTMLSelectElement>('select[name="lens"]', form).value = view.filters.lens ?? "";
  requireElement<HTMLSelectElement>('select[name="from"]', form).value = view.filters.fromMonth ?? "";
  requireElement<HTMLSelectElement>('select[name="to"]', form).value = view.filters.toMonth ?? "";
  termInput.value = view.term;
  state.term = view.term;
}

function dashboardUrl(query: string): string {
  return `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
}

let lastHistoryPushMs: number | null = null;

/**
 * Record the current view in the URL. A change gets a history entry, except
 * that a quick burst of changes (ticking several wards) shares one.
 */
function syncUrl(state: DashboardState, controls: DashboardControls, mode: "change" | "replace"): void {
  const url = dashboardUrl(serializeDashboardUrlState(readViewState(state, controls), state.urlContext));
  if (mode === "change" && url === `${window.location.pathname}${window.location.search}${window.location.hash}`) return;
  const now = performance.now();
  if (mode === "change" && chooseHistoryMode(now, lastHistoryPushMs) === "push") {
    window.history.pushState(null, "", url);
    lastHistoryPushMs = now;
  } else {
    window.history.replaceState(null, "", url);
  }
}

export function startAnalyticsDashboard(data: AnalyticsDataset): void {
  const state = buildDashboardState(data);
  const controls: DashboardControls = {
    form: requireElement<HTMLFormElement>("#analytics-filters"),
    profileSelect: requireElement<HTMLSelectElement>("#profile-ward"),
    termInput: requireElement<HTMLInputElement>("#term-input"),
  };
  const { form, profileSelect, termInput } = controls;
  populateFilterOptions(
    form,
    state.urlContext.wards,
    state.dataMonths,
    data.lenses.lenses,
    state.urlContext.defaultFromMonth,
  );
  profileSelect.append(...state.allWards.map((ward) => new Option(formatWard(ward), ward)));
  renderLensDefinitions(state);

  const filtersNow = () => readFilters(form);
  /** Choose a topic from the overview, then bring its detail into view. */
  const selectTopic = (lensId: string) => {
    requireElement<HTMLSelectElement>('select[name="lens"]', form).value = lensId;
    commit({ announce: false });
    requireElement<HTMLElement>("#topic-detail").scrollIntoView({ behavior: "smooth", block: "start" });
    // The clicked control was redrawn; move focus to where the reader now is.
    requireElement<HTMLElement>("#topic-detail-heading").focus({ preventScroll: true });
  };
  const rerender = ({ announce = true } = {}) => renderDashboard(state, controls, selectTopic, announce);
  /** Render a change the reader made and record it in the history. */
  const commit = ({ announce = true } = {}) => {
    rerender({ announce });
    syncUrl(state, controls, "change");
  };
  const restoreFromUrl = ({ announce }: { announce: boolean }) => {
    applyViewState(state, controls, parseDashboardUrlState(new URLSearchParams(window.location.search), state.urlContext));
    if (state.term) requestTermIndex(state, filtersNow);
    rerender({ announce });
  };

  form.addEventListener("change", (event) => {
    const target = event.target as HTMLInputElement;
    // The ward profile select is a shortcut to selecting just that ward.
    if (event.target === profileSelect) setWardSelection(form, profileSelect.value ? [profileSelect.value] : []);
    if (target.name === "from" || target.name === "to") {
      const { fromMonth, toMonth } = reconcileDateWindow(readFilters(form), target.name);
      requireElement<HTMLSelectElement>('select[name="from"]', form).value = fromMonth ?? "";
      requireElement<HTMLSelectElement>('select[name="to"]', form).value = toMonth ?? "";
    }
    commit();
  });
  form.addEventListener("reset", () => {
    requireElement<HTMLDetailsElement>("#ward-picker").open = false;
    // Form reset updates control values after the event; render on the next tick.
    setTimeout(() => commit());
  });
  requireElement<HTMLButtonElement>("#clear-wards").addEventListener("click", () => {
    setWardSelection(form, []);
    commit();
  });
  requireElement<HTMLButtonElement>("#back-to-overview").addEventListener("click", () => {
    applyViewState(state, controls, { filters: clearViewSelection(filtersNow()), term: state.term });
    commit({ announce: false });
    // The button is gone; the heading now names the overview.
    requireElement<HTMLElement>("#dashboard-view-heading").focus();
  });
  requireElement<HTMLButtonElement>("#date-window-toggle").addEventListener("click", () => {
    const showingFullArchive = classifyDateWindow(readFilters(form), state.broadWindow) === "full";
    setDateWindow(form, showingFullArchive ? (state.broadWindow?.startMonth ?? null) : null);
    commit();
  });
  requireElement<HTMLElement>("#topic-trends").addEventListener("click", (event) => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>("button[data-topic]");
    if (button?.dataset.topic) selectTopic(button.dataset.topic);
  });
  requireElement<HTMLDetailsElement>("#coverage-details").addEventListener("toggle", () => {
    renderCoveragePanel(state, filtersNow());
    refreshExportButtons();
  });

  const showTerm = (term: string) => {
    state.term = term;
    requestTermIndex(state, filtersNow);
    renderTermExplorer(state, filtersNow());
    refreshExportButtons();
    syncUrl(state, controls, "change");
  };
  // Start downloading the term index as soon as someone reaches for the explorer.
  termInput.addEventListener("focus", () => requestTermIndex(state, filtersNow));
  requireElement<HTMLFormElement>("#term-form").addEventListener("submit", (event) => {
    event.preventDefault();
    showTerm(termInput.value);
  });
  requireElement<HTMLElement>("#term-suggestions").addEventListener("click", (event) => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>("button[data-term]");
    if (!button?.dataset.term) return;
    termInput.value = button.dataset.term;
    showTerm(button.dataset.term);
  });

  document.querySelectorAll<HTMLButtonElement>("button[data-export-png]").forEach((button) => {
    button.addEventListener("click", () => {
      void exportPanel(state, button, readViewState(state, controls));
    });
  });

  window.addEventListener("popstate", () => {
    lastHistoryPushMs = null;
    restoreFromUrl({ announce: true });
  });

  let resizeTimer: ReturnType<typeof setTimeout> | undefined;
  let lastWidth = window.innerWidth;
  window.addEventListener("resize", () => {
    if (window.innerWidth === lastWidth) return;
    lastWidth = window.innerWidth;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => rerender(), RESIZE_DEBOUNCE_MS);
  });

  restoreFromUrl({ announce: false });
  // Drop any invalid or default parameters from the address the reader shares.
  syncUrl(state, controls, "replace");
}
