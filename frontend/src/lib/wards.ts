/** Chicago has had 50 wards since 1923; ward numbers are stable while alders change. */
export const FIRST_WARD = 1;
export const LAST_WARD = 50;

/** `sources.source_type` value for alders. */
export const ALDERMAN_SOURCE_TYPE = "alderman";

/** Every Chicago ward number, in order. */
export const ALL_WARD_NUMBERS: readonly number[] = Array.from(
  { length: LAST_WARD - FIRST_WARD + 1 },
  (_, index) => FIRST_WARD + index,
);

/** Canonical ward number form: no leading zeros, no sign, no whitespace. */
const CANONICAL_WARD_PATTERN = /^[1-9]\d?$/;

/**
 * Parses the `[ward]` route parameter. Returns the ward number when the
 * parameter is a canonical integer between FIRST_WARD and LAST_WARD,
 * otherwise null (the page should respond 404). Non-canonical forms such as
 * "05" are rejected so each ward has exactly one URL.
 */
export function parseWardParam(rawWard: string | undefined): number | null {
  if (!rawWard || !CANONICAL_WARD_PATTERN.test(rawWard)) {
    return null;
  }
  const wardNumber = Number(rawWard);
  return wardNumber >= FIRST_WARD && wardNumber <= LAST_WARD
    ? wardNumber
    : null;
}

/** Path of the ward directory page. */
export const WARD_DIRECTORY_PATH = "/wards";

/** Path of the page for a ward. */
export function buildWardPath(wardNumber: number | string): string {
  return `/ward/${wardNumber}`;
}

/** Path of the search page pre-filtered to a ward. */
export function buildWardSearchPath(wardNumber: number): string {
  return `/search?${new URLSearchParams({ ward: String(wardNumber) })}`;
}

/**
 * Joins alder names for display: "A", "A and B", "A, B, and C".
 * Returns null when there are no names.
 */
export function formatAlderNames(names: readonly string[]): string | null {
  if (names.length === 0) {
    return null;
  }
  if (names.length <= 2) {
    return names.join(" and ");
  }
  return `${names.slice(0, -1).join(", ")}, and ${names[names.length - 1]}`;
}

export interface WardDirectoryEntry<TSource> {
  wardNumber: number;
  sources: TSource[];
}

/**
 * Groups alder sources by ward and returns one entry per Chicago ward, in
 * ward order. Wards without a matching source get an empty `sources` list;
 * sources whose ward_number is missing or outside 1-50 are ignored.
 */
export function buildWardDirectory<
  TSource extends { ward_number: string | null },
>(sources: readonly TSource[]): WardDirectoryEntry<TSource>[] {
  const sourcesByWard = new Map<number, TSource[]>();
  for (const source of sources) {
    const wardNumber = parseWardParam(source.ward_number?.trim());
    if (wardNumber === null) {
      continue;
    }
    sourcesByWard.set(wardNumber, [
      ...(sourcesByWard.get(wardNumber) ?? []),
      source,
    ]);
  }
  return ALL_WARD_NUMBERS.map((wardNumber) => ({
    wardNumber,
    sources: sourcesByWard.get(wardNumber) ?? [],
  }));
}

export type WardContactKind = "website" | "signup" | "phone" | "email";

export interface WardContactLink {
  kind: WardContactKind;
  label: string;
  href: string;
  /** True for links that leave the site and should open in a new tab. */
  isExternal: boolean;
}

export interface WardContactSource {
  website: string | null;
  signup_url: string | null;
  phone: string | null;
  email_address: string | null;
}

const WEB_PROTOCOLS = new Set(["http:", "https:"]);

/** Returns the URL when it is an absolute http(s) URL, otherwise null. */
function toSafeWebUrl(rawUrl: string | null): string | null {
  const trimmed = rawUrl?.trim();
  if (!trimmed) {
    return null;
  }
  try {
    return WEB_PROTOCOLS.has(new URL(trimmed).protocol) ? trimmed : null;
  } catch {
    return null;
  }
}

/** Builds a `tel:` href from a display phone number, or null if it has no digits. */
function toTelHref(rawPhone: string | null): string | null {
  const digits = rawPhone?.replace(/\D/g, "");
  return digits ? `tel:${digits}` : null;
}

/**
 * Builds the public contact links shown in a ward page header, in display
 * order. Missing fields are omitted, and web links are limited to http(s)
 * URLs so stored data cannot inject other URL schemes.
 */
export function buildWardContactLinks(
  source: WardContactSource,
): WardContactLink[] {
  const website = toSafeWebUrl(source.website);
  const signupUrl = toSafeWebUrl(source.signup_url);
  const phone = source.phone?.trim();
  const telHref = toTelHref(source.phone);
  const email = source.email_address?.trim();

  const links: (WardContactLink | null)[] = [
    website
      ? { kind: "website", label: "Website", href: website, isExternal: true }
      : null,
    signupUrl
      ? {
          kind: "signup",
          label: "Newsletter signup",
          href: signupUrl,
          isExternal: true,
        }
      : null,
    phone && telHref
      ? { kind: "phone", label: phone, href: telHref, isExternal: false }
      : null,
    email
      ? {
          kind: "email",
          label: email,
          href: `mailto:${email}`,
          isExternal: false,
        }
      : null,
  ];
  return links.filter((link): link is WardContactLink => link !== null);
}

