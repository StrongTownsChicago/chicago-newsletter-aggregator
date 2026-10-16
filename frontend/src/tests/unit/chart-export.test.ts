import { describe, expect, it } from "vitest";
import {
  buildExportFileName,
  buildExportFooter,
  buildExportHeader,
  chooseExportScale,
  EXPORT_CAVEAT,
  wrapText,
  type ChartExportContext,
} from "../../lib/analytics/charts/export";

const context: ChartExportContext = {
  title: "Civic calendar",
  scope: "Jan 2026 – Oct 2026 · All wards",
  caption: "Numbers are wards out of the wards that sent newsletters that month.",
  dataAsOf: "Data as of Oct 14, 2026, 9:00 PM from 2,215 newsletters.",
  siteName: "Chicago Alderman Newsletter Tracker",
  pageUrl: "https://example.org/analytics?topic=budget_taxes",
};

/** One unit of width per character, so wrapping is easy to reason about. */
const measureByLength = (text: string) => text.length;

describe("buildExportHeader and buildExportFooter", () => {
  it("embed the title, window, denominator, data date, caveat, site and link", () => {
    const text = [...buildExportHeader(context), ...buildExportFooter(context)].map((line) => line.text).join("\n");
    for (const part of [
      context.title,
      context.scope,
      context.caption,
      context.dataAsOf,
      EXPORT_CAVEAT,
      context.siteName,
      context.pageUrl,
    ]) {
      expect(text).toContain(part);
    }
  });

  it("styles the title as a title and skips an empty caption", () => {
    const header = buildExportHeader({ ...context, caption: "  " });
    expect(header[0]).toEqual({ text: context.title, role: "title" });
    expect(header).toHaveLength(2);
  });

  it("states the coverage caveat once, briefly", () => {
    expect(EXPORT_CAVEAT).toMatch(/not every ward is covered/);
    expect(EXPORT_CAVEAT.split(".").filter(Boolean)).toHaveLength(1);
    expect(EXPORT_CAVEAT).not.toMatch(/\balders?\b/i);
  });
});

describe("wrapText", () => {
  it("breaks at word boundaries within the width", () => {
    expect(wrapText("one two three four", 9, measureByLength)).toEqual(["one two", "three", "four"]);
  });

  it("breaks a word longer than the line by characters", () => {
    expect(wrapText("https://example.org/long", 10, measureByLength)).toEqual(["https://ex", "ample.org/", "long"]);
  });

  it("returns no lines for blank text", () => {
    expect(wrapText("   ", 10, measureByLength)).toEqual([]);
  });
});

describe("buildExportFileName", () => {
  const date = new Date("2026-10-14T12:00:00Z");

  it("slugs the title and appends the date", () => {
    expect(buildExportFileName('Term explorer: "bike lanes"', date)).toBe("term-explorer-bike-lanes-2026-10-14.png");
  });

  it("falls back to a generic name", () => {
    expect(buildExportFileName("¿?", date)).toBe("chart-2026-10-14.png");
  });

  it("keeps long titles short", () => {
    expect(buildExportFileName("word ".repeat(40), date).length).toBeLessThanOrEqual(60 + "-2026-10-14.png".length);
  });
});

describe("chooseExportScale", () => {
  it("doubles ordinary charts", () => {
    expect(chooseExportScale(1000, 600)).toBe(2);
  });

  it("scales very large charts down to fit browser canvas limits", () => {
    const scale = chooseExportScale(3000, 4000);
    expect(scale).toBeLessThan(2);
    expect(3000 * scale * 4000 * scale).toBeLessThanOrEqual(16_777_216 + 1);
    expect(20_000 * chooseExportScale(20_000, 300)).toBeLessThanOrEqual(16_384);
  });
});
