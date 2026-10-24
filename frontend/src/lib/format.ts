/**
 * Turns a snake_case identifier (e.g. a source type) into a human-readable
 * Title Case label, e.g. "alderman" -> "Alderman". Topics use
 * `formatTopicLabel` in `topics.ts` instead.
 */
export function humanizeIdentifier(identifier: string): string {
  return identifier
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
