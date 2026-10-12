import type { SupabaseClient } from "@supabase/supabase-js";
import {
  SOURCE_WARD_DIRECTORY_SELECT,
  SOURCE_WARD_PROFILE_SELECT,
  buildNewsletterCardSelect,
  buildNewsletterCountSelect,
  type NewsletterCardRow,
  type WardDirectorySource,
  type WardProfileSource,
} from "./newsletter-queries";
import { getPageRange } from "./pagination";
import { ALDERMAN_SOURCE_TYPE } from "./wards";

/** Newsletter column used to order ward listings and report recency. */
const RECEIVED_DATE_COLUMN = "received_date";

/**
 * Fetches the alder source(s) for a ward. A ward normally has one alder, but
 * more than one source can share a ward (e.g. after a change of alder), so
 * all are returned, most recently added first.
 */
export async function fetchWardSources(
  supabase: SupabaseClient,
  wardNumber: number,
): Promise<WardProfileSource[]> {
  const { data, error } = await supabase
    .from("sources")
    .select(SOURCE_WARD_PROFILE_SELECT)
    .eq("source_type", ALDERMAN_SOURCE_TYPE)
    .eq("ward_number", String(wardNumber))
    .order("id", { ascending: false });

  if (error) {
    throw new Error(
      `Failed to fetch sources for ward ${wardNumber}: ${error.message}`,
    );
  }
  return (data ?? []) as unknown as WardProfileSource[];
}

/** Fetches every alder source for the ward directory, in one query. */
export async function fetchWardDirectorySources(
  supabase: SupabaseClient,
): Promise<WardDirectorySource[]> {
  const { data, error } = await supabase
    .from("sources")
    .select(SOURCE_WARD_DIRECTORY_SELECT)
    .eq("source_type", ALDERMAN_SOURCE_TYPE)
    .order("id", { ascending: false });

  if (error) {
    throw new Error(`Failed to fetch ward directory sources: ${error.message}`);
  }
  return (data ?? []) as unknown as WardDirectorySource[];
}

export interface WardNewsletterPage {
  /** Newsletters on the requested page, newest first. */
  newsletters: NewsletterCardRow[];
  /** Total newsletters across all of the ward's sources. */
  totalCount: number;
  /** Received date of the ward's newest newsletter, regardless of page. */
  latestReceivedDate: string | null;
}

export const EMPTY_WARD_NEWSLETTER_PAGE: WardNewsletterPage = {
  newsletters: [],
  totalCount: 0,
  latestReceivedDate: null,
};

/**
 * Fetches one page of newsletters sent by any of `sourceIds`, plus the total
 * count and latest received date. The three queries run in parallel and the
 * listing selects card columns only (no newsletter bodies).
 */
export async function fetchWardNewsletterPage(
  supabase: SupabaseClient,
  sourceIds: readonly number[],
  page: number,
): Promise<WardNewsletterPage> {
  if (sourceIds.length === 0) {
    return EMPTY_WARD_NEWSLETTER_PAGE;
  }

  const { from, to } = getPageRange(page);
  const sourceIdList = [...sourceIds];
  const newslettersTable = () => supabase.from("newsletters");

  const [listResult, countResult, latestResult] = await Promise.all([
    newslettersTable()
      .select(buildNewsletterCardSelect({ filtersOnSource: false }))
      .in("source_id", sourceIdList)
      .order(RECEIVED_DATE_COLUMN, { ascending: false })
      .range(from, to),
    newslettersTable()
      .select(buildNewsletterCountSelect({ filtersOnSource: false }), {
        count: "exact",
        head: true,
      })
      .in("source_id", sourceIdList),
    newslettersTable()
      .select(RECEIVED_DATE_COLUMN)
      .in("source_id", sourceIdList)
      .order(RECEIVED_DATE_COLUMN, { ascending: false })
      .limit(1),
  ]);

  const failedResult = [listResult, countResult, latestResult].find(
    (result) => result.error,
  );
  if (failedResult?.error) {
    throw new Error(
      `Failed to fetch newsletters for sources ${sourceIdList.join(", ")}: ${failedResult.error.message}`,
    );
  }

  const latestRows = (latestResult.data ?? []) as { received_date: string }[];
  return {
    newsletters: (listResult.data ?? []) as unknown as NewsletterCardRow[],
    totalCount: countResult.count ?? 0,
    latestReceivedDate: latestRows[0]?.received_date ?? null,
  };
}
