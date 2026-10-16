// @vitest-environment node
import { readdirSync, readFileSync } from "node:fs";
import path from "node:path";
import { ESLint, type Linter } from "eslint";
import { describe, expect, it } from "vitest";
import eslintConfig from "../../../eslint.config.js";

const FRONTEND_ROOT = path.resolve(__dirname, "../../..");
const DEFAULT_MAX_LINES = 400;

// Per-file max-lines ceilings in eslint.config.js, repeated here. Every file is
// under the default cap, so there are none; adding one is a two-place change on purpose.
const ADOPTED_CEILINGS: Record<string, number> = {};

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

/** Every file the cap covers, relative to the frontend root with forward slashes. */
function listCappedFiles(): string[] {
  const roots: [string, RegExp][] = [
    ["src", /\.(ts|astro)$/],
    ["e2e", /\.ts$/],
  ];
  return roots.flatMap(([root, pattern]) =>
    readdirSync(path.join(FRONTEND_ROOT, root), { recursive: true, encoding: "utf8" })
      .map((file) => `${root}/${file.split(path.sep).join("/")}`)
      .filter((file) => pattern.test(file)),
  );
}

// An eslint-disable comment naming max-lines or no rule at all, or an inline `eslint max-lines:` setting.
const INLINE_MAX_LINES_OVERRIDE =
  /(?:\/\/|\/\*)\s*(?:eslint-disable(?:-next-line|-line)?(?:\s*(?:\*\/|--|$)|[^\n]*\bmax-lines\b)|eslint\s[^\n]*\bmax-lines\b)/m;

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

  // Catches what the block check above can't see: "off", a numeric severity, or a later block.
  it("applies the cap, or the file's adopted ceiling, to every file", async () => {
    const eslint = new ESLint({ cwd: FRONTEND_ROOT });
    for (const file of listCappedFiles()) {
      const config = (await eslint.calculateConfigForFile(file)) as Linter.Config;
      expect(config.rules?.["max-lines"], file).toEqual([
        2,
        { max: ADOPTED_CEILINGS[file] ?? DEFAULT_MAX_LINES, skipBlankLines: true, skipComments: true },
      ]);
    }
  });

  it("has no inline max-lines overrides", () => {
    const overridden = listCappedFiles().filter((file) =>
      INLINE_MAX_LINES_OVERRIDE.test(readFileSync(path.join(FRONTEND_ROOT, file), "utf8")),
    );
    expect(overridden).toEqual([]);
  });

  it.runIf(Object.keys(ADOPTED_CEILINGS).length > 0)("has no slack: each ceiling equals the file's measured size", async () => {
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
