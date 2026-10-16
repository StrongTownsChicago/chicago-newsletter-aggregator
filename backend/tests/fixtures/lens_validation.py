"""Guard for the reviewed lens list in `analytics/lenses.py`.

The lens list is reviewed by hand; the tests run this check over it so a
duplicate id, an ambiguous lone word or a redundant phrase fails CI.
"""

from collections.abc import Iterable

from analytics.lens_matching import tokenize_phrase
from analytics.lenses import AMBIGUOUS_WORDS, Lens
from analytics.text import contains_word_run

# Phrases are folded before the check, so "CAPS" (folded to "cap") is caught.
FOLDED_AMBIGUOUS_WORDS: frozenset[str] = frozenset(
    word for ambiguous in AMBIGUOUS_WORDS for word in tokenize_phrase(ambiguous)
)


def validate_lenses(lenses: Iterable[Lens]) -> list[str]:
    """Return every problem with a lens list; an empty list means it is sound.

    Checks that ids are unique, that no phrase is a lone AMBIGUOUS_WORDS word,
    and that no phrase repeats or contains another phrase of the same lens
    (the longer one could never add a match, so it only misleads readers).
    """
    problems: list[str] = []
    seen_ids: set[str] = set()
    for lens in lenses:
        if lens.id in seen_ids:
            problems.append(f"duplicate lens id {lens.id!r}")
        seen_ids.add(lens.id)
        tokenized = [(phrase, tokenize_phrase(phrase)) for phrase in lens.phrases]
        for phrase, words in tokenized:
            if not words:
                problems.append(f"{lens.id}: phrase {phrase!r} has no words")
            elif len(words) == 1 and words[0] in FOLDED_AMBIGUOUS_WORDS:
                problems.append(f"{lens.id}: {phrase!r} is ambiguous on its own")
        for index, (phrase, words) in enumerate(tokenized):
            for other_phrase, other_words in tokenized[index + 1 :]:
                if (
                    words
                    and other_words
                    and (
                        contains_word_run(words, other_words)
                        or contains_word_run(other_words, words)
                    )
                ):
                    problems.append(
                        f"{lens.id}: {phrase!r} and {other_phrase!r} overlap"
                    )
    return problems
