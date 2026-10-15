"""Recurring calendar events, used to tag rising terms as seasonal.

With under a year of data, "labor day" rising in September looks exactly like
a new trend; only knowing the calendar tells them apart. This curated list
names holidays, heritage months, and annual programs aldermen announce every
year. A term is seasonal when it contains one of these phrases as a run of
words (plurals folded), so "labor day" matches "labor day parade" and "flu"
matches "flu shots".

Phrases are written as the term tokenizer produces them: lowercase, with
stopwords and possessives dropped ("mother's day" becomes "mother day").
"""

from analytics.plurals import fold_term
from analytics.text import contains_word_run

HOLIDAYS_AND_OBSERVANCES: frozenset[str] = frozenset(
    {
        "new year",
        "luther king",
        "mlk",
        "black history",
        "valentine",
        "patrick day",
        "easter",
        "passover",
        "ramadan",
        "cinco",
        "memorial day",
        "mother day",
        "father day",
        "juneteenth",
        "pride month",
        "pride parade",
        "independence day",
        "fireworks",
        "labor day",
        "rosh hashanah",
        "yom kippur",
        "mexican independence",
        "hispanic heritage",
        "heritage month",
        "indigenous peoples",
        "columbus day",
        "halloween",
        "trick",
        "muertos",
        "diwali",
        "veterans day",
        "thanksgiving",
        "hanukkah",
        "kwanzaa",
        "christmas",
        "holiday season",
    }
)

# Seasons and the annual programs tied to them.
SEASONAL_PROGRAMS: frozenset[str] = frozenset(
    {
        "spring",
        "summer",
        "fall",
        "autumn",
        "winter",
        "spring break",
        "flu",
        "school supplies",
        "school bash",
        "school giveaway",
        "backpack",
        "school year",
        "national night",
        "senior fest",
        "air show",
        "water show",
        "marathon",
        "cooling center",
        "warming center",
        "extreme heat",
        "heat advisory",
        "snow removal",
        "snow route",
        "parking ban",
        "street sweeping",
        "leaf",
        "turkey",
        "toy drive",
        "coat drive",
        # Cook County property tax bills arrive in two installments a year.
        "installment",
    }
)

SEASONAL_PHRASES: frozenset[str] = HOLIDAYS_AND_OBSERVANCES | SEASONAL_PROGRAMS

_FOLDED_SEASONAL_PHRASES: tuple[list[str], ...] = tuple(
    fold_term(phrase).split(" ") for phrase in sorted(SEASONAL_PHRASES)
)


def is_seasonal_term(term: str) -> bool:
    """True if the term contains a recurring calendar event from SEASONAL_PHRASES."""
    words = fold_term(term).split(" ")
    return any(contains_word_run(words, phrase) for phrase in _FOLDED_SEASONAL_PHRASES)
