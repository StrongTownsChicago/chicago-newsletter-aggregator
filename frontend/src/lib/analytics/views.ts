// Which /analytics view fits the selection, and the panels each view shows.
import type { AnalyticsFilters } from "./core";

export type DashboardView = "overview" | "topic" | "ward";

export const DASHBOARD_PANEL_IDS = [
  "term-explorer",
  "civic-calendar",
  "topic-detail",
  "ward-profile",
  "rising-terms",
  "sending-cadence",
  "coverage",
] as const;

export type DashboardPanelId = (typeof DASHBOARD_PANEL_IDS)[number];

/** Each view's panels, top to bottom; the rest are hidden. */
export const VIEW_PANELS: Record<DashboardView, readonly DashboardPanelId[]> = {
  overview: ["term-explorer", "civic-calendar", "rising-terms", "sending-cadence", "coverage"],
  topic: ["topic-detail", "civic-calendar", "term-explorer", "rising-terms", "sending-cadence", "coverage"],
  // One ward's reach is all or nothing, so the calendar and the city-wide panels give way to its profile.
  ward: ["ward-profile", "term-explorer", "coverage"],
};

type ViewSelection = Pick<AnalyticsFilters, "wards" | "lens">;

/** The ward a selection focuses on: the only selected ward, or null. */
export function focusedWard(selection: Pick<AnalyticsFilters, "wards">): string | null {
  return selection.wards.length === 1 ? selection.wards[0] : null;
}

/** One ward wins over a topic; a topic over the overview. */
export function selectDashboardView(selection: ViewSelection): DashboardView {
  if (focusedWard(selection) !== null) return "ward";
  return selection.lens ? "topic" : "overview";
}

/** Back to overview: no wards and no topic, same dates. */
export function clearViewSelection(filters: AnalyticsFilters): AnalyticsFilters {
  return { ...filters, wards: [], lens: null };
}

export interface ViewLabels {
  ward: (ward: string) => string;
  topic: (lensId: string) => string;
}

/** "Overview", "Public safety", "Ward 5" or "Ward 5 · Public safety". */
export function describeDashboardView(selection: ViewSelection, labels: ViewLabels): string {
  const ward = focusedWard(selection);
  const topic = selection.lens ? labels.topic(selection.lens) : null;
  if (ward !== null) return topic ? `${labels.ward(ward)} · ${topic}` : labels.ward(ward);
  return topic ?? "Overview";
}
