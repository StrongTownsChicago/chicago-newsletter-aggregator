// PNG export of a dashboard panel: title, window, caption, data date and the view's canonical URL.
import { describeDataAsOf, listWindowMonths } from "../../lib/analytics/core";
import { describeMonthSpan, describeWardScope } from "../../lib/analytics/descriptions";
import { formatWard } from "../../lib/analytics/format";
import {
  buildCanonicalViewUrl,
  serializeDashboardUrlState,
  type DashboardViewState,
} from "../../lib/analytics/url-state";
import { focusedWard } from "../../lib/analytics/views";
import { downloadChartPng } from "../../lib/analytics/charts/export";
import { SITE_NAME } from "../../lib/seo";
import { lensLabel, type DashboardState } from "./dashboard-state";
import { requireElement } from "./dom";

const EXPORT_FAILURE_MESSAGE_MS = 3000;

/** Panels whose numbers ignore the global filters, described as such in the export. */
const CITY_WIDE_PANELS = new Set(["rising-terms"]);

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
export function refreshExportButtons(): void {
  document.querySelectorAll<HTMLButtonElement>("button[data-export-png]").forEach((button) => {
    const section = button.closest<HTMLElement>("section");
    const hasChart = Boolean(section && exportRegion(section)?.querySelector("svg"));
    button.disabled = !hasChart;
    button.hidden = !hasChart;
  });
}

export async function exportPanel(state: DashboardState, button: HTMLButtonElement, view: DashboardViewState): Promise<void> {
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
