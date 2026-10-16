// The summary tiles above the panels, chosen per view.
import {
  formatDay,
  formatMonth,
  listWindowMonths,
  summarizeWardCounts,
  wardsInScope,
} from "../../lib/analytics/core";
import { describeMonthSpan, describeRecency, pluralize } from "../../lib/analytics/descriptions";
import { formatCount, formatMedian } from "../../lib/analytics/format";
import {
  describeTopicReach,
  findLargestChangeTopic,
  findPeakPoint,
  findWidestReachTopic,
  formatLatestReach,
  formatPointChange,
} from "../../lib/analytics/topic-trends";
import type { DashboardView } from "../../lib/analytics/views";
import { lensLabel, type DashboardRender, type TopicOverview } from "./dashboard-state";

export interface SummaryTile {
  label: string;
  value: string;
  detail: string;
}

export function buildTile({ label, value, detail }: SummaryTile): HTMLElement {
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
    value: formatCount(facts.length),
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
      value: formatCount(profile.windowNewsletters),
      detail: topic
        ? `${span} · ${formatCount(topic.newslettersMentioning)} mention ${lensLabel(state, topic.lens)}`
        : span,
    },
    {
      label: "Coverage start",
      value: profile.firstDate ? formatDay(profile.firstDate) : "–",
      detail: `${pluralize(profile.archiveNewsletters, "newsletter")}, all dates`,
    },
  ];
}

export const VIEW_TILES: Record<DashboardView, (render: DashboardRender) => SummaryTile[]> = {
  overview: buildOverviewTiles,
  topic: buildTopicTiles,
  ward: buildWardTiles,
};
