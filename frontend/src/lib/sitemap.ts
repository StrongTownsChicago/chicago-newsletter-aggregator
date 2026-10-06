import type { SupabaseClient } from "@supabase/supabase-js";

/** PostgREST caps each response at this many rows by default. */
export const SUPABASE_PAGE_SIZE = 1000;

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

function buildUrlElement(entry: NewsletterSitemapEntry, site: URL | string): string {
  const location = new URL(`/newsletter/${encodeURIComponent(entry.id)}`, site).href;
  const lastmod = toLastmod(entry.received_date);
  const lastmodElement = lastmod ? `<lastmod>${lastmod}</lastmod>` : "";
  return `<url><loc>${escapeXml(location)}</loc>${lastmodElement}</url>`;
}

/** Renders a sitemap `<urlset>` document listing every newsletter detail page. */
export function buildNewsletterSitemapXml(
  entries: NewsletterSitemapEntry[],
  site: URL | string,
): string {
  const urlElements = entries.map((entry) => buildUrlElement(entry, site)).join("\n");
  return [
    '<?xml version="1.0" encoding="UTF-8"?>',
    '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    urlElements,
    "</urlset>",
  ]
    .filter(Boolean)
    .join("\n");
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
