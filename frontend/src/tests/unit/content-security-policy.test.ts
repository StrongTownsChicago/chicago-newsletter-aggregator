import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { CONTENT_SECURITY_POLICY, CONTENT_SECURITY_POLICY_HEADER } from "../../lib/content-security-policy";
import { headersForPattern } from "../headers-rules";

const HEADERS_FILE = readFileSync(path.resolve(__dirname, "../../../public/_headers"), "utf-8");
const SOURCE_DIRECTORY = path.resolve(__dirname, "../..");

/** Every .astro file under src/, relative to it. */
const ASTRO_FILES = readdirSync(SOURCE_DIRECTORY, { recursive: true, encoding: "utf-8" }).filter((file) =>
  file.endsWith(".astro"),
);

/** Each directive's sources, keyed by directive name. */
function parsePolicy(policy: string): Map<string, string[]> {
  return new Map(
    policy.split(";").map((directive) => {
      const [name, ...sources] = directive.trim().split(/\s+/);
      return [name, sources];
    }),
  );
}

describe("Content-Security-Policy", () => {
  const directives = parsePolicy(CONTENT_SECURITY_POLICY);

  it("is enforced, not report-only", () => {
    expect(CONTENT_SECURITY_POLICY_HEADER).toBe("Content-Security-Policy");
  });

  it("is served on static files exactly as the middleware sends it", () => {
    expect(headersForPattern(HEADERS_FILE, "/*")).toContain(
      `${CONTENT_SECURITY_POLICY_HEADER}: ${CONTENT_SECURITY_POLICY}`,
    );
  });

  it("runs only the site's own script files and Cloudflare's analytics beacon", () => {
    expect(directives.get("script-src")).toEqual(["'self'", "https://static.cloudflareinsights.com"]);
    expect(directives.get("object-src")).toEqual(["'none'"]);
    expect(directives.get("base-uri")).toEqual(["'self'"]);
  });

  it("never allows inline or evaluated scripts", () => {
    for (const [name, sources] of directives) {
      if (name === "style-src") continue;
      expect(sources, name).not.toContain("'unsafe-inline'");
      expect(sources, name).not.toContain("'unsafe-eval'");
    }
  });

  it("keeps the site out of frames and frames out of the site", () => {
    expect(directives.get("frame-src")).toEqual(["'none'"]);
    expect(directives.get("frame-ancestors")).toEqual(["'none'"]);
  });

  // A page's own handlers would be blocked like a newsletter's: wire them in a <script>.
  it.each(ASTRO_FILES)("%s has no inline event handlers or javascript: URLs", (file) => {
    const source = readFileSync(path.join(SOURCE_DIRECTORY, file), "utf-8");
    expect(source).not.toMatch(/<[^>]*\son[a-z]+\s*=/i);
    expect(source).not.toMatch(/javascript:/i);
  });
});
