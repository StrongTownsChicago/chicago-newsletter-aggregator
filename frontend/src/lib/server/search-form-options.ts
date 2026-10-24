import type { Source } from "../supabase";

/**
 * Derives the search form's ward options and source labels from a single
 * fetch of the sources table (see `SEARCH_SOURCE_COLUMNS`).
 */

/** Source columns needed for the search form. */
export const SEARCH_SOURCE_COLUMNS = [
  "id",
  "name",
  "ward_number",
] as const satisfies readonly (keyof Source)[];

export type SearchSourceRow = Pick<
  Source,
  (typeof SEARCH_SOURCE_COLUMNS)[number]
>;

export interface WardOption {
  ward: string;
  /** "Ward 40 – Andre Vasquez"; several offices in one ward are joined. */
  label: string;
}

const wardSortKey = (wardNumber: string): number => Number.parseInt(wardNumber, 10);

/**
 * Ward dropdown options in numeric order, each labelled with the names of the
 * ward's sources so one dropdown serves both "my ward" and "my alderman".
 */
export function buildWardOptions(sources: SearchSourceRow[]): WardOption[] {
  const namesByWard = new Map<string, string[]>();
  for (const { ward_number, name } of sources) {
    if (!ward_number) continue;
    namesByWard.set(ward_number, [...(namesByWard.get(ward_number) ?? []), name]);
  }
  return [...namesByWard]
    .sort(([a], [b]) => wardSortKey(a) - wardSortKey(b))
    .map(([ward, names]) => ({
      ward,
      label: `Ward ${ward} – ${[...names].sort((a, b) => a.localeCompare(b)).join(", ")}`,
    }));
}

/** Source names by id, for labelling a source filter carried in the URL. */
export function buildSourceNames(sources: SearchSourceRow[]): Map<number, string> {
  return new Map(sources.map(({ id, name }) => [id, name]));
}
