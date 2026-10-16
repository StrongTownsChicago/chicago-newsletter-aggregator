// @vitest-environment node
import path from "node:path";
import { ESLint, type Linter } from "eslint";
import { describe, expect, it } from "vitest";
import eslintConfig from "../../../eslint.config.js";

const FRONTEND_ROOT = path.resolve(__dirname, "../../..");
const DEFAULT_MAX_LINES = 400;

// Same numbers as the max-lines ceilings in eslint.config.js. Raising one is a
// two-place change on purpose; lower both when a file shrinks.
const ADOPTED_CEILINGS: Record<string, number> = {
  "src/scripts/analytics-dashboard.ts": 1170,
  "src/lib/analytics-charts.ts": 851,
  "src/pages/preferences.astro": 785,
  "src/lib/analytics.ts": 635,
  "src/tests/unit/analytics.test.ts": 488,
};

interface MaxLinesBlock {
  files: string[];
  max: number;
}

function collectMaxLinesBlocks(configs: Linter.Config[]): MaxLinesBlock[] {
  return configs.flatMap((config) => {
    const rule = config.rules?.["max-lines"];
    if (!Array.isArray(rule)) return [];
    const options = rule[1] as { max: number };
    const files = (config.files ?? []).flat().map(String);
    return [{ files, max: options.max }];
  });
}

const blocks = collectMaxLinesBlocks(eslintConfig as Linter.Config[]);
const ceilingBlocks = blocks.filter((block) => block.max !== DEFAULT_MAX_LINES);

describe("max-lines budgets", () => {
  it("keeps the default cap", () => {
    expect(blocks.some((block) => block.max === DEFAULT_MAX_LINES)).toBe(true);
  });

  it("has exactly the adopted ceilings, none raised", () => {
    const configured = Object.fromEntries(
      ceilingBlocks.map((block) => [block.files.join(","), block.max]),
    );
    expect(Object.keys(configured).sort()).toEqual(Object.keys(ADOPTED_CEILINGS).sort());
    for (const [file, max] of Object.entries(configured)) {
      expect(max, file).toBeLessThanOrEqual(ADOPTED_CEILINGS[file]);
    }
  });

  it("has no slack: each ceiling equals the file's measured size", async () => {
    const eslint = new ESLint({
      cwd: FRONTEND_ROOT,
      ruleFilter: ({ ruleId }) => ruleId === "max-lines",
      overrideConfig: {
        rules: { "max-lines": ["error", { max: 1, skipBlankLines: true, skipComments: true }] },
      },
    });
    const files = Object.keys(ADOPTED_CEILINGS);
    const results = await eslint.lintFiles(files);
    const measured = Object.fromEntries(
      results.map((result) => {
        const file = path.relative(FRONTEND_ROOT, result.filePath).split(path.sep).join("/");
        // Several results per .astro file (its <script> blocks); the file itself is the largest.
        const counts = result.messages
          .filter((message) => message.ruleId === "max-lines")
          .map((message) => Number(/\((\d+)\)/.exec(message.message)?.[1]));
        return [file, Math.max(...counts)];
      }),
    );
    for (const file of files) {
      expect(measured[file], `${file}: lower its ceiling to the measured size`).toBe(
        ADOPTED_CEILINGS[file],
      );
    }
  }, 60_000);
});
