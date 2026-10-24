import { describe, expect, it } from "vitest";
import fc from "fast-check";
import { foldPlural, foldTerm } from "../../lib/analytics/plurals";

const PROPERTY_RUNS = { numRuns: 500 };

/** Words weighted toward the endings the rules look at, plus non-ASCII letters and non-letters. */
const word = fc.oneof(
  fc.stringMatching(/^[a-z]{0,7}(s|es|ies|sses|xes|ches|shes|ss|us|is|ys)?s?$/),
  fc.stringMatching(/^[a-zéñüß]{0,6}s$/),
  fc.constantFrom("news", "series", "buses", "busses", "bus", "ties", "species", "illinois"),
  fc.string({ maxLength: 8 }),
);

describe("foldPlural properties", () => {
  it("is idempotent: a folded word folds to itself", () => {
    fc.assert(
      fc.property(word, (written) => {
        const folded = foldPlural(written);
        expect(foldPlural(folded)).toBe(folded);
      }),
      PROPERTY_RUNS,
    );
  });

  it("leaves words not ending in s unchanged and never lengthens a word", () => {
    fc.assert(
      fc.property(word, (written) => {
        const folded = foldPlural(written);
        if (!written.endsWith("s")) expect(folded).toBe(written);
        expect(folded.length).toBeLessThanOrEqual(written.length);
      }),
      PROPERTY_RUNS,
    );
  });

  it("only removes an ending, or turns -ies into -y", () => {
    fc.assert(
      fc.property(word, (written) => {
        const folded = foldPlural(written);
        const isPrefix = written.startsWith(folded);
        const isIesToY = written.endsWith("ies") && folded === `${written.slice(0, -"ies".length)}y`;
        expect(isPrefix || isIesToY).toBe(true);
      }),
      PROPERTY_RUNS,
    );
  });
});

describe("foldTerm properties", () => {
  it("is idempotent and folds each word on its own", () => {
    fc.assert(
      fc.property(fc.array(word, { minLength: 1, maxLength: 2 }), (words) => {
        const term = words.join(" ");
        const folded = foldTerm(term);
        expect(foldTerm(folded)).toBe(folded);
        expect(folded).toBe(term.split(" ").map(foldPlural).join(" "));
      }),
      PROPERTY_RUNS,
    );
  });
});
