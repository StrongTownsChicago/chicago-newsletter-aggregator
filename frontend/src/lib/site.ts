import { SEARCH_PATH } from "./search-filters";
import { WARD_DIRECTORY_PATH } from "./wards";

/** One-line explanation of the site shown under the site name in the header. */
export const SITE_TAGLINE =
  "A searchable database tracking what aldermen communicate to their wards.";

export const STRONG_TOWNS_CHICAGO_NAME = "Strong Towns Chicago";
export const STRONG_TOWNS_CHICAGO_URL = "https://www.strongtownschicago.org/";
/** Footer credit text that precedes the linked organization name. */
export const FOOTER_CREDIT_PREFIX = "Built for";
export const SOURCE_CODE_URL =
  "https://github.com/StrongTownsChicago/chicago-newsletter-aggregator";
export const SOURCE_CODE_LINK_LABEL = "Source code on GitHub";

export const HOME_PATH = "/";
export const PREFERENCES_PATH = "/preferences";
export const REPORTS_INDEX_PATH = "/reports";
export const ANALYTICS_PATH = "/analytics";
const WARD_PROFILE_PATH_PREFIX = "/ward";

export interface NavItem {
  label: string;
  href: string;
  /** Paths that mark this item as current; each also matches its sub-paths. */
  activePathPrefixes: readonly string[];
}

const PUBLIC_NAV_ITEMS: readonly NavItem[] = [
  { label: "Recent", href: HOME_PATH, activePathPrefixes: [HOME_PATH] },
  { label: "Search", href: SEARCH_PATH, activePathPrefixes: [SEARCH_PATH] },
  {
    label: "Wards",
    href: WARD_DIRECTORY_PATH,
    activePathPrefixes: [WARD_DIRECTORY_PATH, WARD_PROFILE_PATH_PREFIX],
  },
  { label: "Analytics", href: ANALYTICS_PATH, activePathPrefixes: [ANALYTICS_PATH] },
];

const PREFERENCES_NAV_ITEM: NavItem = {
  label: "Preferences",
  href: PREFERENCES_PATH,
  activePathPrefixes: [PREFERENCES_PATH],
};

/**
 * Returns the primary navigation items. Preferences is only listed when the
 * visitor can use it (notifications enabled and signed in).
 */
export function buildPrimaryNavItems(options: {
  showPreferences: boolean;
}): NavItem[] {
  return options.showPreferences
    ? [...PUBLIC_NAV_ITEMS, PREFERENCES_NAV_ITEM]
    : [...PUBLIC_NAV_ITEMS];
}

function stripTrailingSlashes(pathname: string): string {
  const stripped = pathname.replace(/\/+$/, "");
  return stripped || HOME_PATH;
}

function pathMatchesPrefix(pathname: string, prefix: string): boolean {
  if (prefix === HOME_PATH) {
    return pathname === HOME_PATH;
  }
  return pathname === prefix || pathname.startsWith(`${prefix}/`);
}

/**
 * Returns true when `pathname` belongs to the section `item` links to.
 * The home item only matches the root, so it isn't active on every page;
 * other items match their own path and anything beneath it
 * (e.g. Wards is active on both `/wards` and `/ward/12`).
 */
export function isNavItemActive(item: NavItem, pathname: string): boolean {
  const normalizedPath = stripTrailingSlashes(pathname);
  return item.activePathPrefixes.some((prefix) =>
    pathMatchesPrefix(normalizedPath, prefix),
  );
}
