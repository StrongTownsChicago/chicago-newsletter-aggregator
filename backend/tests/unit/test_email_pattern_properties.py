"""Property-based tests for email_matches_pattern against a reference LIKE matcher."""

import unittest
from functools import cache

from hypothesis import given
from hypothesis import strategies as st

from ingest.email.email_parser import email_matches_pattern
from tests.fixtures.property_settings import PROPERTY_SETTINGS

# Address characters, regex metacharacters (which must match only themselves),
# the `%` wildcard, the literal `_`, and whitespace for the trimming rule.
ADDRESS_ALPHABET = "abAB09@._+-%*?()[]{}|^$\\ \t"
ADDRESSES = st.text(alphabet=ADDRESS_ALPHABET, max_size=12)
LITERAL_ADDRESSES = st.text(
    alphabet=ADDRESS_ALPHABET.replace("%", ""), min_size=1, max_size=12
).filter(str.strip)
DOMAIN_LABELS = st.text(alphabet="abcxyz09-", min_size=1, max_size=8)


def like_matches(email: str, pattern: str) -> bool:
    """Whole-string, case-insensitive SQL LIKE with only `%` as a wildcard."""
    text, wildcard_pattern = email.strip().lower(), pattern.strip().lower()
    if not text or not wildcard_pattern:
        return False

    @cache
    def matches_from(text_index: int, pattern_index: int) -> bool:
        if pattern_index == len(wildcard_pattern):
            return text_index == len(text)
        if wildcard_pattern[pattern_index] == "%":
            return any(
                matches_from(next_index, pattern_index + 1)
                for next_index in range(text_index, len(text) + 1)
            )
        return (
            text_index < len(text)
            and text[text_index] == wildcard_pattern[pattern_index]
            and matches_from(text_index + 1, pattern_index + 1)
        )

    return matches_from(0, 0)


class TestEmailPatternProperties(unittest.TestCase):
    @PROPERTY_SETTINGS
    @given(ADDRESSES, ADDRESSES)
    def test_agrees_with_reference_like_matcher(self, email: str, pattern: str) -> None:
        self.assertEqual(
            email_matches_pattern(email, pattern), like_matches(email, pattern)
        )

    @PROPERTY_SETTINGS
    @given(LITERAL_ADDRESSES)
    def test_a_pattern_without_wildcards_matches_itself_in_any_case(
        self, address: str
    ) -> None:
        self.assertTrue(email_matches_pattern(address.upper(), address.lower()))

    @PROPERTY_SETTINGS
    @given(DOMAIN_LABELS, DOMAIN_LABELS, DOMAIN_LABELS)
    def test_domain_wildcard_never_matches_a_lookalike_domain(
        self, local_part: str, domain: str, attacker_suffix: str
    ) -> None:
        pattern = f"%@{domain}.org"

        self.assertTrue(email_matches_pattern(f"{local_part}@{domain}.org", pattern))
        self.assertFalse(
            email_matches_pattern(
                f"{local_part}@{domain}.org.{attacker_suffix}.io", pattern
            )
        )
        self.assertFalse(email_matches_pattern(f"{local_part}@{domain}xorg", pattern))


if __name__ == "__main__":
    unittest.main()
