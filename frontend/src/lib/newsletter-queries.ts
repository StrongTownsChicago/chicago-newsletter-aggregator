import type { Newsletter, Source } from "./supabase";

/**
 * Column lists for newsletter queries.
 *
 * Listing pages (homepage, search) render summary cards and must never fetch
 * newsletter bodies (`raw_html`, `plain_text`) or source contact details
 * (`email_address`, `phone`). Each list below is the single source of truth
 * for both the PostgREST select string and the matching TypeScript row type.
 */

/** Newsletter columns rendered by NewsletterCard. */
export const NEWSLETTER_CARD_COLUMNS = [
  "id",
  "subject",
  "received_date",
  "summary",
  "topics",
  "relevance_score",
] as const satisfies readonly (keyof Newsletter)[];

/** Source columns rendered by NewsletterCard. */
export const SOURCE_CARD_COLUMNS = [
  "name",
  "ward_number",
] as const satisfies readonly (keyof Source)[];

/** Source columns rendered by the newsletter detail page (public contact info). */
export const SOURCE_DETAIL_COLUMNS = [
  "name",
  "ward_number",
  "phone",
  "email_address",
] as const satisfies readonly (keyof Source)[];

export type NewsletterCardSource = Pick<
  Source,
  (typeof SOURCE_CARD_COLUMNS)[number]
>;

export type NewsletterCardRow = Pick<
  Newsletter,
  (typeof NEWSLETTER_CARD_COLUMNS)[number]
> & {
  sources: NewsletterCardSource | null;
};

interface SourceJoinOptions {
  /**
   * Use an inner join so that filters on `sources.*` columns exclude
   * newsletters whose source does not match (rather than nulling the embed).
   */
  filtersOnSource: boolean;
}

const sourcesRelation = ({ filtersOnSource }: SourceJoinOptions): string =>
  filtersOnSource ? "sources!inner" : "sources";

/** Select string for paginated listing queries that feed NewsletterCard. */
export const buildNewsletterCardSelect = (
  options: SourceJoinOptions,
): string =>
  `${NEWSLETTER_CARD_COLUMNS.join(", ")}, ${sourcesRelation(options)}(${SOURCE_CARD_COLUMNS.join(", ")})`;

/**
 * Select string for `head: true` count queries. Only embeds sources when a
 * source filter needs the inner join to restrict the counted rows.
 */
export const buildNewsletterCountSelect = ({
  filtersOnSource,
}: SourceJoinOptions): string =>
  filtersOnSource ? `id, ${sourcesRelation({ filtersOnSource })}(id)` : "id";

/** Select string for the newsletter detail page, which needs the full body. */
export const NEWSLETTER_DETAIL_SELECT = `*, sources(${SOURCE_DETAIL_COLUMNS.join(", ")})`;
