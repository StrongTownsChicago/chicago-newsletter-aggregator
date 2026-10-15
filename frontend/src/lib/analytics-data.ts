// Fetches the analytics JSON written by `uv run python -m utils.compute_analytics`.
// The files are committed under frontend/public/analytics-data/ and served as
// static assets, so neither the server bundle nor the client bundle contains
// them. The large term index is fetched separately, only when the term
// explorer needs it (see createLazyLoader).
import type {
  AnalyticsDataset,
  AnalyticsMetadata,
  DistinctiveTerm,
  LensSummary,
  NewsletterFact,
  RisingTerms,
  SourceCoverage,
  TermIndex,
} from "./analytics";

/** URL path of the static analytics files (frontend/public/analytics-data/). */
export const ANALYTICS_DATA_BASE_PATH = "/analytics-data";

/** Contents of each generated file, keyed by file stem. Add new files here. */
export interface AnalyticsDataFiles {
  metadata: AnalyticsMetadata;
  newsletters: { newsletters: NewsletterFact[] };
  sources: { sources: SourceCoverage[] };
  lenses: LensSummary;
  terms: TermIndex;
  distinctive: { wards: Record<string, DistinctiveTerm[]> };
  rising: RisingTerms;
}

export type AnalyticsDataFile = keyof AnalyticsDataFiles;

/** Files the dashboard needs before it can render anything. */
export const CORE_ANALYTICS_FILES = [
  "metadata",
  "newsletters",
  "sources",
  "lenses",
  "distinctive",
  "rising",
] as const satisfies readonly AnalyticsDataFile[];

const HTTP_NOT_FOUND = 404;

export type AnalyticsDataErrorKind = "missing" | "failed";

/** A data file that is absent ("missing") or could not be loaded ("failed"). */
export class AnalyticsDataError extends Error {
  constructor(
    readonly kind: AnalyticsDataErrorKind,
    readonly fileName: string,
    detail: string,
  ) {
    super(`${fileName}: ${detail}`);
    this.name = "AnalyticsDataError";
  }
}

export type FetchFunction = (url: string) => Promise<Response>;

export function analyticsFileName(file: AnalyticsDataFile): string {
  return `${file}.json`;
}

export function analyticsFileUrl(file: AnalyticsDataFile): string {
  return `${ANALYTICS_DATA_BASE_PATH}/${analyticsFileName(file)}`;
}

function describeError(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Fetch and parse one generated file, classifying every failure. */
export async function fetchAnalyticsFile<K extends AnalyticsDataFile>(
  file: K,
  fetchFile: FetchFunction = fetch,
): Promise<AnalyticsDataFiles[K]> {
  const fileName = analyticsFileName(file);
  let response: Response;
  try {
    response = await fetchFile(analyticsFileUrl(file));
  } catch (error) {
    throw new AnalyticsDataError("failed", fileName, describeError(error));
  }
  if (response.status === HTTP_NOT_FOUND) {
    throw new AnalyticsDataError("missing", fileName, "not found");
  }
  if (!response.ok) {
    throw new AnalyticsDataError("failed", fileName, `HTTP ${response.status}`);
  }
  try {
    return (await response.json()) as AnalyticsDataFiles[K];
  } catch (error) {
    throw new AnalyticsDataError("failed", fileName, `invalid JSON (${describeError(error)})`);
  }
}

export type AnalyticsFileSet<F extends readonly AnalyticsDataFile[]> = {
  [K in F[number]]: AnalyticsDataFiles[K];
};

export type AnalyticsLoadResult<T> =
  | { status: "ready"; data: T }
  | { status: "missing"; missingFiles: string[] }
  | { status: "failed"; message: string };

/**
 * Fetch several files in parallel. Missing files are reported together so the
 * setup instructions can list them; any other failure takes precedence.
 */
export async function loadAnalyticsFiles<const F extends readonly AnalyticsDataFile[]>(
  files: F,
  fetchFile: FetchFunction = fetch,
): Promise<AnalyticsLoadResult<AnalyticsFileSet<F>>> {
  const results = await Promise.allSettled(files.map((file) => fetchAnalyticsFile(file, fetchFile)));
  const errors = results.flatMap((result) => (result.status === "rejected" ? [result.reason as unknown] : []));
  const failure = errors.find((error) => !(error instanceof AnalyticsDataError) || error.kind === "failed");
  if (failure) return { status: "failed", message: describeError(failure) };
  if (errors.length > 0) {
    return { status: "missing", missingFiles: (errors as AnalyticsDataError[]).map((error) => error.fileName) };
  }
  const data = Object.fromEntries(
    files.map((file, position) => [file, (results[position] as PromiseFulfilledResult<unknown>).value]),
  ) as AnalyticsFileSet<F>;
  return { status: "ready", data };
}

/** Load the core files and shape them into the dataset the dashboard renders. */
export async function loadCoreAnalyticsData(
  fetchFile: FetchFunction = fetch,
): Promise<AnalyticsLoadResult<AnalyticsDataset>> {
  const result = await loadAnalyticsFiles(CORE_ANALYTICS_FILES, fetchFile);
  if (result.status !== "ready") return result;
  const { metadata, newsletters, sources, lenses, distinctive, rising } = result.data;
  return {
    status: "ready",
    data: {
      metadata,
      newsletters: newsletters.newsletters,
      sources: sources.sources,
      lenses,
      distinctiveByWard: distinctive.wards,
      rising,
    },
  };
}

/** Fetch the term index on its own; it is most of the data and only the term explorer uses it. */
export function fetchTermIndex(fetchFile: FetchFunction = fetch): Promise<TermIndex> {
  return fetchAnalyticsFile("terms", fetchFile);
}

/**
 * Wrap a loader so it runs at most once at a time and its result is reused.
 * A failed load is forgotten, so the next call retries.
 */
export function createLazyLoader<T>(load: () => Promise<T>): () => Promise<T> {
  let pending: Promise<T> | null = null;
  return () => {
    pending ??= load().catch((error: unknown) => {
      pending = null;
      throw error;
    });
    return pending;
  };
}
