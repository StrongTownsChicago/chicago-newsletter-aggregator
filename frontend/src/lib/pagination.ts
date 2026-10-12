/** Newsletters shown per page on paginated listings. */
export const NEWSLETTERS_PER_PAGE = 20;

/**
 * Parses the `page` query parameter of a paginated listing. Missing,
 * non-numeric, fractional, or non-positive values fall back to the first page.
 */
export function parsePageParam(rawPage: string | null): number {
  const page = Number(rawPage);
  return Number.isInteger(page) && page >= 1 ? page : 1;
}

export interface PageRange {
  /** Zero-based index of the first row on the page (inclusive). */
  from: number;
  /** Zero-based index of the last row on the page (inclusive), as PostgREST `range()` expects. */
  to: number;
}

/** Row range for a one-based page number. */
export function getPageRange(
  page: number,
  pageSize: number = NEWSLETTERS_PER_PAGE,
): PageRange {
  const from = (page - 1) * pageSize;
  return { from, to: from + pageSize - 1 };
}

/** Number of pages needed to show `totalCount` rows. */
export function countPages(
  totalCount: number,
  pageSize: number = NEWSLETTERS_PER_PAGE,
): number {
  return Math.ceil(totalCount / pageSize);
}
