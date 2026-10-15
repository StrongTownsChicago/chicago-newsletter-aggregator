"""Tokenization of newsletter text into unigram and bigram terms."""

import re

from analytics.stopwords import EXCLUDED_TERMS

URL_PATTERN = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
# Matches only from the start of a whitespace-delimited run; without the
# lookbehind every position inside a long run is retried, which is quadratic
# (minutes on the multi-hundred-KB runs some extracted newsletters contain).
EMAIL_PATTERN = re.compile(r"(?<!\S)\S+@\S+\.\S+")
# Punctuation that ends a phrase; bigrams never span these boundaries.
PHRASE_BOUNDARY_PATTERN = re.compile(r"[.,;:!?()\[\]{}<>\"|/\\*#=+•·–—…\n\r\t]+")
# Letters and digits in any script, so accented Spanish words stay whole.
WORD_PATTERN = re.compile(r"[^\W_]+(?:'[^\W_]+)*")
POSSESSIVE_SUFFIX = "'s"
ORDINAL_PATTERN = re.compile(r"\d+(?:st|nd|rd|th)")
# The only tokens with digits that carry topical meaning on their own: public
# service phone lines. Other numbers are dates, times, addresses, and phone
# fragments. 311 (city services, and its "CHI311" app), 911 (emergencies), 988
# (Suicide & Crisis Lifeline), 211 (community resource referrals).
ALLOWED_DIGIT_TOKENS: frozenset[str] = frozenset({"311", "chi311", "911", "988", "211"})
MIN_TOKEN_LENGTH = 2


def normalize_text(text: str) -> str:
    """Lowercase text, unify apostrophes, and blank out URLs and email addresses.

    URLs and emails are replaced with a phrase boundary so no bigram is formed
    across the removed span.
    """
    lowered = text.lower().replace("’", "'").replace("‘", "'")
    without_urls = URL_PATTERN.sub(" . ", lowered)
    return EMAIL_PATTERN.sub(" . ", without_urls)


def normalize_token(raw_token: str) -> str | None:
    """Return the indexable form of a word, or None if it should be dropped.

    Drops single characters, excluded words, and tokens containing digits
    unless they are ordinals ("43rd" and "75th" are common in street names) or
    in ALLOWED_DIGIT_TOKENS; this removes numbers, dates, zip codes, and
    tracking IDs. Strips a trailing possessive so "ward's" and "ward" count as
    the same term.
    """
    token = raw_token.removesuffix(POSSESSIVE_SUFFIX).strip("'")
    if len(token) < MIN_TOKEN_LENGTH:
        return None
    if (
        any(char.isdigit() for char in token)
        and token not in ALLOWED_DIGIT_TOKENS
        and not ORDINAL_PATTERN.fullmatch(token)
    ):
        return None
    if token in EXCLUDED_TERMS or raw_token in EXCLUDED_TERMS:
        return None
    return token


def split_into_phrases(text: str) -> list[list[str | None]]:
    """Split normalized text into phrases of tokens.

    Dropped words stay in place as None so adjacency is preserved: a bigram is
    only formed from two kept words that were next to each other in the text.
    """
    return [
        [normalize_token(word) for word in WORD_PATTERN.findall(phrase)]
        for phrase in PHRASE_BOUNDARY_PATTERN.split(normalize_text(text))
    ]


def extract_terms(text: str) -> set[str]:
    """Return the distinct unigrams and bigrams present in text."""
    terms: set[str] = set()
    for phrase in split_into_phrases(text):
        terms.update(token for token in phrase if token is not None)
        terms.update(
            f"{first} {second}"
            for first, second in zip(phrase, phrase[1:])
            if first is not None and second is not None
        )
    return terms


def count_words(text: str) -> int:
    """Count whitespace-separated words in text."""
    return len(text.split())


def contains_word_run(words: list[str], part: list[str]) -> bool:
    """True if part occurs in words as a contiguous run."""
    return any(
        words[start : start + len(part)] == part
        for start in range(len(words) - len(part) + 1)
    )
