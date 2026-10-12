/**
 * Turns a snake_case identifier (topic slug, source type) into a
 * human-readable Title Case label, e.g. "bike_lanes" -> "Bike Lanes".
 */
export function humanizeIdentifier(identifier: string): string {
  return identifier
    .split("_")
    .filter(Boolean)
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(" ");
}
