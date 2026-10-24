// The /analytics dashboard's state, and everything one render computes from it.
import {
  EMPTY_FILTERS,
  filterFacts,
  findBroadCoverageWindow,
  listSourceWards,
  listWindowMonths,
  monthOf,
  type AnalyticsDataset,
  type AnalyticsFilters,
  type BroadCoverageWindow,
  type LensDefinition,
  type NewsletterFact,
  type TermIndex,
} from "../../lib/analytics/core";
import {
  computeLensWardReach,
  MIN_ACTIVE_WARDS_FOR_REACH,
  type LensReachCell,
} from "../../lib/analytics/reach";
import {
  findAsOfMonth,
  listFullMonths,
  summarizeTopicTrends,
  type TopicTrend,
} from "../../lib/analytics/topic-trends";
import type { DashboardUrlContext } from "../../lib/analytics/url-state";
import { focusedWard, type DashboardView } from "../../lib/analytics/views";
import { buildWardProfile, type WardProfile } from "../../lib/analytics/ward-profile";

export interface DashboardState {
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

/** City-wide views fade thin months; a ward selection is small by design. */
function reachFadeThreshold(filters: AnalyticsFilters): number {
  return filters.wards.length ? 0 : MIN_ACTIVE_WARDS_FOR_REACH;
}

export function lensLabel(state: DashboardState, lensId: string): string {
  return state.lensById.get(lensId)?.label ?? lensId;
}

/** Ward reach for every topic in the window, and each topic's trend over its full months. */
export interface TopicOverview {
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

/** Everything one render of the dashboard needs, computed once. */
export interface DashboardRender {
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

export function buildRender(state: DashboardState, filters: AnalyticsFilters, selectTopic: (lensId: string) => void): DashboardRender {
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
            state.data,
            ward,
            { window: months, archive: state.dataMonths },
            state.urlContext.lensIds,
          ),
    selectTopic,
  };
}

export function buildDashboardState(data: AnalyticsDataset): DashboardState {
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
