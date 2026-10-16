"""Unit tests for analytics/stopwords.py word lists."""

import unittest

from analytics.plurals import fold_plural
from analytics.stopwords import EXCLUDED_TERMS, SPANISH_STOPWORDS, TREND_FILLER_WORDS


def is_mojibake(word: str) -> bool:
    """True when the word is UTF-8 text that was mis-decoded as Windows-1252.

    Re-encoding such a word as Windows-1252 recovers valid UTF-8 bytes that
    decode to a different string (e.g. "mÃ¡s" -> "más"). Correct words either
    fail that round trip or come back unchanged.
    """
    try:
        return word.encode("cp1252").decode("utf-8") != word
    except UnicodeError:
        return False


class TestStopwordEncoding(unittest.TestCase):
    def test_detector_flags_mis_decoded_text_only(self):
        self.assertTrue(is_mojibake("mÃ¡s"))
        self.assertFalse(is_mojibake("más"))
        self.assertFalse(is_mojibake("street"))

    def test_no_excluded_term_is_mojibake(self):
        self.assertEqual([term for term in EXCLUDED_TERMS if is_mojibake(term)], [])

    def test_accented_spanish_stopword_is_spelled_correctly(self):
        self.assertIn("más", SPANISH_STOPWORDS)


class TestTrendFillerWords(unittest.TestCase):
    def test_written_in_folded_singular_form(self):
        # Rising terms fold each word before looking it up.
        self.assertEqual(
            [word for word in TREND_FILLER_WORDS if fold_plural(word) != word], []
        )

    def test_not_already_excluded_from_the_index(self):
        # Excluded words never reach a term, so listing them would be dead weight.
        self.assertEqual(TREND_FILLER_WORDS & EXCLUDED_TERMS, frozenset())
