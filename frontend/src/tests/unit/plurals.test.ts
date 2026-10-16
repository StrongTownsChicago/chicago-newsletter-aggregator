// The TypeScript fold must agree with the backend's (analytics/plurals.py), so
// both are tested against the same case list.
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { foldPlural, foldTerm } from "../../lib/analytics/plurals";

const SHARED_CASES_PATH = path.resolve(__dirname, "../../../../backend/tests/fixtures/plural_fold_cases.json");

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
