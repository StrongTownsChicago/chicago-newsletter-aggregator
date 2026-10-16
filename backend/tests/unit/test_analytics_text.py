"""Unit tests for analytics/text.py tokenization."""

import re
import unittest

from analytics.text import (
    EMAIL_PATTERN,
    count_words,
    extract_terms,
    normalize_text,
    normalize_token,
    split_into_phrases,
)


class TestNormalizeText(unittest.TestCase):
    def test_lowercases_and_unifies_apostrophes(self) -> None:
        self.assertEqual(normalize_text("Ward’s OFFICE"), "ward's office")

    def test_replaces_urls_and_emails_with_boundaries(self) -> None:
        normalized = normalize_text(
            "see https://example.com/page and info@ward32.org now"
        )
        self.assertNotIn("example", normalized)
        self.assertNotIn("ward32", normalized)
        self.assertIn(" . ", normalized)

    def test_replaces_email_inside_a_longer_token(self) -> None:
        normalized = normalize_text("write(info@ward32.org) today")
        self.assertNotIn("ward32", normalized)
        self.assertIn("today", normalized)

    def test_email_pattern_matches_exactly_what_the_unanchored_pattern_did(
        self,
    ) -> None:
        # The lookbehind only skips retries inside a run: an unanchored match
        # can always extend back to the start of its run, so matches are equal.
        unanchored = re.compile(r"\S+@\S+\.\S+")
        samples = [
            "info@ward32.org",
            "(info@ward32.org)",
            "email:info@ward32.org today",
            "Email: info@ward32.org, or call",
            "<a@b.co> and c@d.org.",
            "write\u00a0info@ward32.org now",
            "a@b@c.d e@f",
            "no email here @ all.",
            "@ward32.org",
            "x@y. trailing",
            "line one\nfoo@bar.com\tbaz@qux.io",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(
                    [match.span() for match in EMAIL_PATTERN.finditer(sample)],
                    [match.span() for match in unanchored.finditer(sample)],
                )

    def test_email_after_punctuation_does_not_leak_into_terms(self) -> None:
        terms = extract_terms("Questions? email:info@ward32.org or (help@ward32.org)")
        self.assertFalse(any("ward32" in term or "info" in term for term in terms))

    def test_long_runs_without_spaces_are_handled_in_linear_time(self) -> None:
        # A per-position retry made runs like this take minutes.
        normalized = normalize_text("x" * 200_000 + " ward")
        self.assertTrue(normalized.endswith("ward"))

    def test_replaces_www_urls(self) -> None:
        self.assertNotIn(
            "chicagorecycles", normalize_text("visit www.chicagorecycles.org")
        )


class TestNormalizeToken(unittest.TestCase):
    def test_keeps_regular_words(self) -> None:
        self.assertEqual(normalize_token("zoning"), "zoning")

    def test_drops_stopwords_and_boilerplate(self) -> None:
        self.assertIsNone(normalize_token("the"))
        self.assertIsNone(normalize_token("unsubscribe"))
        self.assertIsNone(normalize_token("del"))
        self.assertIsNone(normalize_token("october"))

    def test_drops_numbers_ids_and_single_characters(self) -> None:
        self.assertIsNone(normalize_token("2026"))
        self.assertIsNone(normalize_token("60614"))
        self.assertIsNone(normalize_token("218af5f0b5"))
        self.assertIsNone(normalize_token("x"))

    def test_keeps_allowlisted_service_numbers(self) -> None:
        for token in ("311", "chi311", "911", "988", "211"):
            with self.subTest(token=token):
                self.assertEqual(normalize_token(token), token)

    def test_keeps_ordinals_used_in_street_names(self) -> None:
        self.assertEqual(normalize_token("75th"), "75th")
        self.assertEqual(normalize_token("43rd"), "43rd")

    def test_strips_possessive(self) -> None:
        self.assertEqual(normalize_token("ward's"), "ward")

    def test_drops_contracted_stopwords(self) -> None:
        self.assertIsNone(normalize_token("don't"))


class TestSplitIntoPhrases(unittest.TestCase):
    def test_punctuation_splits_phrases_and_dropped_words_stay_as_none(self) -> None:
        phrases = split_into_phrases("Bike lanes for the city. Transit")
        self.assertEqual(phrases, [["bike", "lanes", None, None, "city"], ["transit"]])

    def test_keeps_accented_words_whole(self) -> None:
        self.assertEqual(split_into_phrases("información"), [["información"]])


class TestExtractTerms(unittest.TestCase):
    def test_extracts_unigrams_and_adjacent_bigrams(self) -> None:
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

    def test_bigrams_do_not_span_stopwords(self) -> None:
        terms = extract_terms("lanes for city")
        self.assertNotIn("lanes city", terms)
        self.assertEqual(terms, {"lanes", "city"})

    def test_bigrams_do_not_span_punctuation_or_urls(self) -> None:
        terms = extract_terms("bike. lane https://x.com/a street")
        self.assertNotIn("bike lane", terms)
        self.assertNotIn("lane street", terms)

    def test_hyphenated_words_form_bigrams(self) -> None:
        self.assertIn("single stair", extract_terms("single-stair reform"))

    def test_keeps_311_in_terms(self) -> None:
        self.assertIn("call 311", extract_terms("Call 311 to report potholes"))

    def test_empty_text_has_no_terms(self) -> None:
        self.assertEqual(extract_terms(""), set())


class TestCountWords(unittest.TestCase):
    def test_counts_whitespace_separated_words(self) -> None:
        self.assertEqual(count_words("one  two\nthree"), 3)
        self.assertEqual(count_words(""), 0)


if __name__ == "__main__":
    unittest.main()
