"""Unit tests for analytics/plurals.py plural folding."""

import unittest

from analytics.plurals import choose_display_forms, fold_plural, fold_term


class TestFoldPlural(unittest.TestCase):
    def test_strips_a_plain_plural_s(self):
        self.assertEqual(fold_plural("lanes"), "lane")
        self.assertEqual(fold_plural("humps"), "hump")
        self.assertEqual(fold_plural("seniors"), "senior")

    def test_ies_becomes_y(self):
        self.assertEqual(fold_plural("libraries"), "library")
        self.assertEqual(fold_plural("activities"), "activity")

    def test_sibilant_es_plurals_drop_es(self):
        self.assertEqual(fold_plural("taxes"), "tax")
        self.assertEqual(fold_plural("churches"), "church")
        self.assertEqual(fold_plural("addresses"), "address")
        self.assertEqual(fold_plural("businesses"), "business")

    def test_irregular_plurals_use_the_merge_table(self):
        self.assertEqual(fold_plural("buses"), "bus")

    def test_non_plural_endings_are_kept(self):
        for word in ("bus", "business", "campus", "illinois", "crisis", "gas", "its"):
            with self.subTest(word=word):
                self.assertEqual(fold_plural(word), word)

    def test_words_whose_stem_means_something_else_are_kept(self):
        for word in ("news", "means", "goods", "economics", "politics"):
            with self.subTest(word=word):
                self.assertEqual(fold_plural(word), word)

    def test_numbers_ordinals_and_non_plurals_are_untouched(self):
        for word in ("311", "75th", "zoning", "ward"):
            with self.subTest(word=word):
                self.assertEqual(fold_plural(word), word)


class TestFoldTerm(unittest.TestCase):
    def test_folds_each_word_of_a_bigram(self):
        self.assertEqual(fold_term("bike lanes"), "bike lane")
        self.assertEqual(fold_term("property taxes"), "property tax")
        self.assertEqual(fold_term("seniors centers"), "senior center")


class TestChooseDisplayForms(unittest.TestCase):
    def test_variants_map_to_the_most_common_written_form(self):
        forms = choose_display_forms({"speed humps": 12, "speed hump": 4})
        self.assertEqual(
            forms, {"speed humps": "speed humps", "speed hump": "speed humps"}
        )

    def test_ties_prefer_the_shorter_form(self):
        forms = choose_display_forms({"bike lane": 5, "bike lanes": 5})
        self.assertEqual(forms["bike lanes"], "bike lane")

    def test_unrelated_terms_are_not_merged(self):
        forms = choose_display_forms({"news": 9, "new": 20, "bus": 3})
        self.assertEqual(forms, {"news": "news", "new": "new", "bus": "bus"})


if __name__ == "__main__":
    unittest.main()
