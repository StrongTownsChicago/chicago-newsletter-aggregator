// Loads the analytics JSON written by `uv run python -m utils.compute_analytics`.
// The files are gitignored, so a clean checkout (including production builds)
// has none of them; import.meta.glob simply matches nothing in that case.
import type {
  AnalyticsDataset,
  AnalyticsMetadata,
  DistinctiveTerm,
  NewsletterFact,
  RisingTerms,
  SourceCoverage,
  TermIndex,
} from "./analytics";

const DATA_DIRECTORY = "../data/analytics";

export const ANALYTICS_DATA_FILES = [
  "metadata",
  "newsletters",
  "sources",
  "terms",
  "distinctive",
  "rising",
] as const;

type AnalyticsDataFile = (typeof ANALYTICS_DATA_FILES)[number];

const loaders = import.meta.glob<unknown>("../data/analytics/*.json", { import: "default" });

function loaderFor(file: AnalyticsDataFile): (() => Promise<unknown>) | undefined {
  return loaders[`${DATA_DIRECTORY}/${file}.json`];
}

/** Data files the dashboard needs that have not been generated yet. */
export function findMissingAnalyticsFiles(): string[] {
  return ANALYTICS_DATA_FILES.filter((file) => !loaderFor(file)).map((file) => `${file}.json`);
}

async function loadFile<T>(file: AnalyticsDataFile): Promise<T> {
  const loader = loaderFor(file);
  if (!loader) throw new Error(`Missing analytics data file: ${file}.json`);
  return (await loader()) as T;
}

export async function loadAnalyticsMetadata(): Promise<AnalyticsMetadata | null> {
  return loaderFor("metadata") ? loadFile<AnalyticsMetadata>("metadata") : null;
}

/** Load every analytics file, or null when any is missing. */
export async function loadAnalyticsDataset(): Promise<AnalyticsDataset | null> {
  if (findMissingAnalyticsFiles().length > 0) return null;
  const [metadata, newsletters, sources, terms, distinctive, rising] = await Promise.all([
    loadFile<AnalyticsMetadata>("metadata"),
    loadFile<{ newsletters: NewsletterFact[] }>("newsletters"),
    loadFile<{ sources: SourceCoverage[] }>("sources"),
    loadFile<TermIndex>("terms"),
    loadFile<{ wards: Record<string, DistinctiveTerm[]> }>("distinctive"),
    loadFile<RisingTerms>("rising"),
  ]);
  return {
    metadata,
    newsletters: newsletters.newsletters,
    sources: sources.sources,
    terms,
    distinctiveByWard: distinctive.wards,
    rising,
  };
}
