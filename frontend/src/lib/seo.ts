export const SITE_NAME = "Chicago Alderman Newsletter Tracker";

/** Search engines typically display roughly this many characters of a meta description. */
export const META_DESCRIPTION_MAX_LENGTH = 155;

const ELLIPSIS = "…";

/**
 * Collapses whitespace and shortens `text` to at most `maxLength` characters,
 * cutting at a word boundary and appending an ellipsis when truncated.
 */
export function truncateDescription(
  text: string,
  maxLength: number = META_DESCRIPTION_MAX_LENGTH,
): string {
  const normalized = text.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }

  const hardCut = normalized.slice(0, maxLength - ELLIPSIS.length);
  const lastSpace = hardCut.lastIndexOf(" ");
  const wordBoundaryCut = lastSpace > 0 ? hardCut.slice(0, lastSpace) : hardCut;
  return wordBoundaryCut.replace(/[\s.,;:!?-]+$/, "") + ELLIPSIS;
}

export interface NewsletterDescriptionInput {
  subject: string;
  summary: string | null;
  received_date: string;
  sources?: { name: string; ward_number: string | null } | null;
}

function formatReceivedDate(receivedDate: string): string | null {
  const date = new Date(receivedDate);
  if (Number.isNaN(date.getTime())) {
    return null;
  }
  return date.toLocaleDateString("en-US", {
    year: "numeric",
    month: "long",
    day: "numeric",
    timeZone: "America/Chicago",
  });
}

/**
 * Builds the meta description for a newsletter detail page. Uses the LLM summary
 * when available; otherwise describes the newsletter by sender, ward, date, and subject.
 */
export function buildNewsletterDescription(
  newsletter: NewsletterDescriptionInput,
): string {
  const summary = newsletter.summary?.trim();
  if (summary) {
    return truncateDescription(summary);
  }

  const source = newsletter.sources;
  const sender = source?.name
    ? source.ward_number
      ? `${source.name} (Ward ${source.ward_number})`
      : source.name
    : "a Chicago alderman";
  const formattedDate = formatReceivedDate(newsletter.received_date);
  const sentOn = formattedDate ? ` sent ${formattedDate}` : "";

  return truncateDescription(
    `Newsletter from ${sender}${sentOn}: ${newsletter.subject.trim()}`,
  );
}

/**
 * Builds the canonical URL for a page. Query strings are dropped and trailing
 * slashes removed (except for the root) so each page has exactly one canonical form.
 *
 * Paginated listings pass `page` so that page 2+ canonicalizes to itself
 * (`?page=N`) rather than to page 1, which would discourage crawlers from
 * following deeper pages and the newsletters linked from them.
 */
export function buildCanonicalUrl(
  pathname: string,
  site: URL | string,
  page?: number,
): string {
  const normalizedPath =
    pathname.length > 1 ? pathname.replace(/\/+$/, "") : pathname;
  const canonicalUrl = new URL(normalizedPath || "/", site);
  if (page !== undefined && Number.isInteger(page) && page > 1) {
    canonicalUrl.searchParams.set("page", String(page));
  }
  return canonicalUrl.href;
}

/**
 * Returns true when the request host differs from the production site host.
 * Used to keep Cloudflare Pages preview and *.pages.dev hosts out of search indexes.
 */
export function isNonProductionHost(
  requestHost: string,
  productionSite: URL | string | undefined,
): boolean {
  if (!productionSite) {
    return true;
  }
  const productionHost = new URL(productionSite).host.toLowerCase();
  return requestHost.toLowerCase() !== productionHost;
}
