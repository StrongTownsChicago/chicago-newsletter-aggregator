"""Matching keyword lenses (`analytics.lenses`) against newsletter text.

Matching is explainable by design: text is split into sentences
(`split_into_sentences`), words and phrases are plural-folded the same way, and
a phrase matches whole words in order within one sentence (`LensMatcher.match`).
"""

import re
from collections import Counter
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import Any

from analytics.lenses import Lens
from analytics.plurals import fold_plural
from analytics.records import NewsletterRecord
from analytics.text import POSSESSIVE_SUFFIX, WORD_PATTERN, normalize_text

# Sentence and list punctuation ends a phrase. Line breaks do not (see
# `split_into_sentences`); blank lines, which separate paragraphs, do.
SENTENCE_BOUNDARY_PATTERN = re.compile(r"[.,;:!?()\[\]{}<>\"|/\\*#=+•·–—…]+")
PARAGRAPH_BREAK_PATTERN = re.compile(r"\n\s*\n")
# Joins a subject to its body as a separate paragraph.
SUBJECT_SEPARATOR = "\n\n"


def tokenize_phrase(phrase: str) -> list[str]:
    """Split a phrase into lowercase, plural-folded words, dropping possessives."""
    words = WORD_PATTERN.findall(phrase.lower().replace("’", "'"))
    return [fold_plural(word.removesuffix(POSSESSIVE_SUFFIX)) for word in words]


def phrase_key(phrase: str) -> str:
    """The folded form a phrase is matched by: "Speed Humps" -> "speed hump"."""
    return " ".join(tokenize_phrase(phrase))


def split_into_sentences(text: str) -> Iterator[list[str]]:
    """Yield the folded words of each sentence or list item of text.

    Text is lowercased, URLs and email addresses are dropped, and each word is
    plural-folded (`analytics.plurals`), so "speed hump" also finds "Speed
    Humps"; phrases are folded the same way. A phrase matches whole words only,
    in order, within one sentence or list item: "park" never matches "parking",
    and no phrase spans a period, bullet or paragraph break. Line breaks inside a
    paragraph do not split a phrase, because some sources hard-wrap their text.
    """
    for paragraph in PARAGRAPH_BREAK_PATTERN.split(normalize_text(text)):
        for sentence in SENTENCE_BOUNDARY_PATTERN.split(paragraph):
            words = tokenize_phrase(sentence)
            if words:
                yield words


@dataclass(frozen=True)
class TextMatches:
    """What the lens phrases found in one text."""

    # Every occurrence of each phrase, keyed by `phrase_key`.
    phrases: Counter[str] = field(default_factory=Counter)
    # Separate mentions of each lens, keyed by lens id: phrases of one lens
    # that overlap or touch count as a single mention.
    lens_mentions: Counter[str] = field(default_factory=Counter)


class LensMatcher:
    """Finds which lens phrases a text contains; built once, used for many texts."""

    def __init__(self, lenses: Iterable[Lens]) -> None:
        self.lenses = tuple(lenses)
        self.keys_by_lens = {
            lens.id: frozenset(phrase_key(phrase) for phrase in lens.phrases)
            for lens in self.lenses
        }
        self.lens_ids_by_key: dict[str, list[str]] = {}
        for lens in self.lenses:
            for key in sorted(self.keys_by_lens[lens.id]):
                self.lens_ids_by_key.setdefault(key, []).append(lens.id)
        self.first_words = {key.split(" ")[0] for key in self.lens_ids_by_key}
        self.max_phrase_words = max(
            (len(key.split(" ")) for key in self.lens_ids_by_key), default=0
        )

    def find_phrases(self, words: list[str]) -> Iterator[tuple[int, int, str]]:
        """Yield (start, end, phrase key) for every phrase in one sentence's words,
        in order of start.
        """
        for start, word in enumerate(words):
            if word not in self.first_words:
                continue
            for end in range(
                start + 1, min(start + self.max_phrase_words, len(words)) + 1
            ):
                candidate = " ".join(words[start:end])
                if candidate in self.lens_ids_by_key:
                    yield start, end, candidate

    def match(self, text: str) -> TextMatches:
        """Count the phrase occurrences and the separate lens mentions in text.

        Phrases of one lens that overlap or sit side by side ("aldermanic menu
        money", "city council meeting", "zoning map amendment") are one mention,
        so a single reference cannot reach a minimum of two on its own.
        """
        matches = TextMatches()
        for words in split_into_sentences(text):
            # Where each lens's current mention ends (exclusive) in this sentence.
            mention_ends: dict[str, int] = {}
            for start, end, key in self.find_phrases(words):
                matches.phrases[key] += 1
                for lens_id in self.lens_ids_by_key[key]:
                    current_end = mention_ends.get(lens_id)
                    # A phrase starting inside or right after the current
                    # mention extends it rather than starting a new one.
                    if current_end is None or start > current_end:
                        matches.lens_mentions[lens_id] += 1
                        mention_ends[lens_id] = end
                    else:
                        mention_ends[lens_id] = max(current_end, end)
        return matches

    def lenses_mentioned(
        self, lens_mentions: Mapping[str, int], min_mentions: int
    ) -> list[str]:
        """Return the ids of the lenses mentioned at least min_mentions times, in lens order."""
        return [
            lens.id
            for lens in self.lenses
            if lens_mentions.get(lens.id, 0) >= min_mentions
        ]


def match_newsletters(
    newsletters: Iterable[NewsletterRecord], matcher: LensMatcher
) -> dict[str, TextMatches]:
    """Match the lens phrases in each newsletter's subject and text, by newsletter id.

    The subject is its own paragraph, so no phrase spans subject and body.
    """
    return {
        newsletter.id: matcher.match(
            f"{newsletter.subject}{SUBJECT_SEPARATOR}{newsletter.plain_text}"
        )
        for newsletter in newsletters
    }


def summarize_lens_hits(
    matcher: LensMatcher,
    phrase_counts_by_newsletter: Mapping[str, Mapping[str, int]],
    lenses_by_newsletter: Mapping[str, list[str]],
) -> list[dict[str, Any]]:
    """Describe each lens with how many newsletters mention it and contain each phrase.

    phrase_counts_by_newsletter holds each newsletter's `TextMatches.phrases`.

    This is the evidence a reader needs to audit a lens: its full definition
    plus which phrases do the work. Phrases are listed most-found first.
    """
    phrase_newsletters: Counter[str] = Counter(
        key for counts in phrase_counts_by_newsletter.values() for key in counts
    )
    lens_newsletters: Counter[str] = Counter(
        lens_id for lens_ids in lenses_by_newsletter.values() for lens_id in lens_ids
    )
    return [
        {
            "id": lens.id,
            "label": lens.label,
            "description": lens.description,
            "strong_towns_focus": lens.strong_towns_focus,
            "newsletters": lens_newsletters[lens.id],
            "phrases": sorted(
                (
                    {
                        "phrase": phrase,
                        "newsletters": phrase_newsletters[phrase_key(phrase)],
                    }
                    for phrase in lens.phrases
                ),
                key=lambda item: (-item["newsletters"], item["phrase"].lower()),
            ),
        }
        for lens in matcher.lenses
    ]
