// Term explorer panel: a term's share of newsletters by month and the wards using it most.
import {
  filterFacts,
  MIN_MONTH_NEWSLETTERS_FOR_SHARES,
  trimSparseEdges,
  type AnalyticsFilters,
} from "../../../lib/analytics/core";
import { createLazyLoader, fetchTermIndex } from "../../../lib/analytics/data";
import { pluralize } from "../../../lib/analytics/descriptions";
import { formatCount, formatOptionalShare } from "../../../lib/analytics/format";
import { searchScopeForFilters } from "../../../lib/analytics/search-links";
import {
  expandTermPostings,
  normalizeTermQuery,
  resolveIndexedTerm,
  suggestTerms,
  termMentionsByMonth,
  termMentionsByWard,
} from "../../../lib/analytics/terms";
import { renderTermTimeline, renderTermWards } from "../../../lib/analytics/charts/terms";
import type { DashboardState } from "../dashboard-state";
import { chartWidth, emptyMessage, panel, requireElement, setTable } from "../dom";
import { refreshExportButtons } from "../export";

const TERM_WARD_LIMIT = 15;
const TERM_SUGGESTION_LIMIT = 8;

// Shared by every request so concurrent triggers fetch terms.json once.
const loadTermIndex = createLazyLoader(() => fetchTermIndex());

export function renderTermExplorer(state: DashboardState, filters: AnalyticsFilters): void {
  const { section, caption, table } = panel("term-explorer");
  const message = requireElement<HTMLElement>("#term-message", section);
  const results = requireElement<HTMLElement>("#term-results", section);
  const timeline = requireElement<HTMLElement>("#term-timeline", section);
  const wardsChart = requireElement<HTMLElement>("#term-wards", section);
  const suggestions = requireElement<HTMLElement>("#term-suggestions", section);
  const tableView = requireElement<HTMLElement>("[data-table-view]", section);
  const { metadata } = state.data;
  caption.textContent = `${formatCount(metadata.term_count)} terms, each in ${metadata.min_term_newsletters}+ newsletters.`;

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
  message.textContent = `"${indexedTerm}" appears in ${formatCount(totalMentions)} of ${pluralize(scopeFacts.length, "newsletter")}.`;

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

/** Fetch the term index once, then redraw the term explorer with it (or with the error). */
export function requestTermIndex(state: DashboardState, readCurrentFilters: () => AnalyticsFilters): void {
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
