import { describe, expect, it, vi } from "vitest";
import {
  AnalyticsDataError,
  analyticsFileUrl,
  CORE_ANALYTICS_FILES,
  createLazyLoader,
  fetchAnalyticsFile,
  fetchTermIndex,
  loadCoreAnalyticsData,
  type AnalyticsDataFile,
  type AnalyticsDataFiles,
  type FetchFunction,
} from "../../lib/analytics-data";

const FILE_CONTENTS: AnalyticsDataFiles = {
  metadata: {
    generated_at: "2026-10-14T20:05:00+00:00",
    newsletter_count: 1,
    source_count: 1,
    first_date: "2026-10-01",
    last_date: "2026-10-01",
    term_count: 1,
    min_term_newsletters: 1,
  },
  newsletters: { newsletters: [] },
  sources: { sources: [] },
  lenses: { text: "cleaned", min_phrase_occurrences: 2, readable_newsletters: 0, lenses: [] },
  terms: { min_newsletters: 1, months: [], buckets: [], terms: {} },
  distinctive: { wards: { "1": [] } },
  rising: { latest_month: null, baseline_months: [], latest_active_wards: 0, baseline_active_wards: [], terms: [] },
};

type ResponseOverrides = Partial<Record<AnalyticsDataFile, () => Promise<Response>>>;

function jsonResponse(body: unknown): Response {
  return new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } });
}

/** A fetch that serves FILE_CONTENTS by URL, with per-file overrides. */
function fakeFetch(overrides: ResponseOverrides = {}) {
  return vi.fn<FetchFunction>(async (url) => {
    const file = (Object.keys(FILE_CONTENTS) as AnalyticsDataFile[]).find((name) => analyticsFileUrl(name) === url);
    if (!file) return new Response("Not found", { status: 404 });
    const override = overrides[file];
    return override ? override() : jsonResponse(FILE_CONTENTS[file]);
  });
}

const notFound = async () => new Response("<h1>Not found</h1>", { status: 404 });
const networkError = () => Promise.reject(new TypeError("Failed to fetch"));

describe("fetchAnalyticsFile", () => {
  it("fetches the file from the static data path and parses it", async () => {
    const fetchFile = fakeFetch();
    await expect(fetchAnalyticsFile("metadata", fetchFile)).resolves.toEqual(FILE_CONTENTS.metadata);
    expect(fetchFile).toHaveBeenCalledWith("/analytics-data/metadata.json");
  });

  it("reports a 404 as a missing file", async () => {
    const error: unknown = await fetchAnalyticsFile("rising", fakeFetch({ rising: notFound })).catch(
      (caught: unknown) => caught,
    );
    expect(error).toBeInstanceOf(AnalyticsDataError);
    expect(error).toMatchObject({ kind: "missing", fileName: "rising.json" });
  });

  it("reports server errors, network errors, and invalid JSON as failures", async () => {
    const serverError = fakeFetch({ rising: async () => new Response("oops", { status: 500 }) });
    const invalidJson = fakeFetch({ rising: async () => new Response("<html>", { status: 200 }) });

    await expect(fetchAnalyticsFile("rising", serverError)).rejects.toMatchObject({
      kind: "failed",
      message: "rising.json: HTTP 500",
    });
    await expect(fetchAnalyticsFile("rising", fakeFetch({ rising: networkError }))).rejects.toMatchObject({
      kind: "failed",
      message: "rising.json: Failed to fetch",
    });
    await expect(fetchAnalyticsFile("rising", invalidJson)).rejects.toMatchObject({ kind: "failed" });
  });
});

describe("loadCoreAnalyticsData", () => {
  it("shapes the core files into a dataset without fetching the term index", async () => {
    const fetchFile = fakeFetch();
    const result = await loadCoreAnalyticsData(fetchFile);

    expect(result).toEqual({
      status: "ready",
      data: {
        metadata: FILE_CONTENTS.metadata,
        newsletters: [],
        sources: [],
        lenses: FILE_CONTENTS.lenses,
        distinctiveByWard: { "1": [] },
        rising: FILE_CONTENTS.rising,
      },
    });
    expect(fetchFile).toHaveBeenCalledTimes(CORE_ANALYTICS_FILES.length);
    expect(fetchFile).not.toHaveBeenCalledWith(analyticsFileUrl("terms"));
  });

  it("lists every missing file, as on a checkout before the first refresh", async () => {
    const result = await loadCoreAnalyticsData(fakeFetch({ metadata: notFound, sources: notFound }));
    expect(result).toEqual({ status: "missing", missingFiles: ["metadata.json", "sources.json"] });
  });

  it("reports a failure ahead of missing files", async () => {
    const result = await loadCoreAnalyticsData(fakeFetch({ metadata: notFound, newsletters: networkError }));
    expect(result).toEqual({ status: "failed", message: "newsletters.json: Failed to fetch" });
  });
});

describe("lazy term index", () => {
  it("fetches terms.json only when first requested, then reuses it", async () => {
    const fetchFile = fakeFetch();
    const loadTerms = createLazyLoader(() => fetchTermIndex(fetchFile));
    expect(fetchFile).not.toHaveBeenCalled();

    const [first, second] = await Promise.all([loadTerms(), loadTerms()]);
    await loadTerms();

    expect(first).toEqual(FILE_CONTENTS.terms);
    expect(second).toBe(first);
    expect(fetchFile).toHaveBeenCalledTimes(1);
    expect(fetchFile).toHaveBeenCalledWith("/analytics-data/terms.json");
  });

  it("retries after a failed load", async () => {
    const load = vi.fn<() => Promise<string>>().mockRejectedValueOnce(new Error("offline")).mockResolvedValueOnce("terms");
    const loadTerms = createLazyLoader(load);

    await expect(loadTerms()).rejects.toThrow("offline");
    await expect(loadTerms()).resolves.toBe("terms");
    expect(load).toHaveBeenCalledTimes(2);
  });
});
