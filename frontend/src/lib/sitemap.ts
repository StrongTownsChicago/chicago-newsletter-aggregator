import type { SupabaseClient } from "@supabase/supabase-js";
import { ALL_WARD_NUMBERS, WARD_DIRECTORY_PATH, buildWardPath } from "./wards";

/** PostgREST caps each response at this many rows by default. */
export const SUPABASE_PAGE_SIZE = 1000;

const SITEMAP_CACHE_MAX_AGE_SECONDS = 60 * 60;

/** Response headers shared by the server-rendered sitemap endpoints. */
export const SITEMAP_RESPONSE_HEADERS = {
  "Content-Type": "application/xml; charset=utf-8",
  "Cache-Control": `public, max-age=${SITEMAP_CACHE_MAX_AGE_SECONDS}`,
} as const;

export interface NewsletterSitemapEntry {
  id: string;
  received_date: string | null;
}

const XML_ESCAPES: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&apos;",
};

function escapeXml(value: string): string {
  return value.replace(/[&<>"']/g, (character) => XML_ESCAPES[character]);
}

function toLastmod(receivedDate: string | null): string | null {
  if (!receivedDate) {
    return null;
  }
  const date = new Date(receivedDate);
  return Number.isNaN(date.getTime()) ? null : date.toISOString();
}

/** A page to list in a sitemap. */
export interface SitemapPage {
  /** Site-relative path, e.g. `/ward/1`. */
  path: string;
  /** Last modification timestamp in any `Date`-parsable form. */
  lastmod?: string | null;
}

function buildUrlElement(page: SitemapPage, site: URL | string): string {
  const location = new URL(page.path, site).href;
  const lastmod = toLastmod(page.lastmod ?? null);
  const lastmodElement = lastmod ? `<lastmod>${lastmod}</lastmod>` : "";
  return `<url><loc>${escapeXml(location)}</loc>${lastmodElement}</url>`;
}

/** Renders a sitemap `<urlset>` document listing the given pages. */
export function buildSitemapXml(
  pages: readonly SitemapPage[],
  site: URL | string,
): string {
  const urlElements = pages.map((page) => buildUrlElement(page, site)).join("\n");
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    urlElements,
    "</urlset>",
  ]
    .filter(Boolean)
    .join("\n");
}

/** Renders a sitemap `<urlset>` document listing every newsletter detail page. */
export function buildNewsletterSitemapXml(
  entries: NewsletterSitemapEntry[],
  site: URL | string,
): string {
  return buildSitemapXml(
    entries.map((entry) => ({
      path: `/newsletter/${encodeURIComponent(entry.id)}`,
      lastmod: entry.received_date,
    })),
    site,
  );
}

/**
 * Pages for the ward sitemap: the ward directory plus one page per ward.
 * Every ward is listed because ward numbers are fixed, so the set needs no
 * database query.
 */
export function buildWardSitemapPages(): SitemapPage[] {
  return [
    { path: WARD_DIRECTORY_PATH },
    ...ALL_WARD_NUMBERS.map((wardNumber) => ({ path: buildWardPath(wardNumber) })),
  ];
}

/**
 * Fetches the id and received_date of every newsletter, paging past the
 * PostgREST row cap. Ordered by id so pages are stable across requests.
 */
export async function fetchNewsletterSitemapEntries(
  supabase: SupabaseClient,
  pageSize: number = SUPABASE_PAGE_SIZE,
): Promise<NewsletterSitemapEntry[]> {
  const entries: NewsletterSitemapEntry[] = [];

  for (let start = 0; ; start += pageSize) {
    const { data, error } = await supabase
      .from("newsletters")
      .select("id, received_date")
      .order("id", { ascending: true })
      .range(start, start + pageSize - 1);

    if (error) {
      throw new Error(`Failed to fetch newsletters for sitemap: ${error.message}`);
    }

    const page = (data ?? []) as NewsletterSitemapEntry[];
    entries.push(...page);

    if (page.length < pageSize) {
      return entries;
    }
  }
}
