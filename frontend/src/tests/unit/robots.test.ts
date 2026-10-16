import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { disallowRulesFor, isPathDisallowed } from "../robots-rules";

const robotsTxt = readFileSync(path.resolve(__dirname, "../../../public/robots.txt"), "utf-8");

const blocks = (userAgent: string, pagePath: string) =>
  isPathDisallowed(disallowRulesFor(robotsTxt, userAgent), pagePath);

describe("robots.txt", () => {
  it.each(["GPTBot", "ClaudeBot", "CCBot", "Google-Extended", "PerplexityBot", "Bytespider"])(
    "blocks the AI crawler %s from the whole site",
    (userAgent) => {
      expect(blocks(userAgent, "/")).toBe(true);
      expect(blocks(userAgent, "/newsletter/some-id")).toBe(true);
    },
  );

  it.each(["Googlebot", "Bingbot", "ChatGPT-User", "Claude-User", "Perplexity-User"])(
    "lets %s fetch public pages",
    (userAgent) => {
    expect(blocks(userAgent, "/")).toBe(false);
    expect(blocks(userAgent, "/newsletter/some-id")).toBe(false);
    expect(blocks(userAgent, "/ward/1")).toBe(false);
    },
  );

  it("keeps account pages and the API out for every crawler", () => {
    expect(blocks("Googlebot", "/preferences")).toBe(true);
    expect(blocks("Googlebot", "/api/search-timeline")).toBe(true);
  });
});

describe("disallowRulesFor", () => {
  const sample = ["User-agent: *", "Disallow: /private", "", "User-agent: BotA", "User-agent: BotB", "Disallow: /"].join(
    "\n",
  );

  it("applies a group's rules to every agent it names", () => {
    expect(disallowRulesFor(sample, "BotA")).toEqual(["/"]);
    expect(disallowRulesFor(sample, "botb")).toEqual(["/"]);
  });

  it("falls back to the * group for unnamed agents", () => {
    expect(disallowRulesFor(sample, "Googlebot")).toEqual(["/private"]);
  });
});
