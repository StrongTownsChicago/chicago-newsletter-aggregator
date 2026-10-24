// The TypeScript fold must agree with the backend's (analytics/plurals.py), so
// both are tested against the same case list.
import { existsSync, readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { foldPlural, foldTerm } from "../../lib/analytics/plurals";

const SHARED_CASES_FILE = "backend/tests/fixtures/plural_fold_cases.json";

/** Searches upward, so the test also runs from Stryker's sandbox copy in frontend/.stryker-tmp/. */
function findSharedCasesPath(directory: string): string {
  const candidate = path.join(directory, SHARED_CASES_FILE);
  if (existsSync(candidate)) return candidate;
  const parent = path.dirname(directory);
  if (parent === directory) throw new Error(`${SHARED_CASES_FILE} not found above ${__dirname}`);
  return findSharedCasesPath(parent);
}

const SHARED_CASES_PATH = findSharedCasesPath(__dirname);

interface SharedFoldCases {
  words: [string, string][];
  terms: [string, string][];
}

const sharedCases = JSON.parse(readFileSync(SHARED_CASES_PATH, "utf-8")) as SharedFoldCases;

describe("foldPlural", () => {
  it.each(sharedCases.words)("folds %s to %s, like the backend", (word, folded) => {
    expect(foldPlural(word)).toBe(folded);
  });
});

describe("foldTerm", () => {
  it.each(sharedCases.terms)("folds %s to %s, like the backend", (term, folded) => {
    expect(foldTerm(term)).toBe(folded);
  });
});
