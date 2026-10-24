// Client wiring for /analytics: reads the filters, recomputes each panel with
// the pure functions in lib/, renders the charts, and mirrors the view in the URL.
// The panels, tiles, filters and PNG export live beside it in client/analytics/.
import { classifyDateWindow, type AnalyticsDataset, type AnalyticsFilters } from "../../lib/analytics/core";
import { formatWard } from "../../lib/analytics/format";
import { normalizeTermQuery } from "../../lib/analytics/terms";
import {
  chooseHistoryMode,
  parseDashboardUrlState,
  reconcileDateWindow,
  serializeDashboardUrlState,
  type DashboardViewState,
} from "../../lib/analytics/url-state";
import {
  clearViewSelection,
  DASHBOARD_PANEL_IDS,
  describeDashboardView,
  selectDashboardView,
  VIEW_PANELS,
  type DashboardPanelId,
  type DashboardView,
} from "../../lib/analytics/views";
import {
  buildDashboardState,
  buildRender,
  lensLabel,
  type DashboardRender,
  type DashboardState,
} from "./dashboard-state";
import { requireElement } from "./dom";
import { exportPanel, refreshExportButtons } from "./export";
import {
  populateFilterOptions,
  readFilters,
  renderDateWindowStatus,
  setDateWindow,
  setWardSelection,
  updateWardSummary,
  wireWardPickerDismissal,
} from "./filters";
import { renderCivicCalendarPanel } from "./panels/civic-calendar";
import { renderCoveragePanel } from "./panels/coverage";
import { renderLensDefinitions } from "./panels/lens-definitions";
import { renderRisingPanel } from "./panels/rising-terms";
import { renderCadencePanel } from "./panels/sending-cadence";
import { renderTermExplorer, requestTermIndex } from "./panels/term-explorer";
import { renderTopicDetailPanel } from "./panels/topic-detail";
import { renderWardProfilePanel } from "./panels/ward-profile";
import { buildTile, VIEW_TILES } from "./tiles";

const RESIZE_DEBOUNCE_MS = 200;

const PANEL_RENDERERS: Record<DashboardPanelId, (render: DashboardRender) => void> = {
  "term-explorer": ({ state, filters }) => renderTermExplorer(state, filters),
  "civic-calendar": renderCivicCalendarPanel,
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

function renderDashboard(
  state: DashboardState,
  controls: DashboardControls,
  selectTopic: (lensId: string) => void,
  announce: boolean,
): void {
  const filters = readFilters(controls.form);
  const view = selectDashboardView(filters);
  updateWardSummary(filters);
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

/** The dashboard's controls, looked up once. */
interface DashboardControls {
  form: HTMLFormElement;
  termInput: HTMLInputElement;
}

function readViewState(state: DashboardState, controls: DashboardControls): DashboardViewState {
  return {
    filters: readFilters(controls.form),
    term: normalizeTermQuery(state.term),
  };
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
    termInput: requireElement<HTMLInputElement>("#term-input"),
  };
  const { form, termInput } = controls;
  populateFilterOptions(
    form,
    { wards: state.urlContext.wards, months: state.dataMonths, lenses: data.lenses.lenses },
    state.urlContext.defaultFromMonth,
  );
  wireWardPickerDismissal(requireElement<HTMLDetailsElement>("#ward-picker"));
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
