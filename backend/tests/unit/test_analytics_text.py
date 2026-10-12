"""Unit tests for analytics/text.py tokenization."""

import unittest

from analytics.text import (
    count_words,
    extract_terms,
    normalize_text,
    normalize_token,
    split_into_phrases,
)


class TestNormalizeText(unittest.TestCase):
    def test_lowercases_and_unifies_apostrophes(self):
        self.assertEqual(normalize_text("Ward’s OFFICE"), "ward's office")

    def test_replaces_urls_and_emails_with_boundaries(self):
        normalized = normalize_text(
            "see https://example.com/page and info@ward32.org now"
        )
        self.assertNotIn("example", normalized)
        self.assertNotIn("ward32", normalized)
        self.assertIn(" . ", normalized)

    def test_replaces_www_urls(self):
        self.assertNotIn(
            "chicagorecycles", normalize_text("visit www.chicagorecycles.org")
        )


class TestNormalizeToken(unittest.TestCase):
    def test_keeps_regular_words(self):
        self.assertEqual(normalize_token("zoning"), "zoning")

    def test_drops_stopwords_and_boilerplate(self):
        self.assertIsNone(normalize_token("the"))
        self.assertIsNone(normalize_token("unsubscribe"))
        self.assertIsNone(normalize_token("del"))
        self.assertIsNone(normalize_token("october"))

    def test_drops_numbers_ids_and_single_characters(self):
        self.assertIsNone(normalize_token("2026"))
        self.assertIsNone(normalize_token("60614"))
        self.assertIsNone(normalize_token("218af5f0b5"))
        self.assertIsNone(normalize_token("x"))

    def test_keeps_ordinals_used_in_street_names(self):
        self.assertEqual(normalize_token("75th"), "75th")
        self.assertEqual(normalize_token("43rd"), "43rd")

    def test_strips_possessive(self):
        self.assertEqual(normalize_token("ward's"), "ward")

    def test_drops_contracted_stopwords(self):
        self.assertIsNone(normalize_token("don't"))


class TestSplitIntoPhrases(unittest.TestCase):
    def test_punctuation_splits_phrases_and_dropped_words_stay_as_none(self):
        phrases = split_into_phrases("Bike lanes for the city. Transit")
        self.assertEqual(phrases, [["bike", "lanes", None, None, "city"], ["transit"]])

    def test_keeps_accented_words_whole(self):
        self.assertEqual(split_into_phrases("información"), [["información"]])


class TestExtractTerms(unittest.TestCase):
    def test_extracts_unigrams_and_adjacent_bigrams(self):
        self.assertEqual(
            extract_terms("Protected bike lanes"),
            {
                "protected",
                "bike",
                "lanes",
                "protected bike",
                "bike lanes",
            },
        )

    def test_bigrams_do_not_span_stopwords(self):
        terms = extract_terms("lanes for city")
        self.assertNotIn("lanes city", terms)
        self.assertEqual(terms, {"lanes", "city"})

    def test_bigrams_do_not_span_punctuation_or_urls(self):
        terms = extract_terms("bike. lane https://x.com/a street")
        self.assertNotIn("bike lane", terms)
        self.assertNotIn("lane street", terms)

    def test_hyphenated_words_form_bigrams(self):
        self.assertIn("single stair", extract_terms("single-stair reform"))

    def test_empty_text_has_no_terms(self):
        self.assertEqual(extract_terms(""), set())


class TestCountWords(unittest.TestCase):
    def test_counts_whitespace_separated_words(self):
        self.assertEqual(count_words("one  two\nthree"), 3)
        self.assertEqual(count_words(""), 0)


if __name__ == "__main__":
    unittest.main()
