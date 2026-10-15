// Client-side wiring for /analytics: reads the filter form, recomputes every
// panel with the pure functions in lib/analytics.ts, and renders the charts.
// The page script loads the core data; the term index is fetched here on demand.
// The view (filters, ward profile, term) is mirrored in the URL so it can be
// shared, and restored on load and on back/forward.
import {
  buildCoverageGrid,
  describeDataAsOf,
  buildLensWardGrid,
  classifyDateWindow,
  computeLensWardReach,
  countActiveWardsByMonth,
  countBroadlyCoveredMonths,
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
  monthDateRange,
  monthOf,
  normalizeTermQuery,
  resolveIndexedTerm,
  searchScopeForFilters,
  suggestTerms,
  summarizeFacts,
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
  type MonthWardActivity,
  type NewsletterFact,
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
} from "../lib/analytics-methodology";
import {
  parseDashboardUrlState,
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
import { downloadChartPng } from "../lib/chart-export";
import { SITE_NAME } from "../lib/seo";

const TERM_WARD_LIMIT = 15;
const TERM_SUGGESTION_LIMIT = 8;
const GAP_LIMIT = 10;
const COVERAGE_STATUS_LABELS: Record<CoverageStatus, string> = {
  untracked: "Not tracked yet",
  silent: "Tracked, none received",
  received: "Received",
};
const RESIZE_DEBOUNCE_MS = 200;
/** Plot heights of the lens trend cards: small multiples, or one enlarged lens. */
const LENS_TREND_HEIGHT = 140;
const SELECTED_LENS_TREND_HEIGHT = 260;
const numberFormat = new Intl.NumberFormat("en-US");

interface DashboardState {
  data: AnalyticsDataset;
  wardBySource: Map<number, string | null>;
  lensById: Map<string, LensDefinition>;
  /** Every ward with a source, including wards with no newsletters archived. */
  allWards: string[];
  /** Every month from the first to the latest newsletter. */
  dataMonths: string[];
  wardActivity: MonthWardActivity[];
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

/** "3 wards", or "1–32 wards" when the count varied. */
function describeWardRange(fewest: number, most: number): string {
  return fewest === most ? pluralize(most, "ward") : `${numberFormat.format(fewest)}–${pluralize(most, "ward")}`;
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
  toggle.textContent = kind === "full" ? "Show broad-coverage window" : "Show full archive";
  if (!broadWindow) {
    status.textContent = `Showing ${span}.`;
  } else if (kind === "broad") {
    status.textContent = `Showing ${span}, the period of broad coverage: ${describeBroadCoverageRule(broadWindow)}.`;
  } else if (kind === "full") {
    status.textContent =
      `Showing the full archive, ${span}. Before ${formatMonth(broadWindow.startMonth)} only ` +
      `${describeWardRange(broadWindow.minActiveWardsBefore, broadWindow.maxActiveWardsBefore)} a month sent newsletters, ` +
      "so pooled numbers mix real change with wards being added.";
  } else {
    status.textContent = `Showing a custom window, ${span}. Broad coverage starts ${formatMonth(broadWindow.startMonth)}.`;
  }
}

// ---------------------------------------------------------------------------
// Panels

function renderSummary(
  state: DashboardState,
  filters: AnalyticsFilters,
  facts: NewsletterFact[],
  factsIgnoringLens: NewsletterFact[],
): void {
  const summary = summarizeFacts(facts);
  const wardCounts = summarizeWardCounts(
    wardsInScope(state.allWards, filters),
    factsIgnoringLens,
    state.data.newsletters,
  );
  const windowMonths = listWindowMonths(filters, state.dataMonths);
  const broadWindow = state.broadWindow;
  const wardNoun = filters.wards.length ? "selected wards" : "wards";
  const neverArchived = wardCounts.wardsNeverArchived;
  const tiles: [string, string][] = [
    [
      numberFormat.format(summary.newsletters),
      summary.firstDate ? `matching the filters (${summary.firstDate} to ${summary.lastDate})` : "matching the filters",
    ],
    [
      `${wardCounts.wardsWithNewsletters} of ${wardCounts.scopeWards}`,
      `${wardNoun} sent newsletters in this window.` +
        (neverArchived.length
          ? ` ${pluralize(neverArchived.length, "ward")} ${neverArchived.length === 1 ? "has" : "have"} none archived at all: ${neverArchived.join(", ")}.`
          : ""),
    ],
    [
      describeMonthSpan(windowMonths),
      broadWindow
        ? `${countBroadlyCoveredMonths(windowMonths, state.wardActivity, broadWindow.minActiveWards)} of ${pluralize(windowMonths.length, "month")} with broad coverage (${broadWindow.minActiveWards}+ wards sending)`
        : pluralize(windowMonths.length, "month"),
    ],
    [state.data.metadata.last_date ?? "–", "latest newsletter in the archive"],
  ];
  const values = document.querySelectorAll<HTMLElement>("#summary-tiles [data-tile-value]");
  const details = document.querySelectorAll<HTMLElement>("#summary-tiles [data-tile-detail]");
  tiles.forEach(([value, detail], index) => {
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
    `${archivedWards} of ${pluralize(wards.length, "ward")} ${wards.length === 1 ? "has" : "have"} newsletters in the archive` +
    (wardsNeverArchived.length
      ? `; ${wardsNeverArchived.length} ${wardsNeverArchived.length === 1 ? "has" : "have"} none.`
      : ".");
  if (!chart) return;
  const cells = buildCoverageGrid(state.data.newsletters, wards, months);
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
      : emptyMessage("No wards or months in the selected window."),
  );
  const wardTable = document.createElement("div");
  setTable(
    wardTable,
    [
      { label: "Ward", value: (row) => row.ward },
      { label: "Aldermen", value: (row) => row.aldermen.join(", ") },
      { label: "First newsletter", value: (row) => row.firstDate ?? "None archived" },
      { label: "Latest newsletter", value: (row) => row.lastDate ?? "" },
      { label: "Newsletters (whole archive)", value: (row) => row.newsletters, numeric: true },
    ],
    coverage,
  );
  // The grid's per-month cells, so its counts and states are not available by color alone.
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
  const timeline = requireElement<HTMLElement>("#term-timeline", section);
  const wardsChart = requireElement<HTMLElement>("#term-wards", section);
  const wardsTitle = requireElement<HTMLElement>("#term-wards-title", section);
  const suggestions = requireElement<HTMLElement>("#term-suggestions", section);
  const { metadata } = state.data;
  caption.textContent = `${numberFormat.format(metadata.term_count)} indexed terms (each appears in at least ${metadata.min_term_newsletters} newsletters).`;

  const clearResults = () => {
    timeline.replaceChildren();
    wardsChart.replaceChildren();
    wardsTitle.classList.add("hidden");
    replaceContent(table, emptyMessage("Search a term to see its table."));
  };

  const term = normalizeTermQuery(state.term);
  const index = state.terms;
  if (!index) {
    suggestions.replaceChildren();
    clearResults();
    message.textContent = !term
      ? "Type a term to explore."
      : state.termsError
        ? `Could not load the term index (${state.termsError}). Search again to retry.`
        : "Loading the term index…";
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
    message.textContent = "Type a term to explore.";
    clearResults();
    return;
  }
  const indexedTerm = resolveIndexedTerm(index, term);
  if (indexedTerm === null) {
    message.textContent =
      `"${term}" is not in the term index. It may be too rare (fewer than ${index.min_newsletters} newsletters), ` +
      "a common stopword, or a phrase longer than two words." +
      (suggestionTerms.length ? " Try one of the suggestions above." : "");
    clearResults();
    return;
  }

  const scopeFacts = filterFacts(state.data.newsletters, filters, { ignoreLens: true });
  const postings = index.terms[indexedTerm];
  const bucketCounts = expandTermPostings(index, postings, state.wardBySource, filters);
  const months = termMentionsByMonth(bucketCounts, scopeFacts);
  const wards = termMentionsByWard(bucketCounts, scopeFacts);
  const totalMentions = months.reduce((total, point) => total + point.mentions, 0);
  // A query can match another written form of the term ("bike lane" finds "bike lanes").
  message.textContent = `"${indexedTerm}" appears in ${pluralize(totalMentions, "newsletter")} out of ${numberFormat.format(scopeFacts.length)} in the selected wards and dates.`;

  if (totalMentions === 0) {
    clearResults();
    return;
  }
  const timelinePoints = trimSparseEdges(months);
  timeline.replaceChildren(
    timelinePoints.length
      ? renderTermTimeline(timelinePoints, chartWidth(timeline))
      : emptyMessage(
          `No month has ${MIN_MONTH_NEWSLETTERS_FOR_SHARES} or more newsletters in the selected wards and dates, so there is no monthly share to chart. See the table for counts.`,
        ),
  );
  wardsTitle.classList.remove("hidden");
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

/** City-wide views fade thin months; a ward selection is small by design, and its denominator is always shown. */
function reachFadeThreshold(filters: AnalyticsFilters): number {
  return filters.wards.length ? 0 : MIN_ACTIVE_WARDS_FOR_REACH;
}

function lensLabel(state: DashboardState, lensId: string): string {
  return state.lensById.get(lensId)?.label ?? lensId;
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

/** A note when the window ends in the archive's latest month and that month is not over in the data. */
function describePartialLastMonth(lastDate: string | null, months: string[]): string {
  const lastMonth = months.at(-1);
  if (!lastDate || !lastMonth || monthOf(lastDate) !== lastMonth) return "";
  return lastDate < monthDateRange(lastMonth).toDate
    ? `${formatMonth(lastMonth)} is partial: newsletters through ${lastDate}.`
    : "";
}

function renderCivicCalendarPanel(
  state: DashboardState,
  filters: AnalyticsFilters,
  scopeFacts: NewsletterFact[],
  months: string[],
): void {
  const { chart, caption, table } = panel("civic-calendar");
  const lenses = state.data.lenses.lenses;
  const cells = computeLensWardReach(scopeFacts, lenses.map((lens) => lens.id), months);
  const threshold = reachFadeThreshold(filters);
  caption.textContent = [
    "Numbers are wards (shown when at least a quarter of active wards mentioned the topic).",
    describePartialLastMonth(state.data.metadata.last_date, months),
  ]
    .filter(Boolean)
    .join(" ");
  if (!chart) return;
  replaceContent(
    chart,
    months.length && lenses.length
      ? renderCivicCalendar(cells, lenses, months, filters.lens, threshold, chartWidth(chart))
      : emptyMessage("No months in the selected window."),
  );
  setTable(table, reachColumns(state, threshold), cells);
}

function renderLensDefinitions(state: DashboardState): void {
  const container = requireElement<HTMLElement>("[data-lens-definitions]");
  const summary = state.data.lenses;
  const rules = document.createElement("p");
  rules.textContent =
    `${describeTopicMatching(summary)} ` +
    `Counts below are out of the ${numberFormat.format(summary.readable_newsletters)} newsletters analyzed across the whole archive. ` +
    "Topics marked Strong Towns Chicago focus are narrower slices of the broader topics.";
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

function renderLensTrendsPanel(
  state: DashboardState,
  filters: AnalyticsFilters,
  scopeFacts: NewsletterFact[],
  months: string[],
): void {
  const { chart, caption, table } = panel("lens-trends");
  if (!chart) return;
  const lenses = filters.lens
    ? state.data.lenses.lenses.filter((lens) => lens.id === filters.lens)
    : state.data.lenses.lenses;
  const cells = computeLensWardReach(scopeFacts, lenses.map((lens) => lens.id), months);
  const threshold = reachFadeThreshold(filters);
  // Thin months are left out of the lines (a gap), as the calendar fades them.
  const points = cells.map((cell) => (isReachFaded(cell, threshold) ? { ...cell, share: null } : cell));
  caption.textContent = threshold
    ? `Months with fewer than ${threshold} wards sending newsletters are left blank.`
    : "Shares are out of the selected wards that sent newsletters each month.";
  const maxShare = Math.max(0, ...points.map((point) => point.share ?? 0));
  const single = lenses.length === 1;
  chart.classList.toggle("md:grid-cols-2", !single);
  const cardWidth = single ? chartWidth(chart) : Math.max(chartWidth(chart) / 2 - 12, 300);
  replaceContent(
    chart,
    ...(points.some((point) => point.share !== null)
      ? lenses.map((lens) => {
          const figure = document.createElement("figure");
          const title = document.createElement("figcaption");
          title.className = "text-sm font-semibold text-gray-700";
          title.textContent = lens.label;
          figure.append(
            title,
            renderReachTrend(
              points.filter((point) => point.lens === lens.id),
              months,
              maxShare,
              single ? SELECTED_LENS_TREND_HEIGHT : LENS_TREND_HEIGHT,
              cardWidth,
            ),
          );
          return figure;
        })
      : [emptyMessage("No month in the selected window has enough wards sending newsletters.")]),
  );
  setTable(table, reachColumns(state, threshold), cells);
}

function renderLensWardsPanel(
  state: DashboardState,
  filters: AnalyticsFilters,
  scopeFacts: NewsletterFact[],
  months: string[],
): void {
  const { chart, caption, table } = panel("lens-wards");
  if (!chart) return;
  if (!filters.lens) {
    caption.textContent = "";
    replaceContent(chart, emptyMessage("Choose a topic in the filters above to see which wards mentioned it."));
    replaceContent(table, emptyMessage("Choose a topic to see its table."));
    return;
  }
  const label = lensLabel(state, filters.lens);
  const wards = listWards(state.data.newsletters).filter((ward) => !filters.wards.length || filters.wards.includes(ward));
  const cells = buildLensWardGrid(scopeFacts, filters.lens, wards, months);
  const wardsMentioning = new Set(cells.filter((cell) => cell.status === "mentioned").map((cell) => cell.ward));
  caption.textContent = `${label}: ${wardsMentioning.size} of ${pluralize(wards.length, "ward")} mentioned it at least once in the selected window. Wards with no newsletters archived are not listed (see the coverage grid).`;
  replaceContent(
    chart,
    wards.length && months.length
      ? renderLensWardGrid(cells, wards, months, label, chartWidth(chart))
      : emptyMessage("No wards or months in the selected window."),
  );
  setTable(
    table,
    [
      { label: "Ward", value: (cell) => cell.ward },
      { label: "Month", value: (cell) => cell.month },
      { label: "Status", value: (cell) => LENS_WARD_STATUS_LABELS[cell.status] },
      { label: "Newsletters mentioning", value: (cell) => cell.mentioning, numeric: true },
      { label: "Newsletters", value: (cell) => cell.newsletters, numeric: true },
    ],
    cells.filter((cell) => cell.status !== "no_newsletter"),
  );
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

function renderProfileTiles(profile: WardProfile, windowSpan: string): void {
  const { cadence, archiveCadence } = profile;
  setProfileTiles([
    [
      numberFormat.format(profile.windowNewsletters),
      `${windowSpan} · sent in ${cadence.monthsWithNewsletters} of ${pluralize(cadence.trackedMonths, "tracked month")}`,
    ],
    [
      numberFormat.format(profile.archiveNewsletters),
      profile.firstDate ? `${profile.firstDate} to ${profile.lastDate}` : "",
    ],
    [
      formatMedian(cadence.medianPerTrackedMonth),
      `median · all dates ${formatMedian(archiveCadence.medianPerTrackedMonth)} · all wards ${formatMedian(profile.cityMedianPerTrackedMonth)}`,
    ],
    [
      formatMedian(cadence.medianDaysBetween),
      `median · all dates ${formatMedian(archiveCadence.medianDaysBetween)}`,
    ],
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

/** The selected ward's profile over the window's months; the ward and topic filters do not apply. */
function renderWardProfilePanel(state: DashboardState, months: string[]): void {
  const { section, caption, table } = panel("ward-profile");
  const ward = requireElement<HTMLSelectElement>("#profile-ward", section).value;
  const message = requireElement<HTMLElement>("#profile-message", section);
  const content = requireElement<HTMLElement>("#profile-content", section);
  const showMessage = (text: string) => {
    message.textContent = text;
    message.hidden = false;
    content.hidden = true;
    caption.textContent = "";
    replaceContent(table, emptyMessage("Choose a ward."));
  };
  if (!ward) {
    showMessage("Choose a ward.");
    return;
  }
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
  const aldermen = profile.aldermen.join(", ");
  requireElement<HTMLElement>("#profile-heading", section).textContent = aldermen
    ? `${formatWard(ward)} · ${aldermen}`
    : formatWard(ward);
  caption.textContent = `${pluralize(profile.windowNewsletters, "newsletter")} in these dates, ${numberFormat.format(profile.archiveNewsletters)} in all.`;
  renderProfileTiles(profile, describeMonthSpan(months));

  const cadenceChart = requireElement<HTMLElement>("#profile-cadence", section);
  replaceContent(
    cadenceChart,
    months.length ? renderWardCadence(profile.months, months, chartWidth(cadenceChart)) : emptyMessage("No months in the selected window."),
  );
  const topicsChart = requireElement<HTMLElement>("#profile-topics", section);
  replaceContent(
    topicsChart,
    months.length
      ? renderWardTopicGrid(profile.topicCells, lenses, months, ward, chartWidth(topicsChart))
      : emptyMessage("No months in the selected window."),
  );

  const comparisonChart = requireElement<HTMLElement>("#profile-comparison", section);
  const comparisonNote = requireElement<HTMLElement>("#profile-comparison-note", section);
  if (profile.sharesShown) {
    comparisonNote.textContent = `Dark: share of ${formatWard(ward)}'s months mentioning the topic. Light: average share of active wards, same months.`;
    replaceContent(
      comparisonChart,
      renderWardTopicComparison(profile.topics, lenses, ward, chartWidth(comparisonChart)),
    );
  } else {
    comparisonNote.textContent = "";
    replaceContent(
      comparisonChart,
      emptyMessage(
        `Too few newsletters to compare (needs ${MIN_WARD_NEWSLETTERS_FOR_SHARES} across ${MIN_WARD_MONTHS_FOR_SHARES} months).`,
      ),
    );
  }

  const distinctiveChart = requireElement<HTMLElement>("#profile-distinctive", section);
  const terms = state.data.distinctiveByWard[ward] ?? [];
  replaceContent(
    distinctiveChart,
    terms.length
      ? renderDistinctiveTerms(terms, ward, profile.archiveNewsletters, chartWidth(distinctiveChart))
      : emptyMessage("Too few newsletters for distinctive terms."),
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
    tableHeading("Distinctive vocabulary (all dates)"),
    termTable,
  );
}

function renderRisingPanel(state: DashboardState): void {
  const { chart, caption, table } = panel("rising-terms");
  const rising = state.data.rising;
  if (!rising.latest_month) {
    caption.textContent = "No complete month of data yet.";
    replaceContent(chart, emptyMessage("No rising terms."));
    replaceContent(table, emptyMessage("No rows."));
    return;
  }
  const baselineSpan = `${formatMonth(rising.baseline_months[0])} – ${formatMonth(rising.baseline_months[rising.baseline_months.length - 1])}`;
  const latest = formatMonth(rising.latest_month);
  caption.textContent =
    `${latest}: ${pluralize(rising.latest_active_wards, "ward")} sent newsletters ` +
    `(${rising.baseline_active_wards.join(", ")} in ${baselineSpan}). Terms that are part of a higher-ranked term's phrase (such as "labor" or "day weekend" after "labor day") are left out.`;
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
  setTable(
    table,
    [
      { label: "Term", value: (item) => item.term },
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
  caption.textContent = `Based on ${pluralize(facts.length, "newsletter")}.`;
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
  if ((panelId === "lens-wards" || panelId === "lens-trends") && lens) return `${title}: ${lens}`;
  if (panelId === "term-explorer" && view.term) return `${title}: "${view.term}"`;
  if (panelId === "ward-profile" && view.profileWard) return `${title}: ${formatWard(view.profileWard)}`;
  return title;
}

function exportRegion(section: HTMLElement): HTMLElement | null {
  return section.querySelector<HTMLElement>("[data-export-region]") ?? section.querySelector<HTMLElement>("[data-chart]");
}

/** Enable each export button only while its panel shows a chart. */
function refreshExportButtons(): void {
  document.querySelectorAll<HTMLButtonElement>("button[data-export-png]").forEach((button) => {
    const section = button.closest<HTMLElement>("section");
    button.disabled = !section || !exportRegion(section)?.querySelector("svg");
  });
}

async function exportPanel(state: DashboardState, button: HTMLButtonElement, view: DashboardViewState): Promise<void> {
  const section = button.closest<HTMLElement>("section");
  const region = section ? exportRegion(section) : null;
  if (!section || !region) return;
  const panelId = button.dataset.exportPng ?? section.id;
  const title = requireElement<HTMLElement>("h2", section).textContent?.trim() ?? "";
  button.disabled = true;
  try {
    await downloadChartPng(region, {
      title: describeExportTitle(state, panelId, title, view),
      scope: describeExportScope(state, panelId, view),
      caption: requireElement<HTMLElement>("[data-caption]", section).textContent?.trim() ?? "",
      dataAsOf: describeDataAsOf(state.data.metadata),
      siteName: SITE_NAME,
      pageUrl: window.location.href,
    });
  } finally {
    button.disabled = false;
  }
}

// ---------------------------------------------------------------------------
// Orchestration

function renderDashboard(state: DashboardState, form: HTMLFormElement): void {
  const filters = readFilters(form);
  updateWardSummary(filters);
  const facts = filterFacts(state.data.newsletters, filters);
  const factsIgnoringLens = filterFacts(state.data.newsletters, filters, { ignoreLens: true });
  const months = listWindowMonths(filters, state.dataMonths);

  renderDateWindowStatus(state, filters);
  renderSummary(state, filters, facts, factsIgnoringLens);
  renderCoveragePanel(state, filters);
  renderCivicCalendarPanel(state, filters, factsIgnoringLens, months);
  renderLensTrendsPanel(state, filters, factsIgnoringLens, months);
  renderLensWardsPanel(state, filters, factsIgnoringLens, months);
  renderTermExplorer(state, filters);
  renderWardProfilePanel(state, months);
  renderRisingPanel(state);
  renderCadencePanel(factsIgnoringLens);
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
    wardActivity: countActiveWardsByMonth(data.newsletters),
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

/** Record the current view in the URL: a new history entry for a change, or a replacement. */
function syncUrl(state: DashboardState, controls: DashboardControls, mode: "push" | "replace"): void {
  const url = dashboardUrl(serializeDashboardUrlState(readViewState(state, controls), state.urlContext));
  if (mode === "replace") {
    window.history.replaceState(null, "", url);
  } else if (url !== `${window.location.pathname}${window.location.search}${window.location.hash}`) {
    window.history.pushState(null, "", url);
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
  const rerender = () => renderDashboard(state, form);
  /** Render a change the reader made and record it as a new history entry. */
  const commit = () => {
    rerender();
    syncUrl(state, controls, "push");
  };
  const restoreFromUrl = () => {
    applyViewState(state, controls, parseDashboardUrlState(new URLSearchParams(window.location.search), state.urlContext));
    if (state.term) requestTermIndex(state, filtersNow);
    rerender();
  };

  form.addEventListener("change", (event) => {
    const target = event.target as HTMLInputElement;
    // Follow a single selected ward in the ward profile.
    if (target.name === "ward") {
      const selected = readFilters(form).wards;
      if (selected.length === 1) profileSelect.value = selected[0];
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
  profileSelect.addEventListener("change", () => {
    renderWardProfilePanel(state, listWindowMonths(filtersNow(), state.dataMonths));
    refreshExportButtons();
    syncUrl(state, controls, "push");
  });

  const showTerm = (term: string) => {
    state.term = term;
    requestTermIndex(state, filtersNow);
    renderTermExplorer(state, filtersNow());
    refreshExportButtons();
    syncUrl(state, controls, "push");
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
      exportPanel(state, button, readViewState(state, controls)).catch((error: unknown) => {
        console.error("Chart export failed", error);
      });
    });
  });

  window.addEventListener("popstate", restoreFromUrl);

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
