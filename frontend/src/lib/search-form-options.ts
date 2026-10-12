import type { Source } from "./supabase";

/**
 * Derives the search form's dropdown options from a single fetch of the
 * sources table (see `SEARCH_SOURCE_COLUMNS`).
 */

/** Source columns needed to build the search form dropdowns. */
export const SEARCH_SOURCE_COLUMNS = [
  "id",
  "name",
  "ward_number",
  "source_type",
] as const satisfies readonly (keyof Source)[];

export type SearchSourceRow = Pick<
  Source,
  (typeof SEARCH_SOURCE_COLUMNS)[number]
>;

export interface SourceOption {
  id: number;
  label: string;
}

const wardSortKey = (wardNumber: string | null): number =>
  wardNumber ? Number.parseInt(wardNumber, 10) : Number.POSITIVE_INFINITY;

const compareSources = (a: SearchSourceRow, b: SearchSourceRow): number =>
  wardSortKey(a.ward_number) - wardSortKey(b.ward_number) ||
  a.name.localeCompare(b.name);

const formatSourceLabel = ({ name, ward_number }: SearchSourceRow): string =>
  ward_number ? `Ward ${ward_number} – ${name}` : name;

/** Source dropdown options: ward offices in ward order, then other sources by name. */
export function buildSourceOptions(sources: SearchSourceRow[]): SourceOption[] {
  return [...sources]
    .sort(compareSources)
    .map((source) => ({ id: source.id, label: formatSourceLabel(source) }));
}

/** Distinct ward numbers of sources that have one, in numeric order. */
export function extractWardNumbers(sources: SearchSourceRow[]): string[] {
  const wards = sources
    .map((source) => source.ward_number)
    .filter((ward): ward is string => Boolean(ward));
  return [...new Set(wards)].sort((a, b) => wardSortKey(a) - wardSortKey(b));
}

/** Distinct source types, alphabetically. */
export function extractSourceTypes(sources: SearchSourceRow[]): string[] {
  return [...new Set(sources.map((source) => source.source_type))].sort();
}
