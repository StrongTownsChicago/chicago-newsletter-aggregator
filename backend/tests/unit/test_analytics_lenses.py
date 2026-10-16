"""Unit tests for analytics/lenses.py keyword lenses."""

import unittest
from collections import Counter
from datetime import date

from analytics.lenses import (
    AMBIGUOUS_WORDS,
    LENSES,
    Lens,
    LensMatcher,
    match_newsletters,
    phrase_key,
    split_into_sentences,
    summarize_lens_hits,
)
from analytics.records import NewsletterRecord
from tests.fixtures.lens_validation import validate_lenses

MATCHER = LensMatcher(LENSES)


def lenses_in(text: str, min_mentions: int = 1) -> list[str]:
    """The lens ids a text mentions with the reviewed lens list."""
    return MATCHER.lenses_mentioned(MATCHER.match(text).lens_mentions, min_mentions)


def make_newsletter(newsletter_id: str, subject: str, text: str) -> NewsletterRecord:
    return NewsletterRecord(
        id=newsletter_id,
        received_date=date(2026, 9, 1),
        source_id=1,
        subject=subject,
        plain_text=text,
    )


class TestReviewedLensList(unittest.TestCase):
    def test_lens_list_is_sound(self) -> None:
        self.assertEqual(validate_lenses(LENSES), [])

    def test_covers_what_aldermen_write_about_plus_strong_towns_focus(self) -> None:
        ids = {lens.id for lens in LENSES}
        for expected in (
            "public_safety",
            "city_services",
            "schools",
            "parks_libraries",
            "immigration",
            "housing_development",
            "transportation",
            "budget_taxes",
            "events",
            "elections_civic",
            "seniors_health",
        ):
            self.assertIn(expected, ids)
        self.assertTrue(any(lens.strong_towns_focus for lens in LENSES))

    def test_every_lens_is_described(self) -> None:
        for lens in LENSES:
            self.assertTrue(lens.label and lens.description and lens.phrases, lens.id)


class TestPhraseNormalization(unittest.TestCase):
    def test_folds_case_plurals_possessives_and_hyphens(self) -> None:
        self.assertEqual(phrase_key("Speed Humps"), "speed hump")
        self.assertEqual(phrase_key("ICE-free zones"), "ice free zone")
        self.assertEqual(phrase_key("CPD’s"), "cpd")

    def test_sentences_split_on_punctuation_and_paragraphs_but_not_line_wraps(
        self,
    ) -> None:
        sentences = list(
            split_into_sentences("Protected bike\nlanes are coming. Next item\n\nNew")
        )
        self.assertEqual(
            sentences,
            [["protected", "bike", "lane", "are", "coming"], ["next", "item"], ["new"]],
        )


class TestFalsePositives(unittest.TestCase):
    """Everyday meanings of ambiguous words must not mention a lens."""

    def test_ice_as_weather_or_skating_is_not_immigration(self) -> None:
        self.assertNotIn("immigration", lenses_in("Watch for ice on sidewalks."))
        self.assertNotIn("immigration", lenses_in("Ice skating at the rink tonight."))

    def test_ice_with_a_qualifier_is_immigration(self) -> None:
        self.assertIn("immigration", lenses_in("Report ICE agents and ICE sightings."))

    def test_park_as_a_verb_or_neighborhood_is_not_parks(self) -> None:
        for text in (
            "Please park on the even side of the street.",
            "Join us in Wicker Park and Hyde Park.",
            "Free parking is available.",
        ):
            self.assertNotIn("parks_libraries", lenses_in(text), text)

    def test_park_district_is_parks(self) -> None:
        self.assertIn(
            "parks_libraries", lenses_in("The Chicago Park District pools open.")
        )

    def test_polish_and_bears_mention_nothing(self) -> None:
        self.assertEqual(lenses_in("Polish your résumé before the Bears game."), [])

    def test_words_match_whole_not_inside_other_words(self) -> None:
        # "rat" must not match "ratification" or "separate"; "bus" not "business".
        self.assertEqual(lenses_in("Separate ratification of the bylaws."), [])
        self.assertNotIn("transportation", lenses_in("A small business opened."))

    def test_phrases_do_not_span_sentences(self) -> None:
        self.assertNotIn(
            "street_safety", lenses_in("Ride your bike. Lane closures follow.")
        )

    def test_urls_and_emails_are_ignored(self) -> None:
        text = "See https://example.com/zoning-change and email zoning@ward.org"
        self.assertEqual(lenses_in(text), [])


class TestLensMatcher(unittest.TestCase):
    def test_counts_every_occurrence(self) -> None:
        matches = MATCHER.match("Speed humps here. A speed hump there. Bike lanes.")
        self.assertEqual(matches.phrases["speed hump"], 2)
        self.assertEqual(matches.phrases["bike lane"], 1)
        self.assertEqual(matches.lens_mentions["street_safety"], 3)

    def test_one_phrase_can_belong_to_several_lenses(self) -> None:
        mentioned = lenses_in("New speed humps.")
        self.assertIn("transportation", mentioned)
        self.assertIn("street_safety", mentioned)

    def test_min_occurrences_ignores_passing_mentions(self) -> None:
        passing = "Early voting is at the library."
        self.assertIn("parks_libraries", lenses_in(passing, min_mentions=1))
        self.assertNotIn("parks_libraries", lenses_in(passing, min_mentions=2))
        repeated = "The library reopens. Library hours are longer."
        self.assertIn("parks_libraries", lenses_in(repeated, min_mentions=2))

    def test_overlapping_or_adjacent_phrases_are_one_mention(self) -> None:
        # Each text is one reference built from two phrases of the same lens.
        for text, lens_id in (
            ("Ask about aldermanic menu money.", "budget_taxes"),
            ("At the city council meeting.", "city_council"),
            ("A residential parking permit zone.", "transportation"),
            ("A zoning map amendment.", "zoning_land_use"),
            ("Small business owners welcome.", "local_business"),
        ):
            matches = MATCHER.match(text)
            self.assertGreaterEqual(sum(matches.phrases.values()), 2, text)
            self.assertEqual(matches.lens_mentions[lens_id], 1, text)
            self.assertNotIn(lens_id, lenses_in(text, min_mentions=2), text)

    def test_separated_phrases_are_separate_mentions(self) -> None:
        matches = MATCHER.match("The city council voted on the ordinance.")
        self.assertEqual(matches.lens_mentions["city_council"], 2)
        # A word between the phrases separates them; a sentence break too.
        self.assertEqual(
            MATCHER.match("Zoning. Map amendment.").lens_mentions["zoning_land_use"], 2
        )

    def test_lenses_are_returned_in_lens_order(self) -> None:
        lens_order = [lens.id for lens in LENSES]
        mentioned = lenses_in("Police and schools and the budget.")
        self.assertEqual(mentioned, sorted(mentioned, key=lens_order.index))


class TestValidateLenses(unittest.TestCase):
    def test_ambiguous_words_are_caught_in_any_form(self) -> None:
        # "CAPS" folds to "cap" and "Bears" to "bear"; the guard must still hold.
        for phrase in ("CAPS", "Caps", "Bears", "ICE", "Parks"):
            problems = validate_lenses([Lens("a", "A", "d", (phrase,))])
            self.assertEqual(len(problems), 1, phrase)
            self.assertIn("ambiguous", problems[0])

    def test_reports_ambiguous_overlapping_and_duplicate_definitions(self) -> None:
        ambiguous_word = sorted(AMBIGUOUS_WORDS)[0]
        problems = validate_lenses(
            [
                Lens("a", "A", "d", (ambiguous_word,)),
                Lens("b", "B", "d", ("bike", "bike lanes")),
                Lens("b", "B again", "d", ("budget", "Budgets")),
            ]
        )
        self.assertEqual(len(problems), 4)
        self.assertIn("ambiguous", problems[0])
        self.assertIn("overlap", problems[1])
        self.assertIn("duplicate lens id", problems[2])
        self.assertIn("overlap", problems[3])


class TestNewsletterPhrasesAndSummary(unittest.TestCase):
    def test_subject_counts_but_never_joins_the_body(self) -> None:
        matches = match_newsletters(
            [make_newsletter("n1", "Bike", "lanes and a crosswalk")], MATCHER
        )
        phrases = matches["n1"].phrases
        self.assertEqual(phrases["crosswalk"], 1)
        self.assertNotIn("bike lane", phrases)
        self.assertEqual(phrases["bike"], 1)

    def test_summary_reports_lens_and_phrase_newsletter_counts(self) -> None:
        lens = Lens("transit", "Transit", "Buses and trains.", ("bus", "Red Line"))
        matcher = LensMatcher([lens])
        phrase_counts = {
            "a": Counter({"bus": 3}),
            "b": Counter({"bus": 1, "red line": 1}),
            "c": Counter(),
        }
        summary = summarize_lens_hits(matcher, phrase_counts, {"a": ["transit"]})
        self.assertEqual(
            summary,
            [
                {
                    "id": "transit",
                    "label": "Transit",
                    "description": "Buses and trains.",
                    "strong_towns_focus": False,
                    "newsletters": 1,
                    "phrases": [
                        {"phrase": "bus", "newsletters": 2},
                        {"phrase": "Red Line", "newsletters": 1},
                    ],
                }
            ],
        )


if __name__ == "__main__":
    unittest.main()
