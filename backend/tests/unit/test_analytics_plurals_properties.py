"""Property-based tests for analytics/plurals.py plural folding."""

import unittest

from hypothesis import given
from hypothesis import strategies as st

from analytics.plurals import choose_display_forms, fold_plural, fold_term
from tests.fixtures.property_settings import PROPERTY_SETTINGS

# Stems plus the endings the fold rules care about, so most examples reach a rule.
STEMS = st.text(alphabet="abcehilorstuxyé", min_size=1, max_size=8)
ENDINGS = st.sampled_from(["", "s", "es", "ies", "ses", "sses", "xes", "ches", "us"])
WORDS = st.builds(str.__add__, STEMS, ENDINGS)
TERMS = st.one_of(
    WORDS, st.builds(lambda first, second: f"{first} {second}", WORDS, WORDS)
)


class TestPluralFoldProperties(unittest.TestCase):
    @PROPERTY_SETTINGS
    @given(WORDS)
    def test_folding_a_folded_word_changes_nothing(self, word: str) -> None:
        folded = fold_plural(word)
        self.assertEqual(fold_plural(folded), folded)

    @PROPERTY_SETTINGS
    @given(WORDS)
    def test_folding_only_shortens_a_word(self, word: str) -> None:
        folded = fold_plural(word)
        self.assertLessEqual(len(folded), len(word))
        self.assertTrue(word.startswith(folded.removesuffix("y")))

    @PROPERTY_SETTINGS
    @given(TERMS)
    def test_folding_a_folded_term_changes_nothing(self, term: str) -> None:
        folded = fold_term(term)
        self.assertEqual(fold_term(folded), folded)
        self.assertEqual(len(folded.split(" ")), len(term.split(" ")))

    @PROPERTY_SETTINGS
    @given(st.dictionaries(TERMS, st.integers(min_value=1, max_value=50), min_size=1))
    def test_each_group_shows_its_most_common_variant(
        self, term_counts: dict[str, int]
    ) -> None:
        display_forms = choose_display_forms(term_counts)

        self.assertEqual(display_forms.keys(), term_counts.keys())
        for term, display in display_forms.items():
            self.assertEqual(fold_term(display), fold_term(term))
            group_counts = [
                count
                for variant, count in term_counts.items()
                if fold_term(variant) == fold_term(term)
            ]
            self.assertEqual(term_counts[display], max(group_counts))


if __name__ == "__main__":
    unittest.main()
