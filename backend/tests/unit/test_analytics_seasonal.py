"""Unit tests for analytics/seasonal.py recurring calendar events."""

import unittest

from analytics.plurals import fold_term
from analytics.seasonal import SEASONAL_PHRASES, is_seasonal_term
from analytics.text import extract_terms


class TestIsSeasonalTerm(unittest.TestCase):
    def test_holidays_heritage_months_and_programs(self):
        for term in (
            "labor day",
            "heritage month",
            "mexican independence",
            "senior fest",
            "school supplies",
            "national night",
        ):
            self.assertTrue(is_seasonal_term(term), term)

    def test_matches_a_phrase_inside_a_longer_term_with_plurals_folded(self):
        self.assertTrue(is_seasonal_term("day parade labor day"))
        self.assertTrue(is_seasonal_term("flu shots"))
        self.assertTrue(is_seasonal_term("cooling centers"))

    def test_news_is_not_seasonal(self):
        for term in ("property tax", "tenant ordinance", "election day", "heritage"):
            self.assertFalse(is_seasonal_term(term), term)

    def test_matches_whole_words_only(self):
        self.assertFalse(is_seasonal_term("fallen officers"))


class TestSeasonalPhrases(unittest.TestCase):
    def test_phrases_are_written_as_the_tokenizer_produces_them(self):
        # A phrase with a stopword or possessive could never match a term.
        unreachable = [
            phrase
            for phrase in SEASONAL_PHRASES
            if fold_term(phrase)
            not in {fold_term(term) for term in extract_terms(phrase)}
        ]
        self.assertEqual(unreachable, [])


if __name__ == "__main__":
    unittest.main()
