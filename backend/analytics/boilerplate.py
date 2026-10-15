"""Per-source boilerplate removal: drop text a source repeats in many of its issues.

Newsletters carry standing blocks (platform footers, office hours, resource
directories, links to other elected officials) that recur issue after issue.
Counted as content, they make a ward look "distinctive" for its template and
inflate term shares.

Repeated text is found with word shingles (runs of consecutive words) rather
than whole paragraphs: some platforms export an issue as one unbroken line, and
a standing block often shares a line or sentence with text that changes, so
exact paragraph matching misses it. Any shingle found in a large share of one
source's newsletters is template, and every word it covers is removed.
"""

import math
from collections import Counter, defaultdict
from collections.abc import Iterable
from dataclasses import replace
from typing import NamedTuple

from analytics.records import NewsletterRecord
from analytics.text import EMAIL_PATTERN, URL_PATTERN, WORD_PATTERN

# Long enough that ordinary phrasing ("for more information please visit")
# rarely recurs by chance, short enough to catch short standing lines such as
# a platform footer. Results on the archive barely change between 5 and 12.
SHINGLE_WORDS = 8
# Removed text is replaced by a line break, a phrase boundary for tokenization,
# so no bigram is formed from words on either side of a removed span.
REMOVED_SPAN_REPLACEMENT = "\n"
PERCENT = 100


class Word(NamedTuple):
    """A lowercase word and its character span in the original text."""

    start: int
    end: int
    text: str


def find_words(text: str) -> list[Word]:
    """List the words of text with their positions, skipping URLs and emails.

    Links are blanked with spaces of the same length so positions still refer
    to the original text; tracking URLs differ per send and would otherwise
    hide a repeated block.
    """
    masked = text.replace("’", "'")
    for pattern in (URL_PATTERN, EMAIL_PATTERN):
        masked = pattern.sub(lambda match: " " * len(match.group()), masked)
    return [
        Word(match.start(), match.end(), match.group().lower())
        for match in WORD_PATTERN.finditer(masked)
    ]


def build_shingles(words: list[Word], size: int) -> list[str]:
    """Return every run of size consecutive words, in order (index i starts at word i)."""
    tokens = [word.text for word in words]
    return [
        " ".join(tokens[index : index + size])
        for index in range(len(tokens) - size + 1)
    ]


def find_recurring_shingles(
    shingles_per_newsletter: Iterable[list[str]], min_share_percent: int
) -> set[str]:
    """Return the shingles found in at least min_share_percent of the newsletters."""
    newsletter_count = 0
    counts: Counter[str] = Counter()
    for shingles in shingles_per_newsletter:
        newsletter_count += 1
        counts.update(set(shingles))
    min_newsletters = math.ceil(newsletter_count * min_share_percent / PERCENT)
    return {shingle for shingle, count in counts.items() if count >= min_newsletters}


def find_covered_spans(
    words: list[Word], shingles: list[str], recurring: set[str], size: int
) -> list[tuple[int, int]]:
    """Return the character spans covered by recurring shingles, merged and in order.

    A span runs from the first to the last word of a stretch of consecutive
    covered words, so punctuation and links inside the stretch go with it.
    """
    covered = [False] * len(words)
    for index, shingle in enumerate(shingles):
        if shingle in recurring:
            covered[index : index + size] = [True] * size

    spans: list[tuple[int, int]] = []
    previous_covered = False
    for word, is_covered in zip(words, covered, strict=True):
        if is_covered and previous_covered:
            spans[-1] = (spans[-1][0], word.end)
        elif is_covered:
            spans.append((word.start, word.end))
        previous_covered = is_covered
    return spans


def remove_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """Replace each (start, end) span of text, given in order, with a phrase boundary."""
    pieces: list[str] = []
    position = 0
    for start, end in spans:
        pieces.append(text[position:start])
        pieces.append(REMOVED_SPAN_REPLACEMENT)
        position = end
    pieces.append(text[position:])
    return "".join(pieces)


def remove_source_boilerplate(
    newsletters: list[NewsletterRecord],
    min_share_percent: int,
    min_source_newsletters: int,
) -> list[NewsletterRecord]:
    """Return the newsletters with each source's recurring text removed from plain_text.

    Text is boilerplate when a run of SHINGLE_WORDS words appears in at least
    min_share_percent of its source's newsletters. Sources with fewer than
    min_source_newsletters newsletters are left untouched: with only a few
    issues, one event announced in consecutive issues would look like a
    template. Newsletters without a source, and those with nothing removed,
    are returned unchanged. Order is preserved.
    """
    indexes_by_source: dict[int, list[int]] = defaultdict(list)
    for index, newsletter in enumerate(newsletters):
        if newsletter.source_id is not None:
            indexes_by_source[newsletter.source_id].append(index)

    cleaned = list(newsletters)
    for indexes in indexes_by_source.values():
        if len(indexes) < min_source_newsletters:
            continue
        words = [find_words(newsletters[index].plain_text) for index in indexes]
        shingles = [
            build_shingles(newsletter_words, SHINGLE_WORDS)
            for newsletter_words in words
        ]
        recurring = find_recurring_shingles(shingles, min_share_percent)
        for index, newsletter_words, newsletter_shingles in zip(
            indexes, words, shingles, strict=True
        ):
            spans = find_covered_spans(
                newsletter_words, newsletter_shingles, recurring, SHINGLE_WORDS
            )
            if spans:
                cleaned[index] = replace(
                    newsletters[index],
                    plain_text=remove_spans(newsletters[index].plain_text, spans),
                )
    return cleaned
