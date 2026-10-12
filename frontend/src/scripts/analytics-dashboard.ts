// Client-side wiring for /analytics: reads the filter form, recomputes every
// panel with the pure functions in lib/analytics.ts, and renders the charts.
import {
  computeRelevanceByWard,
  computeTopicTrends,
  computeWardTopicCells,
  countNewslettersByWardMonth,
  expandTermPostings,
  filterFacts,
  findLongestGaps,
  listMonths,
  listWards,
  MIN_WARD_NEWSLETTERS_FOR_SHARES,
  lookupTermPostings,
  monthOf,
  normalizeTermQuery,
  selectCoverage,
  suggestTerms,
  summarizeFacts,
  termMentionsByMonth,
  termMentionsByWard,
  trimSparseEdges,
  type AnalyticsDataset,
  type AnalyticsFilters,
  type NewsletterFact,
} from "../lib/analytics";
import {
  formatOptionalShare,
  formatPercent,
  formatWard,
  renderCadenceHeatmap,
  renderCoverage,
  renderDistinctiveTerms,
  renderRelevanceByWard,
  renderRisingTerms,
  renderTable,
  renderTermTimeline,
  renderTermWards,
  renderTopicTrend,
  renderWardTopicHeatmap,
  sourceLabel,
  type TableColumn,
} from "../lib/analytics-charts";
import { loadAnalyticsDataset } from "../lib/analytics-data";
import { humanizeIdentifier } from "../lib/format";
import { ALL_TOPICS } from "../lib/topics";

const TERM_WARD_LIMIT = 15;
const TERM_SUGGESTION_LIMIT = 8;
const GAP_LIMIT = 10;
const RESIZE_DEBOUNCE_MS = 200;
const numberFormat = new Intl.NumberFormat("en-US");

interface DashboardState {
  data: AnalyticsDataset;
  wardBySource: Map<number, string | null>;
  term: string;
}

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

function pluralize(count: number, noun: string): string {
  return `${numberFormat.format(count)} ${noun}${count === 1 ? "" : "s"}`;
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
    minRelevance: Number(formData.get("relevance") ?? 0),
  };
}

function populateFilterOptions(form: HTMLFormElement, wards: string[], months: string[]): void {
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
    select.append(...months.map((month) => new Option(month, month)));
  }
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

// ---------------------------------------------------------------------------
// Panels

function renderSummary(facts: NewsletterFact[]): void {
  const summary = summarizeFacts(facts);
  const values = document.querySelectorAll<HTMLElement>("#summary-tiles [data-tile-value]");
  const details = document.querySelectorAll<HTMLElement>("#summary-tiles [data-tile-detail]");
  const tiles: [string, string][] = [
    [numberFormat.format(summary.newsletters), "matching the filters"],
    [numberFormat.format(summary.activeSources), "sources with newsletters"],
    [
      summary.firstDate ? `${summary.firstDate.slice(0, 7)} – ${summary.lastDate?.slice(0, 7)}` : "–",
      summary.firstDate ? `${summary.firstDate} to ${summary.lastDate}` : "",
    ],
    [
      summary.averageRelevance === null ? "–" : summary.averageRelevance.toFixed(1),
      `out of 10, from ${pluralize(summary.scoredNewsletters, "scored newsletter")}`,
    ],
  ];
  tiles.forEach(([value, detail], index) => {
    values[index].textContent = value;
    details[index].textContent = detail;
  });
}

function renderTermExplorer(state: DashboardState, filters: AnalyticsFilters): void {
  const { section, caption, table } = panel("term-explorer");
  const message = requireElement<HTMLElement>("#term-message", section);
  const timeline = requireElement<HTMLElement>("#term-timeline", section);
  const wardsChart = requireElement<HTMLElement>("#term-wards", section);
  const wardsTitle = requireElement<HTMLElement>("#term-wards-title", section);
  const suggestions = requireElement<HTMLElement>("#term-suggestions", section);
  const index = state.data.terms;
  caption.textContent = `${numberFormat.format(Object.keys(index.terms).length)} indexed terms (each appears in at least ${index.min_newsletters} newsletters).`;

  const clearResults = () => {
    timeline.replaceChildren();
    wardsChart.replaceChildren();
    wardsTitle.classList.add("hidden");
    replaceContent(table, emptyMessage("Search a term to see its table."));
  };

  const term = normalizeTermQuery(state.term);
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
  const postings = lookupTermPostings(index, term);
  if (!postings) {
    message.textContent =
      `"${term}" is not in the term index. It may be too rare (fewer than ${index.min_newsletters} newsletters), ` +
      "a common stopword, or a phrase longer than two words." +
      (suggestionTerms.length ? " Try one of the suggestions above." : "");
    clearResults();
    return;
  }

  const scopeFacts = filterFacts(state.data.newsletters, {
    ...filters,
    topic: null,
    minRelevance: 0,
  });
  const bucketCounts = expandTermPostings(index, postings, state.wardBySource, filters);
  const months = termMentionsByMonth(bucketCounts, scopeFacts);
  const wards = termMentionsByWard(bucketCounts, scopeFacts);
  const totalMentions = months.reduce((total, point) => total + point.mentions, 0);
  message.textContent = `"${term}" appears in ${pluralize(totalMentions, "newsletter")} out of ${numberFormat.format(scopeFacts.length)} in the selected wards and dates.`;

  if (totalMentions === 0) {
    clearResults();
    return;
  }
  timeline.replaceChildren(renderTermTimeline(trimSparseEdges(months), chartWidth(timeline)));
  wardsTitle.classList.remove("hidden");
  wardsChart.replaceChildren(renderTermWards(wards.slice(0, TERM_WARD_LIMIT), term, chartWidth(wardsChart)));
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

function renderWardTopicPanel(
  facts: NewsletterFact[],
  cityFacts: NewsletterFact[],
  filters: AnalyticsFilters,
): void {
  const { chart, caption, table } = panel("ward-topic-heatmap");
  const cells = computeWardTopicCells(facts, cityFacts, ALL_TOPICS);
  const countProcessed = (items: NewsletterFact[]) => items.filter((fact) => fact.topics !== null).length;
  const wardCount = new Set(cells.map((cell) => cell.ward)).size;
  caption.textContent =
    `Based on ${pluralize(countProcessed(facts), "LLM-processed newsletter")} across ${pluralize(wardCount, "ward")}, ` +
    `compared with ${pluralize(countProcessed(cityFacts), "newsletter")} city-wide ` +
    `(wards with fewer than ${MIN_WARD_NEWSLETTERS_FOR_SHARES} processed newsletters are hidden).`;
  if (!chart) return;
  if (cells.length === 0) {
    replaceContent(chart, emptyMessage("Not enough processed newsletters for these filters."));
  } else {
    replaceContent(chart, renderWardTopicHeatmap(cells, filters.topic, chartWidth(chart)));
  }
  setTable(
    table,
    [
      { label: "Ward", value: (cell) => cell.ward },
      { label: "Topic", value: (cell) => humanizeIdentifier(cell.topic) },
      { label: "Ward newsletters", value: (cell) => `${cell.wardTopicNewsletters} / ${cell.wardNewsletters}`, numeric: true },
      { label: "Ward share", value: (cell) => formatPercent(cell.wardShare), numeric: true },
      { label: "City share", value: (cell) => formatPercent(cell.cityShare), numeric: true },
    ],
    cells.filter((cell) => cell.wardTopicNewsletters > 0),
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
  chart.classList.toggle("md:grid-cols-2", !filters.topic);
  const cardWidth = filters.topic ? chartWidth(chart) : Math.max(chartWidth(chart) / 2 - 12, 300);
  replaceContent(
    chart,
    ...topics.map((topic) => {
      const figure = document.createElement("figure");
      const title = document.createElement("figcaption");
      title.className = "text-sm font-semibold text-gray-700";
      title.textContent = humanizeIdentifier(topic);
      const topicPoints = trimSparseEdges(points.filter((point) => point.topic === topic));
      figure.append(title, renderTopicTrend(topicPoints, maxShare, cardWidth));
      return figure;
    }),
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
  const { section, chart, caption, table } = panel("sending-cadence");
  const counts = countNewslettersByWardMonth(facts);
  const factMonths = facts.map((fact) => monthOf(fact.date)).sort();
  const months = factMonths.length ? listMonths(factMonths[0], factMonths[factMonths.length - 1]) : [];
  caption.textContent = `Based on ${pluralize(facts.length, "newsletter")}.`;
  if (!chart) return;
  replaceContent(
    chart,
    counts.length ? renderCadenceHeatmap(counts, months, chartWidth(chart)) : emptyMessage("No newsletters for these filters."),
  );
  setTable(
    table,
    [
      { label: "Ward", value: (count) => count.ward },
      { label: "Month", value: (count) => count.month },
      { label: "Newsletters", value: (count) => count.newsletters, numeric: true },
    ],
    counts,
  );
  const gaps = findLongestGaps(facts, GAP_LIMIT);
  setTable(
    requireElement<HTMLElement>("#cadence-gaps", section),
    [
      { label: "Source", value: (gap) => sourceLabel({ name: gap.alder ?? `Source ${gap.sourceId}`, ward: gap.ward }) },
      { label: "From", value: (gap) => gap.from },
      { label: "To", value: (gap) => gap.to },
      { label: "Days", value: (gap) => gap.days, numeric: true },
    ],
    gaps,
  );
}

function renderRelevancePanel(facts: NewsletterFact[]): void {
  const { chart, caption, table } = panel("relevance-by-ward");
  const rows = computeRelevanceByWard(facts);
  const scored = rows.reduce((total, row) => total + row.scoredNewsletters, 0);
  caption.textContent = `Based on ${pluralize(scored, "scored newsletter")}. Small counts are noisy.`;
  if (!chart) return;
  replaceContent(
    chart,
    rows.length ? renderRelevanceByWard(rows, chartWidth(chart)) : emptyMessage("No scored newsletters for these filters."),
  );
  setTable(
    table,
    [
      { label: "Ward", value: (row) => row.ward },
      { label: "Average relevance", value: (row) => row.averageRelevance.toFixed(2), numeric: true },
      { label: "Scored newsletters", value: (row) => row.scoredNewsletters, numeric: true },
    ],
    rows,
  );
}

function renderCoveragePanel(state: DashboardState, filters: AnalyticsFilters): void {
  const { chart, caption, table } = panel("coverage");
  const sources = selectCoverage(state.data.sources, filters);
  const withoutNewsletters = state.data.sources.filter((source) => source.newsletters === 0).length;
  caption.textContent = `${pluralize(sources.length, "source")} with newsletters` +
    (withoutNewsletters ? `; ${pluralize(withoutNewsletters, "source")} in the database have none yet.` : ".");
  if (!chart) return;
  replaceContent(
    chart,
    sources.length ? renderCoverage(sources, chartWidth(chart)) : emptyMessage("No sources for these wards."),
  );
  setTable(
    table,
    [
      { label: "Source", value: (source) => sourceLabel(source) },
      { label: "First newsletter", value: (source) => source.first_date ?? "" },
      { label: "Last newsletter", value: (source) => source.last_date ?? "" },
      { label: "Newsletters", value: (source) => source.newsletters, numeric: true },
    ],
    sources,
  );
}

// ---------------------------------------------------------------------------
// Orchestration

function renderDashboard(state: DashboardState, form: HTMLFormElement): void {
  const filters = readFilters(form);
  updateWardSummary(filters);
  const facts = filterFacts(state.data.newsletters, filters);
  const factsIgnoringTopic = filterFacts(state.data.newsletters, filters, { ignoreTopic: true });

  renderSummary(facts);
  renderTermExplorer(state, filters);
  renderWardTopicPanel(
    factsIgnoringTopic,
    filterFacts(state.data.newsletters, { ...filters, wards: [] }, { ignoreTopic: true }),
    filters,
  );
  renderTopicTrendsPanel(factsIgnoringTopic, filters);
  renderDistinctivePanel(state);
  renderRisingPanel(state);
  renderCadencePanel(facts);
  renderRelevancePanel(facts);
  renderCoveragePanel(state, filters);
}

function showLoadError(error: unknown): void {
  const dashboard = requireElement<HTMLElement>("#analytics-dashboard");
  const message = emptyMessage(`Could not load analytics data: ${error instanceof Error ? error.message : String(error)}`);
  dashboard.prepend(message);
}

export async function startAnalyticsDashboard(): Promise<void> {
  let data: AnalyticsDataset | null;
  try {
    data = await loadAnalyticsDataset();
  } catch (error) {
    showLoadError(error);
    return;
  }
  if (!data) {
    showLoadError(new Error("Data files are missing. Run the compute script."));
    return;
  }

  const allMonths = [...new Set(data.newsletters.map((fact) => monthOf(fact.date)))].sort();
  const state: DashboardState = {
    data,
    wardBySource: new Map(data.sources.map((source) => [source.id, source.ward])),
    term: "",
  };

  const form = requireElement<HTMLFormElement>("#analytics-filters");
  populateFilterOptions(form, listWards(data.newsletters), allMonths);

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
  distinctiveSelect.addEventListener("change", () => renderDistinctivePanel(state));

  const termInput = requireElement<HTMLInputElement>("#term-input");
  const filtersNow = () => readFilters(form);
  requireElement<HTMLFormElement>("#term-form").addEventListener("submit", (event) => {
    event.preventDefault();
    state.term = termInput.value;
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
