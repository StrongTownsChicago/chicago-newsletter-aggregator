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
  findLongestGaps,
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
import { downloadChartPng, EXPORT_TEXT_ATTRIBUTE } from "../lib/chart-export";
import { SITE_NAME } from "../lib/seo";

const TERM_WARD_LIMIT = 15;
const TERM_SUGGESTION_LIMIT = 8;
const GAP_LIMIT = 10;
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

/** "28 of 37": wards mentioning a topic in the last full month, of wards sending. */
function formatLatestReach(trend: TopicTrend): string {
  return trend.latest ? `${trend.latest.wardsMentioning} of ${trend.latest.activeWards}` : "–";
}

/** "28 of 37 wards". */
function describeTopicReach(trend: TopicTrend): string {
  return trend.latest ? `${formatLatestReach(trend)} wards` : "";
}

function renderSummary(
  state: DashboardState,
  filters: AnalyticsFilters,
  facts: NewsletterFact[],
  factsIgnoringLens: NewsletterFact[],
  overview: TopicOverview,
): void {
  const wardCounts = summarizeWardCounts(
    wardsInScope(state.allWards, filters),
    factsIgnoringLens,
    state.data.newsletters,
  );
  const span = describeMonthSpan(listWindowMonths(filters, state.dataMonths));
  const latestMonth = overview.fullMonths.at(-1);
  const inLatestMonth = latestMonth ? `, ${formatMonth(latestMonth)}` : "";
  const widest = findWidestReachTopic(overview.trends);
  const largestChange = findLargestChangeTopic(overview.trends);
  const neverArchived = wardCounts.wardsNeverArchived;
  const tiles: [string, string, string][] = [
    [
      "Newsletters",
      numberFormat.format(facts.length),
      filters.lens ? `${span} · mentioning ${lensLabel(state, filters.lens)}` : span,
    ],
    [
      "Wards sending",
      `${wardCounts.wardsWithNewsletters} of ${wardCounts.scopeWards}`,
      neverArchived.length ? `None archived: ${neverArchived.join(", ")}` : "",
    ],
    [
      `Most mentioned topic${inLatestMonth}`,
      widest ? lensLabel(state, widest.lens) : "–",
      widest ? describeTopicReach(widest) : "",
    ],
    [
      `Biggest change${inLatestMonth}`,
      largestChange ? lensLabel(state, largestChange.lens) : "–",
      largestChange?.latestChange != null
        ? `${describeTopicReach(largestChange)}, ${formatPointChange(largestChange.latestChange)} vs average`
        : "",
    ],
  ];
  const labels = document.querySelectorAll<HTMLElement>("#summary-tiles [data-tile-label]");
  const values = document.querySelectorAll<HTMLElement>("#summary-tiles [data-tile-value]");
  const details = document.querySelectorAll<HTMLElement>("#summary-tiles [data-tile-detail]");
  tiles.forEach(([label, value, detail], index) => {
    labels[index].textContent = label;
    values[index].textContent = value;
    details[index].textContent = detail;
  });
}

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

function textCell(tag: "td" | "th", text: string, className: string): HTMLTableCellElement {
  const cell = document.createElement(tag);
  cell.className = className;
  cell.setAttribute(EXPORT_TEXT_ATTRIBUTE, "");
  cell.textContent = text;
  return cell;
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
    textCell("th", "Topic", headClass),
    textCell("th", "Trend", headClass),
    textCell("th", latestMonth ? formatMonth(latestMonth) : "Latest", `${headClass} text-right`),
    textCell("th", "vs average", `${headClass} text-right`),
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
    button.className = "text-left text-blue-700 hover:underline whitespace-nowrap";
    button.textContent = label;
    topicCell.append(button);
    const sparkCell = row.insertCell();
    sparkCell.className = "pr-4 py-0.5";
    const shares = trend.points.flatMap((point) => (point.share === null ? [] : [point.share]));
    sparkCell.append(renderSparkline(trend.points, tightShareDomain(shares), describeSparkline(label, trend.points)));
    row.append(
      textCell("td", formatLatestReach(trend), "pr-4 text-right tabular-nums whitespace-nowrap"),
      textCell(
        "td",
        trend.latestChange === null ? "–" : formatPointChange(trend.latestChange),
        "text-right tabular-nums whitespace-nowrap",
      ),
    );
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

/** The chosen topic's ward-reach trend and its ward × month grid; hidden without a topic. */
function renderTopicDetailPanel(
  state: DashboardState,
  filters: AnalyticsFilters,
  overview: TopicOverview,
  scopeFacts: NewsletterFact[],
  months: string[],
): void {
  const { section, caption, table } = panel("topic-detail");
  const lens = filters.lens;
  section.hidden = !lens;
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

function setProfileTiles(tiles: [string, string][]): void {
  const values = document.querySelectorAll<HTMLElement>("#profile-tiles [data-tile-value]");
  const details = document.querySelectorAll<HTMLElement>("#profile-tiles [data-tile-detail]");
  tiles.forEach(([value, detail], index) => {
    values[index].textContent = value;
    details[index].textContent = detail;
  });
}

function renderProfileTiles(profile: WardProfile): void {
  const { cadence, archiveCadence } = profile;
  setProfileTiles([
    [
      numberFormat.format(profile.windowNewsletters),
      `Sent in ${cadence.monthsWithNewsletters} of ${pluralize(cadence.trackedMonths, "tracked month")}`,
    ],
    [
      numberFormat.format(profile.archiveNewsletters),
      profile.firstDate ? `${profile.firstDate} to ${profile.lastDate}` : "",
    ],
    [
      formatMedian(cadence.medianPerTrackedMonth),
      `All dates ${formatMedian(archiveCadence.medianPerTrackedMonth)} · all wards ${formatMedian(profile.cityMedianPerTrackedMonth)}`,
    ],
    [formatMedian(cadence.medianDaysBetween), `All dates ${formatMedian(archiveCadence.medianDaysBetween)}`],
  ]);
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

/** The chosen ward over the window's months, hidden without one; the ward and topic filters don't apply. */
function renderWardProfilePanel(state: DashboardState, ward: string, months: string[]): void {
  const { section, caption, table } = panel("ward-profile");
  const message = requireElement<HTMLElement>("#profile-message", section);
  const content = requireElement<HTMLElement>("#profile-content", section);
  const tableView = requireElement<HTMLElement>("[data-table-view]", section);
  section.hidden = !ward;
  if (!ward) return;
  const showMessage = (text: string) => {
    message.textContent = text;
    message.hidden = false;
    content.hidden = true;
    tableView.hidden = true;
    caption.textContent = "";
  };
  const lenses = state.data.lenses.lenses;
  const profile = buildWardProfile(
    state.data.newsletters,
    state.data.sources,
    ward,
    months,
    state.dataMonths,
    lenses.map((lens) => lens.id),
  );
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
  renderProfileTiles(profile);

  const cadenceChart = requireElement<HTMLElement>("#profile-cadence", section);
  replaceContent(
    cadenceChart,
    months.length ? renderWardCadence(profile.months, months, chartWidth(cadenceChart)) : emptyMessage("Nothing in these dates."),
  );
  const topicsChart = requireElement<HTMLElement>("#profile-topics", section);
  replaceContent(
    topicsChart,
    months.length
      ? renderWardTopicGrid(profile.topicCells, lenses, months, ward, chartWidth(topicsChart))
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
  const wards =
    panelId === "ward-profile" && view.profileWard ? formatWard(view.profileWard) : describeWardScope(view.filters);
  return `${span} · ${wards}`;
}

function describeExportTitle(state: DashboardState, panelId: string, title: string, view: DashboardViewState): string {
  const lens = view.filters.lens ? lensLabel(state, view.filters.lens) : null;
  if (panelId === "topic-detail" && lens) return `${title}: ${lens}`;
  if (panelId === "term-explorer" && view.term) return `${title}: "${view.term}"`;
  if (panelId === "ward-profile" && view.profileWard) return `${title}: ${formatWard(view.profileWard)}`;
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

function renderDashboard(
  state: DashboardState,
  controls: DashboardControls,
  selectTopic: (lensId: string) => void,
): void {
  const filters = readFilters(controls.form);
  updateWardSummary(filters);
  const facts = filterFacts(state.data.newsletters, filters);
  const factsIgnoringLens = filterFacts(state.data.newsletters, filters, { ignoreLens: true });
  const months = listWindowMonths(filters, state.dataMonths);
  const overview = buildTopicOverview(state, filters, factsIgnoringLens, months);

  renderDateWindowStatus(state, filters);
  renderSummary(state, filters, facts, factsIgnoringLens, overview);
  renderTermExplorer(state, filters);
  renderCivicCalendarPanel(state, filters, overview, months, selectTopic);
  renderTopicDetailPanel(state, filters, overview, factsIgnoringLens, months);
  renderWardProfilePanel(state, controls.profileSelect.value, months);
  renderRisingPanel(state);
  renderCadencePanel(factsIgnoringLens);
  renderCoveragePanel(state, filters);
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
      filterWards: listWards(data.newsletters),
      profileWards: allWards,
      months: dataMonths,
      lensIds: data.lenses.lenses.map((lens) => lens.id),
      defaultFromMonth: broadWindow?.startMonth ?? null,
    },
    term: "",
    terms: null,
    termsError: null,
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
    profileWard: controls.profileSelect.value || null,
    term: normalizeTermQuery(state.term),
  };
}

/** Set every control to a view (from the URL) without rendering. */
function applyViewState(state: DashboardState, controls: DashboardControls, view: DashboardViewState): void {
  const { form, profileSelect, termInput } = controls;
  form.querySelectorAll<HTMLInputElement>('input[name="ward"]').forEach((input) => {
    input.checked = view.filters.wards.includes(input.value);
  });
  requireElement<HTMLSelectElement>('select[name="lens"]', form).value = view.filters.lens ?? "";
  requireElement<HTMLSelectElement>('select[name="from"]', form).value = view.filters.fromMonth ?? "";
  requireElement<HTMLSelectElement>('select[name="to"]', form).value = view.filters.toMonth ?? "";
  profileSelect.value = view.profileWard ?? "";
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
    state.urlContext.filterWards,
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
    commit();
    requireElement<HTMLElement>("#topic-detail").scrollIntoView({ behavior: "smooth", block: "start" });
    // The clicked control was redrawn; move focus to where the reader now is.
    requireElement<HTMLElement>("#topic-detail-heading").focus({ preventScroll: true });
  };
  const rerender = () => renderDashboard(state, controls, selectTopic);
  /** Render a change the reader made and record it in the history. */
  const commit = () => {
    rerender();
    syncUrl(state, controls, "change");
  };
  const restoreFromUrl = () => {
    applyViewState(state, controls, parseDashboardUrlState(new URLSearchParams(window.location.search), state.urlContext));
    if (state.term) requestTermIndex(state, filtersNow);
    rerender();
  };

  // Covers the ward profile select too, which sits in the filter form.
  form.addEventListener("change", (event) => {
    const target = event.target as HTMLInputElement;
    // Follow a single selected ward in the ward profile.
    if (target.name === "ward") {
      const selected = readFilters(form).wards;
      if (selected.length === 1) profileSelect.value = selected[0];
    }
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
    setTimeout(commit);
  });
  requireElement<HTMLButtonElement>("#clear-wards").addEventListener("click", () => {
    form.querySelectorAll<HTMLInputElement>('input[name="ward"]').forEach((input) => {
      input.checked = false;
    });
    commit();
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
    restoreFromUrl();
  });

  let resizeTimer: ReturnType<typeof setTimeout> | undefined;
  let lastWidth = window.innerWidth;
  window.addEventListener("resize", () => {
    if (window.innerWidth === lastWidth) return;
    lastWidth = window.innerWidth;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(rerender, RESIZE_DEBOUNCE_MS);
  });

  restoreFromUrl();
  // Drop any invalid or default parameters from the address the reader shares.
  syncUrl(state, controls, "replace");
}
