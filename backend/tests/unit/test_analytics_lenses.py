"""Unit tests for analytics/lenses.py keyword lenses."""

import unittest
from collections import Counter
from datetime import date

from analytics.lenses import (
    AMBIGUOUS_WORDS,
    LENSES,
    Lens,
    LensMatcher,
    count_newsletter_phrases,
    phrase_key,
    split_into_sentences,
    summarize_lens_hits,
    validate_lenses,
)
from analytics.records import NewsletterRecord

MATCHER = LensMatcher(LENSES)


def lenses_in(text: str, min_occurrences: int = 1) -> list[str]:
    """The lens ids a text mentions with the reviewed lens list."""
    return MATCHER.lenses_mentioned(MATCHER.count_phrases(text), min_occurrences)


def make_newsletter(newsletter_id: str, subject: str, text: str) -> NewsletterRecord:
    return NewsletterRecord(
        id=newsletter_id,
        received_date=date(2026, 9, 1),
        source_id=1,
        subject=subject,
        plain_text=text,
        topics=None,
    )


class TestReviewedLensList(unittest.TestCase):
    def test_lens_list_is_sound(self):
        self.assertEqual(validate_lenses(LENSES), [])

    def test_covers_what_aldermen_write_about_plus_strong_towns_focus(self):
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

    def test_every_lens_is_described(self):
        for lens in LENSES:
            self.assertTrue(lens.label and lens.description and lens.phrases, lens.id)


class TestPhraseNormalization(unittest.TestCase):
    def test_folds_case_plurals_possessives_and_hyphens(self):
        self.assertEqual(phrase_key("Speed Humps"), "speed hump")
        self.assertEqual(phrase_key("ICE-free zones"), "ice free zone")
        self.assertEqual(phrase_key("CPD’s"), "cpd")

    def test_sentences_split_on_punctuation_and_paragraphs_but_not_line_wraps(self):
        sentences = list(
            split_into_sentences("Protected bike\nlanes are coming. Next item\n\nNew")
        )
        self.assertEqual(
            sentences,
            [["protected", "bike", "lane", "are", "coming"], ["next", "item"], ["new"]],
        )


class TestFalsePositives(unittest.TestCase):
    """Everyday meanings of ambiguous words must not mention a lens."""

    def test_ice_as_weather_or_skating_is_not_immigration(self):
        self.assertNotIn("immigration", lenses_in("Watch for ice on sidewalks."))
        self.assertNotIn("immigration", lenses_in("Ice skating at the rink tonight."))

    def test_ice_with_a_qualifier_is_immigration(self):
        self.assertIn("immigration", lenses_in("Report ICE agents and ICE sightings."))

    def test_park_as_a_verb_or_neighborhood_is_not_parks(self):
        for text in (
            "Please park on the even side of the street.",
            "Join us in Wicker Park and Hyde Park.",
            "Free parking is available.",
        ):
            self.assertNotIn("parks_libraries", lenses_in(text), text)

    def test_park_district_is_parks(self):
        self.assertIn(
            "parks_libraries", lenses_in("The Chicago Park District pools open.")
        )

    def test_polish_and_bears_mention_nothing(self):
        self.assertEqual(lenses_in("Polish your résumé before the Bears game."), [])

    def test_words_match_whole_not_inside_other_words(self):
        # "rat" must not match "ratification" or "separate"; "bus" not "business".
        self.assertEqual(lenses_in("Separate ratification of the bylaws."), [])
        self.assertNotIn("transportation", lenses_in("A small business opened."))

    def test_phrases_do_not_span_sentences(self):
        self.assertNotIn(
            "street_safety", lenses_in("Ride your bike. Lane closures follow.")
        )

    def test_urls_and_emails_are_ignored(self):
        text = "See https://example.com/zoning-change and email zoning@ward.org"
        self.assertEqual(lenses_in(text), [])


class TestLensMatcher(unittest.TestCase):
    def test_counts_every_occurrence(self):
        counts = MATCHER.count_phrases(
            "Speed humps here. A speed hump there. Bike lanes."
        )
        self.assertEqual(counts["speed hump"], 2)
        self.assertEqual(counts["bike lane"], 1)

    def test_one_phrase_can_belong_to_several_lenses(self):
        mentioned = lenses_in("New speed humps.")
        self.assertIn("transportation", mentioned)
        self.assertIn("street_safety", mentioned)

    def test_min_occurrences_ignores_passing_mentions(self):
        passing = "Early voting is at the library."
        self.assertIn("parks_libraries", lenses_in(passing, min_occurrences=1))
        self.assertNotIn("parks_libraries", lenses_in(passing, min_occurrences=2))
        repeated = "The library reopens. Library hours are longer."
        self.assertIn("parks_libraries", lenses_in(repeated, min_occurrences=2))

    def test_lenses_are_returned_in_lens_order(self):
        lens_order = [lens.id for lens in LENSES]
        mentioned = lenses_in("Police and schools and the budget.")
        self.assertEqual(mentioned, sorted(mentioned, key=lens_order.index))


class TestValidateLenses(unittest.TestCase):
    def test_reports_ambiguous_overlapping_and_duplicate_definitions(self):
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
    def test_subject_counts_but_never_joins_the_body(self):
        counts = count_newsletter_phrases(
            [make_newsletter("n1", "Bike", "lanes and a crosswalk")], MATCHER
        )
        self.assertEqual(counts["n1"]["crosswalk"], 1)
        self.assertNotIn("bike lane", counts["n1"])
        self.assertEqual(counts["n1"]["bike"], 1)

    def test_summary_reports_lens_and_phrase_newsletter_counts(self):
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
