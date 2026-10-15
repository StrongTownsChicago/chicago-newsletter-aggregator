// Client-side wiring for /analytics: reads the filter form, recomputes every
// panel with the pure functions in lib/analytics.ts, and renders the charts.
// The page script loads the core data; the term index is fetched here on demand.
import {
  BROAD_COVERAGE_PEAK_FRACTION,
  buildCoverageGrid,
  classifyDateWindow,
  computeTopicTrends,
  countActiveWardsByMonth,
  countBroadlyCoveredMonths,
  EMPTY_FILTERS,
  expandTermPostings,
  filterFacts,
  findBroadCoverageWindow,
  findLongestGaps,
  formatMonth,
  listMonthsWithShares,
  listSourceWards,
  listWards,
  listWindowMonths,
  MIN_MONTH_NEWSLETTERS_FOR_SHARES,
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
  type MonthWardActivity,
  type NewsletterFact,
  type TermIndex,
} from "../lib/analytics";
import {
  formatOptionalShare,
  formatPercent,
  formatWard,
  renderCoverageGrid,
  renderDistinctiveTerms,
  renderRisingTerms,
  renderTable,
  renderTermTimeline,
  renderTermWards,
  renderTopicTrend,
  sourceLabel,
  type TableColumn,
} from "../lib/analytics-charts";
import { createLazyLoader, fetchTermIndex } from "../lib/analytics-data";
import { humanizeIdentifier } from "../lib/format";
import { ALL_TOPICS } from "../lib/topics";

const TERM_WARD_LIMIT = 15;
const TERM_SUGGESTION_LIMIT = 8;
const GAP_LIMIT = 10;
const COVERAGE_STATUS_LABELS: Record<CoverageStatus, string> = {
  untracked: "Not tracked yet",
  silent: "Tracked, none received",
  received: "Received",
};
const RESIZE_DEBOUNCE_MS = 200;
const numberFormat = new Intl.NumberFormat("en-US");
const percentFormat = new Intl.NumberFormat("en-US", { style: "percent" });

interface DashboardState {
  data: AnalyticsDataset;
  wardBySource: Map<number, string | null>;
  /** Every ward with a source, including wards with no newsletters archived. */
  allWards: string[];
  /** Every month from the first to the latest newsletter. */
  dataMonths: string[];
  wardActivity: MonthWardActivity[];
  broadWindow: BroadCoverageWindow | null;
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

function pluralize(count: number, noun: string): string {
  return `${numberFormat.format(count)} ${noun}${count === 1 ? "" : "s"}`;
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
    topic: (formData.get("topic") as string) || null,
    fromMonth: (formData.get("from") as string) || null,
    toMonth: (formData.get("to") as string) || null,
  };
}

function populateFilterOptions(
  form: HTMLFormElement,
  wards: string[],
  months: string[],
  defaultFromMonth: string | null,
): void {
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

function describeBroadCoverageRule(broadWindow: BroadCoverageWindow): string {
  return (
    `months when at least ${broadWindow.minActiveWards} wards sent newsletters ` +
    `(${percentFormat.format(BROAD_COVERAGE_PEAK_FRACTION)} of the ${broadWindow.peakActiveWards} in the busiest month)`
  );
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
  factsIgnoringTopic: NewsletterFact[],
): void {
  const summary = summarizeFacts(facts);
  const wardCounts = summarizeWardCounts(
    wardsInScope(state.allWards, filters),
    factsIgnoringTopic,
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
          // Coverage ignores the topic filter, so its search links do too.
          searchScopeForFilters(filters, { includeTopic: false }),
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

  const scopeFacts = filterFacts(state.data.newsletters, { ...filters, topic: null });
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
      // The term index has no topic, so neither do its search links.
      searchScopeForFilters(filters, { includeTopic: false }),
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

function renderTopicTrendsPanel(facts: NewsletterFact[], filters: AnalyticsFilters): void {
  const { chart, caption, table } = panel("topic-trends");
  if (!chart) return;
  const topics = filters.topic ? [filters.topic] : ALL_TOPICS;
  const points = computeTopicTrends(facts, topics);
  const processed = facts.filter((fact) => fact.topics !== null).length;
  caption.textContent = `Based on ${pluralize(processed, "LLM-processed newsletter")}.`;
  if (points.length === 0) {
    replaceContent(chart, emptyMessage("No processed newsletters for these filters."));
    replaceContent(table, emptyMessage("No rows."));
    return;
  }
  const maxShare = Math.max(...points.map((point) => point.share ?? 0));
  const months = listMonthsWithShares(points);
  const monthsShown = new Set(months);
  chart.classList.toggle("md:grid-cols-2", !filters.topic);
  const cardWidth = filters.topic ? chartWidth(chart) : Math.max(chartWidth(chart) / 2 - 12, 300);
  replaceContent(
    chart,
    ...(months.length
      ? topics.map((topic) => {
          const figure = document.createElement("figure");
          const title = document.createElement("figcaption");
          title.className = "text-sm font-semibold text-gray-700";
          title.textContent = humanizeIdentifier(topic);
          const topicPoints = points.filter((point) => point.topic === topic && monthsShown.has(point.month));
          figure.append(title, renderTopicTrend(topicPoints, months, maxShare, cardWidth));
          return figure;
        })
      : [emptyMessage(`No month has ${MIN_MONTH_NEWSLETTERS_FOR_SHARES} or more processed newsletters for these filters.`)]),
  );
  setTable(
    table,
    [
      { label: "Month", value: (point) => point.month },
      { label: "Topic", value: (point) => humanizeIdentifier(point.topic) },
      { label: "Newsletters", value: (point) => `${point.newsletters} / ${point.monthNewsletters}`, numeric: true },
      { label: "Share", value: (point) => formatOptionalShare(point.share), numeric: true },
    ],
    points.filter((point) => point.newsletters > 0),
  );
}

function renderDistinctivePanel(state: DashboardState): void {
  const { chart, caption, table } = panel("distinctive-terms");
  const ward = requireElement<HTMLSelectElement>("#distinctive-ward").value;
  const terms = state.data.distinctiveByWard[ward] ?? [];
  const wardNewsletters = state.data.newsletters.filter((fact) => fact.ward === ward).length;
  caption.textContent = `${formatWard(ward)}: ${pluralize(wardNewsletters, "newsletter")} compared with the rest of the city.`;
  if (!chart) return;
  replaceContent(
    chart,
    terms.length
      ? renderDistinctiveTerms(terms, ward, chartWidth(chart))
      : emptyMessage("Not enough newsletters from this ward to find distinctive terms."),
  );
  setTable(
    table,
    [
      { label: "Term", value: (item) => item.term },
      { label: "Score", value: (item) => item.score, numeric: true },
      { label: "Times more likely", value: (item) => item.lift, numeric: true },
      { label: "Ward newsletters", value: (item) => item.ward_newsletters, numeric: true },
      { label: "Ward share", value: (item) => formatPercent(item.ward_share), numeric: true },
      { label: "Rest of city share", value: (item) => formatPercent(item.rest_share), numeric: true },
    ],
    terms,
  );
}

function renderRisingPanel(state: DashboardState): void {
  const { chart, caption, table } = panel("rising-terms");
  const rising = state.data.rising;
  caption.textContent = rising.latest_month
    ? `${rising.latest_month} (${pluralize(rising.latest_newsletters, "newsletter")}) vs ${rising.baseline_months[0]} – ${rising.baseline_months.at(-1)} (${pluralize(rising.baseline_newsletters, "newsletter")}).`
    : "No complete month of data yet.";
  if (!chart) return;
  replaceContent(
    chart,
    rising.terms.length
      ? renderRisingTerms(rising.terms, `Baseline (${rising.baseline_months[0]} – ${rising.baseline_months.at(-1)})`, `Latest (${rising.latest_month})`, chartWidth(chart))
      : emptyMessage("No rising terms."),
  );
  setTable(
    table,
    [
      { label: "Term", value: (item) => item.term },
      { label: "Latest newsletters", value: (item) => item.latest_newsletters, numeric: true },
      { label: "Sources", value: (item) => item.latest_sources, numeric: true },
      { label: "Latest share", value: (item) => formatPercent(item.latest_share), numeric: true },
      { label: "Baseline share", value: (item) => formatPercent(item.baseline_share), numeric: true },
      { label: "Rise", value: (item) => (item.baseline_newsletters === 0 ? "new" : `${item.ratio}×`), numeric: true },
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
// Orchestration

function renderDashboard(state: DashboardState, form: HTMLFormElement): void {
  const filters = readFilters(form);
  updateWardSummary(filters);
  const facts = filterFacts(state.data.newsletters, filters);
  const factsIgnoringTopic = filterFacts(state.data.newsletters, filters, { ignoreTopic: true });

  renderDateWindowStatus(state, filters);
  renderSummary(state, filters, facts, factsIgnoringTopic);
  renderCoveragePanel(state, filters);
  renderTermExplorer(state, filters);
  renderTopicTrendsPanel(factsIgnoringTopic, filters);
  renderDistinctivePanel(state);
  renderRisingPanel(state);
  renderCadencePanel(factsIgnoringTopic);
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
    .finally(() => renderTermExplorer(state, readCurrentFilters()));
}

function buildDashboardState(data: AnalyticsDataset): DashboardState {
  const factMonths = data.newsletters.map((fact) => monthOf(fact.date)).sort();
  return {
    data,
    wardBySource: new Map(data.sources.map((source) => [source.id, source.ward])),
    allWards: listSourceWards(data.sources),
    dataMonths: listWindowMonths(EMPTY_FILTERS, factMonths),
    wardActivity: countActiveWardsByMonth(data.newsletters),
    broadWindow: findBroadCoverageWindow(data.newsletters),
    term: "",
    terms: null,
    termsError: null,
  };
}

export function startAnalyticsDashboard(data: AnalyticsDataset): void {
  const state = buildDashboardState(data);
  const form = requireElement<HTMLFormElement>("#analytics-filters");
  populateFilterOptions(form, listWards(data.newsletters), state.dataMonths, state.broadWindow?.startMonth ?? null);

  const distinctiveSelect = requireElement<HTMLSelectElement>("#distinctive-ward");
  const distinctiveWards = Object.keys(data.distinctiveByWard);
  distinctiveSelect.append(...distinctiveWards.map((ward) => new Option(formatWard(ward), ward)));

  const rerender = () => renderDashboard(state, form);

  form.addEventListener("change", (event) => {
    const target = event.target as HTMLInputElement;
    // Follow a single selected ward in the distinctive-vocabulary panel.
    if (target.name === "ward") {
      const selected = readFilters(form).wards;
      if (selected.length === 1 && distinctiveWards.includes(selected[0])) {
        distinctiveSelect.value = selected[0];
      }
    }
    rerender();
  });
  form.addEventListener("reset", () => {
    requireElement<HTMLDetailsElement>("#ward-picker").open = false;
    // Form reset updates control values after the event; render on the next tick.
    setTimeout(rerender);
  });
  requireElement<HTMLButtonElement>("#clear-wards").addEventListener("click", () => {
    form.querySelectorAll<HTMLInputElement>('input[name="ward"]').forEach((input) => {
      input.checked = false;
    });
    rerender();
  });
  requireElement<HTMLButtonElement>("#date-window-toggle").addEventListener("click", () => {
    const showingFullArchive = classifyDateWindow(readFilters(form), state.broadWindow) === "full";
    setDateWindow(form, showingFullArchive ? (state.broadWindow?.startMonth ?? null) : null);
    rerender();
  });
  distinctiveSelect.addEventListener("change", () => renderDistinctivePanel(state));

  const termInput = requireElement<HTMLInputElement>("#term-input");
  const filtersNow = () => readFilters(form);
  // Start downloading the term index as soon as someone reaches for the explorer.
  termInput.addEventListener("focus", () => requestTermIndex(state, filtersNow));
  requireElement<HTMLFormElement>("#term-form").addEventListener("submit", (event) => {
    event.preventDefault();
    state.term = termInput.value;
    requestTermIndex(state, filtersNow);
    renderTermExplorer(state, filtersNow());
  });
  requireElement<HTMLElement>("#term-suggestions").addEventListener("click", (event) => {
    const button = (event.target as HTMLElement).closest<HTMLButtonElement>("button[data-term]");
    if (!button?.dataset.term) return;
    termInput.value = button.dataset.term;
    state.term = button.dataset.term;
    renderTermExplorer(state, filtersNow());
  });

  let resizeTimer: ReturnType<typeof setTimeout> | undefined;
  let lastWidth = window.innerWidth;
  window.addEventListener("resize", () => {
    if (window.innerWidth === lastWidth) return;
    lastWidth = window.innerWidth;
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(rerender, RESIZE_DEBOUNCE_MS);
  });

  rerender();
}
