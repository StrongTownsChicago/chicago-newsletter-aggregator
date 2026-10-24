// @vitest-environment node
import { describe, expect, it } from "vitest";
import fc from "fast-check";
import {
  PAGE_CACHE_VERSION_PARAM,
  buildPageCacheKey,
  findPageCacheMaxAge,
  hasTrackingParams,
} from "../../lib/server/page-cache";

const ORIGIN = "https://example.test";
const PROPERTY_RUNS = { numRuns: 200 };

const trackingName = fc.oneof(
  fc.constantFrom("fbclid", "gclid", "mc_cid", "mc_eid", "FBCLID", "Mc_Eid"),
  fc.string({ minLength: 1, maxLength: 12 }).map((suffix) => `utm_${suffix}`),
  fc.string({ minLength: 1, maxLength: 12 }).map((suffix) => `UTM_${suffix}`),
);

const pageParamName = fc
  .string({ unit: "binary", maxLength: 12 })
  .filter((name) => !/^(utm_.+|fbclid|gclid|mc_cid|mc_eid)$/i.test(name) && name !== PAGE_CACHE_VERSION_PARAM);

const paramValue = fc.string({ unit: "binary", maxLength: 12 });

interface QueryEntry {
  name: string;
  value: string;
  isTracking: boolean;
}

const queryEntries: fc.Arbitrary<QueryEntry[]> = fc.array(
  fc.oneof(
    fc.record({ name: pageParamName, value: paramValue, isTracking: fc.constant(false) }),
    fc.record({ name: trackingName, value: paramValue, isTracking: fc.constant(true) }),
  ),
  { maxLength: 10 },
);

const pathname = fc.constantFrom("/", "/search", "/newsletter/7", "/ward/12", "/preferences");
const version = fc.string({ minLength: 1, maxLength: 20 });

function buildUrl(path: string, entries: QueryEntry[]): URL {
  const url = new URL(path, ORIGIN);
  for (const { name, value } of entries) url.searchParams.append(name, value);
  return url;
}

describe("buildPageCacheKey properties", () => {
  it("gives a tracked visit the key of the same visit without its tracking parameters", () => {
    fc.assert(
      fc.property(pathname, queryEntries, version, (path, entries, buildVersion) => {
        const untracked = entries.filter((entry) => !entry.isTracking);
        expect(buildPageCacheKey(buildUrl(path, entries), buildVersion).url).toBe(
          buildPageCacheKey(buildUrl(path, untracked), buildVersion).url,
        );
        expect(hasTrackingParams(buildUrl(path, entries))).toBe(untracked.length < entries.length);
      }),
      PROPERTY_RUNS,
    );
  });

  it("keeps the page's own parameters in order and carries the version exactly once", () => {
    fc.assert(
      fc.property(pathname, queryEntries, version, (path, entries, buildVersion) => {
        const keyUrl = new URL(buildPageCacheKey(buildUrl(path, entries), buildVersion).url);
        expect(keyUrl.origin + keyUrl.pathname).toBe(ORIGIN + path);
        expect(keyUrl.searchParams.getAll(PAGE_CACHE_VERSION_PARAM)).toEqual([buildVersion]);
        expect(hasTrackingParams(keyUrl)).toBe(false);
        const pageEntries = [...keyUrl.searchParams].filter(([name]) => name !== PAGE_CACHE_VERSION_PARAM);
        expect(pageEntries).toEqual(entries.filter((entry) => !entry.isTracking).map(({ name, value }) => [name, value]));
      }),
      PROPERTY_RUNS,
    );
  });

  it("overrides a version parameter the visitor supplied", () => {
    fc.assert(
      fc.property(pathname, paramValue, version, (path, suppliedVersion, buildVersion) => {
        const url = new URL(path, ORIGIN);
        url.searchParams.append(PAGE_CACHE_VERSION_PARAM, suppliedVersion);
        url.searchParams.append(PAGE_CACHE_VERSION_PARAM, suppliedVersion);
        const keyUrl = new URL(buildPageCacheKey(url, buildVersion).url);
        expect(keyUrl.searchParams.getAll(PAGE_CACHE_VERSION_PARAM)).toEqual([buildVersion]);
      }),
      PROPERTY_RUNS,
    );
  });
});

const pathSegment = fc.string({ minLength: 1, maxLength: 10 }).filter((segment) => !segment.includes("/"));

describe("findPageCacheMaxAge properties", () => {
  it("ignores trailing slashes after a non-root path", () => {
    fc.assert(
      fc.property(
        fc.array(pathSegment, { minLength: 1, maxLength: 3 }),
        fc.integer({ min: 1, max: 3 }),
        (segments, slashCount) => {
          const path = `/${segments.join("/")}`;
          expect(findPageCacheMaxAge(path + "/".repeat(slashCount))).toBe(findPageCacheMaxAge(path));
        },
      ),
      PROPERTY_RUNS,
    );
  });

  it("caches nothing below a newsletter or ward page", () => {
    fc.assert(
      fc.property(fc.constantFrom("newsletter", "ward"), pathSegment, pathSegment, (section, id, extra) => {
        expect(findPageCacheMaxAge(`/${section}/${id}`)).not.toBeNull();
        expect(findPageCacheMaxAge(`/${section}/${id}/${extra}`)).toBeNull();
      }),
      PROPERTY_RUNS,
    );
  });
});
