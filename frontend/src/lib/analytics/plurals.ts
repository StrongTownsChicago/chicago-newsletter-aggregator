// TypeScript port of the backend's plural folding (backend/analytics/plurals.py).
// The term index names each merged singular/plural group by its most common
// written form, so the term explorer folds a query the same way to find the
// group whichever form the reader typed. Both implementations are checked
// against backend/tests/fixtures/plural_fold_cases.json; change them together.

/** Shorter words ending in "s" are rarely plurals ("bus", "gas", "yes", "its"). */
const MIN_FOLDABLE_LENGTH = 4;
/** Endings whose final "s" is not a plural marker: "address", "bus", "illinois". */
const NON_PLURAL_ENDINGS = ["ss", "us", "is"];
/** Plurals formed with "es" after a sibilant: "taxes", "churches", "dishes". */
const SIBILANT_PLURAL_ENDINGS = ["sses", "xes", "ches", "shes"];
/** Words ending in "s" whose stripped form is a different, common word. */
const NON_PLURAL_WORDS: ReadonlySet<string> = new Set([
  "news",
  "means",
  "goods",
  "economics",
  "politics",
  "ethics",
  "athletics",
  "physics",
  "series",
  "species",
]);
/** Plurals the rules would get wrong. */
const IRREGULAR_PLURALS: ReadonlyMap<string, string> = new Map([
  ["buses", "bus"],
  ["busses", "bus"],
]);
const LETTERS_ONLY_PATTERN = /^\p{L}+$/u;

/** Length in code points, matching Python's len(). */
function codePointLength(word: string): number {
  return [...word].length;
}

/** The singular form used to count a word; non-plurals come back unchanged. */
export function foldPlural(word: string): string {
  const irregular = IRREGULAR_PLURALS.get(word);
  if (irregular !== undefined) return irregular;
  if (
    codePointLength(word) < MIN_FOLDABLE_LENGTH ||
    !LETTERS_ONLY_PATTERN.test(word) ||
    !word.endsWith("s") ||
    NON_PLURAL_ENDINGS.some((ending) => word.endsWith(ending)) ||
    NON_PLURAL_WORDS.has(word)
  ) {
    return word;
  }
  if (word.endsWith("ies") && codePointLength(word) > MIN_FOLDABLE_LENGTH) {
    return `${word.slice(0, -"ies".length)}y`;
  }
  if (SIBILANT_PLURAL_ENDINGS.some((ending) => word.endsWith(ending))) {
    return word.slice(0, -"es".length);
  }
  return word.slice(0, -"s".length);
}

/** Fold every word of a unigram or bigram term. */
export function foldTerm(term: string): string {
  return term.split(" ").map(foldPlural).join(" ");
}
