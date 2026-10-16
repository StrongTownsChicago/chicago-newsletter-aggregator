// Checks the static files that publish the analytics data: the committed JSON
// must exist for every file the page fetches, and it must stay unlisted.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { ANALYTICS_DATA_BASE_PATH, analyticsFileUrl, CORE_ANALYTICS_FILES } from "../../lib/analytics-data";
import { disallowRulesFor, isPathDisallowed } from "../robots-rules";

const PUBLIC_DIRECTORY = path.resolve(__dirname, "../../../public");

function readPublicFile(relativePath: string): string {
  return readFileSync(`${PUBLIC_DIRECTORY}/${relativePath}`, "utf-8");
}

/** The header lines of the `_headers` rule for exactly this path pattern. */
function headersForPattern(headersFile: string, pattern: string): string[] {
  const lines = headersFile.split(/\r?\n/);
  const start = lines.indexOf(pattern);
  if (start === -1) return [];
  const rule: string[] = [];
  for (const line of lines.slice(start + 1)) {
    if (!/^\s+\S/.test(line)) break;
    rule.push(line.trim());
  }
  return rule;
}

describe("published analytics data", () => {
  it("commits every file the page fetches", () => {
    for (const file of [...CORE_ANALYTICS_FILES, "terms" as const]) {
      expect(existsSync(`${PUBLIC_DIRECTORY}${analyticsFileUrl(file)}`), analyticsFileUrl(file)).toBe(true);
    }
  });

  it("serves the data files as noindex and revalidated on every load", () => {
    const rule = headersForPattern(readPublicFile("_headers"), `${ANALYTICS_DATA_BASE_PATH}/*`);
    expect(rule).toContain("X-Robots-Tag: noindex");
    expect(rule).toContain("Cache-Control: no-cache");
  });

  it("lets crawlers fetch the dashboard and its data", () => {
    const disallowed = disallowRulesFor(readPublicFile("robots.txt"), "Googlebot");
    expect(isPathDisallowed(disallowed, "/analytics")).toBe(false);
    expect(isPathDisallowed(disallowed, `${ANALYTICS_DATA_BASE_PATH}/terms.json`)).toBe(false);
  });
});
