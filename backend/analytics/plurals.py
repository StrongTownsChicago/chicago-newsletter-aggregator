"""Light, rule-based plural folding so "bike lane" and "bike lanes" count as one term.

The rules are a conservative English "S-stemmer" (Harman, 1991): they only
remove plural endings, never other suffixes, so a merge is easy to predict and
explain. Words are folded for counting only; each merged term is displayed in
its most common written form (see `choose_display_forms`).
"""

from collections import defaultdict
from collections.abc import Mapping

# Shorter words ending in "s" are rarely plurals ("bus", "gas", "yes", "its").
MIN_FOLDABLE_LENGTH = 4
# Endings whose final "s" is not a plural marker: "address", "bus", "campus",
# "illinois", "crisis".
NON_PLURAL_ENDINGS = ("ss", "us", "is")
# Plurals formed with "es" after a sibilant: "taxes", "churches", "dishes".
SIBILANT_PLURAL_ENDINGS = ("sses", "xes", "ches", "shes")
# Words ending in "s" whose stripped form is a different, common word.
NON_PLURAL_WORDS: frozenset[str] = frozenset(
    """
    news means goods economics politics ethics athletics physics series species
    """.split()
)
# Plurals the rules would get wrong.
IRREGULAR_PLURALS: Mapping[str, str] = {"buses": "bus", "busses": "bus"}


def fold_plural(word: str) -> str:
    """Return the singular form used to count a word; non-plurals come back unchanged."""
    if word in IRREGULAR_PLURALS:
        return IRREGULAR_PLURALS[word]
    if (
        len(word) < MIN_FOLDABLE_LENGTH
        or not word.isalpha()
        or not word.endswith("s")
        or word.endswith(NON_PLURAL_ENDINGS)
        or word in NON_PLURAL_WORDS
    ):
        return word
    if word.endswith("ies") and len(word) > MIN_FOLDABLE_LENGTH:
        return word.removesuffix("ies") + "y"
    if word.endswith(SIBILANT_PLURAL_ENDINGS):
        return word.removesuffix("es")
    return word.removesuffix("s")


def fold_term(term: str) -> str:
    """Fold every word of a unigram or bigram term."""
    return " ".join(fold_plural(word) for word in term.split(" "))


def choose_display_forms(term_counts: Mapping[str, int]) -> dict[str, str]:
    """Map each written term to the form its folded group is displayed as.

    The display form is the group's most common written form, so readers see
    "speed humps" if that is how newsletters usually put it. Ties go to the
    shorter (singular) form, then alphabetical order, so output is stable.
    """
    groups: dict[str, list[str]] = defaultdict(list)
    for term in term_counts:
        groups[fold_term(term)].append(term)

    display_forms: dict[str, str] = {}
    for variants in groups.values():
        display = min(variants, key=lambda term: (-term_counts[term], len(term), term))
        display_forms.update((variant, display) for variant in variants)
    return display_forms
