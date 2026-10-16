"""Unit tests for analytics/terms.py: collapsing and de-duplicating distinctive terms."""

import unittest
from collections.abc import Callable

from analytics.terms import (
    DistinctiveTerm,
    build_word_specificity,
    choose_representative_term,
    collapse_terms_sharing_newsletters,
    drop_overlapping_terms,
    jaccard_similarity,
)


def distinctive(term: str, score: float = 1.0) -> DistinctiveTerm:
    return DistinctiveTerm(
        term=term,
        score=score,
        lift=2.0,
        ward_newsletters=1,
        ward_share=0.1,
        rest_share=0.0,
    )


def no_specificity(term: str) -> float:
    return 0.0


class TestJaccardSimilarity(unittest.TestCase):
    def test_shared_share_of_union(self) -> None:
        self.assertEqual(jaccard_similarity({1, 2, 3}, {1, 2, 3}), 1.0)
        self.assertEqual(jaccard_similarity({1, 2, 3, 4}, {1, 2, 3}), 0.75)
        self.assertEqual(jaccard_similarity({1}, {2}), 0.0)
        self.assertEqual(jaccard_similarity(set(), set()), 1.0)


class TestWordSpecificity(unittest.TestCase):
    def test_rare_words_score_higher_and_plurals_fold(self) -> None:
        specificity = build_word_specificity(
            {
                "helps": 50,
                "identify": 40,
                "gunshot": 2,
                "detection": 3,
                "helps identify": 5,
            },
            total_newsletters=100,
        )
        self.assertGreater(
            specificity("gunshot detection"), specificity("helps identify")
        )
        self.assertEqual(specificity("gunshots"), specificity("gunshot"))


class TestChooseRepresentativeTerm(unittest.TestCase):
    def test_prefers_a_phrase_over_a_higher_scoring_word(self) -> None:
        group = [distinctive("houseless", 3.0), distinctive("houseless neighbors", 2.0)]
        chosen = choose_representative_term(group, no_specificity)
        self.assertEqual(chosen.term, "houseless neighbors")

    def test_prefers_the_most_specific_phrase(self) -> None:
        group = [
            distinctive("helps identify", 3.0),
            distinctive("gunshot detection", 2.0),
        ]
        specificity = {"helps identify": 1.0, "gunshot detection": 5.0}
        chosen = choose_representative_term(group, specificity.__getitem__)
        self.assertEqual(chosen.term, "gunshot detection")

    def test_prefers_the_phrase_whose_words_recur_in_the_group(self) -> None:
        group = [
            distinctive("shakman exempt", 3.0),
            distinctive("attorney hiring", 1.0),
            distinctive("hiring senior", 1.0),
            distinctive("hiring mid", 1.0),
            distinctive("attorney", 1.0),
        ]
        specificity = {"shakman exempt": 9.0}
        chosen = choose_representative_term(
            group, lambda term: specificity.get(term, 0.0)
        )
        self.assertEqual(chosen.term, "attorney hiring")

    def test_ties_go_to_the_higher_score(self) -> None:
        group = [distinctive("award range", 1.0), distinctive("procurement news", 2.0)]
        chosen = choose_representative_term(group, no_specificity)
        self.assertEqual(chosen.term, "procurement news")


class TestCollapseTermsSharingNewsletters(unittest.TestCase):
    def setUp(self) -> None:
        block = set(range(24))
        self.newsletters_by_term = {
            "procurement news": block,
            "certified vendor": block,
            # Another standing section, in 23 of the block's 24 newsletters
            # (Jaccard 0.958): nearly the same issues, different content.
            "attorney hiring": set(range(23)),
            "truman college": {30, 31, 32, 33, 34},
            # Nests with "truman college" (Jaccard 0.83).
            "truman": {30, 31, 32, 33, 34, 35},
            "bike lane": {30, 40, 41},
        }
        self.ranked = [
            distinctive("procurement news", 3.0),
            distinctive("truman", 2.8),
            distinctive("bike lane", 2.5),
            distinctive("certified vendor", 2.0),
            distinctive("attorney hiring", 1.5),
            distinctive("truman college", 1.0),
        ]

    def collapse(
        self,
        min_similarity: float = 0.8,
        limit: int = 10,
        specificity: Callable[[str], float] = no_specificity,
    ) -> list[DistinctiveTerm]:
        return collapse_terms_sharing_newsletters(
            self.ranked, self.newsletters_by_term, min_similarity, limit, specificity
        )

    def test_identical_sets_and_nested_terms_become_one_entry(self) -> None:
        result = self.collapse()
        self.assertEqual(
            [(item.term, item.related_terms) for item in result],
            [
                ("procurement news", 1),
                ("bike lane", 0),
                ("attorney hiring", 0),
                ("truman college", 1),
            ],
        )

    def test_nearly_identical_sets_of_unrelated_terms_stay_apart(self) -> None:
        result = self.collapse(min_similarity=0.5)
        self.assertIn("attorney hiring", [item.term for item in result])

    def test_threshold_keeps_loosely_overlapping_nested_terms_apart(self) -> None:
        result = self.collapse(min_similarity=0.9)
        self.assertIn("truman", [item.term for item in result])
        self.assertIn("truman college", [item.term for item in result])

    def test_nested_terms_join_only_near_the_first_term(self) -> None:
        # "truman" is in 6 newsletters; "truman square" shares only 3 with it,
        # so it does not join even though it nests with "truman".
        self.newsletters_by_term["truman square"] = {33, 34, 35}
        self.ranked.append(distinctive("truman square", 0.5))
        result = self.collapse()
        self.assertIn("truman square", [item.term for item in result])

    def test_limit_counts_entries_not_terms(self) -> None:
        result = self.collapse(limit=2)
        self.assertEqual(
            [(item.term, item.related_terms) for item in result],
            [("procurement news", 1), ("truman college", 1)],
        )

    def test_entries_are_ranked_by_their_representative_score(self) -> None:
        specificity = {"certified vendor": 9.0}
        result = self.collapse(
            specificity=lambda term: specificity.get(term, 0.0),
        )
        self.assertEqual(
            [item.term for item in result],
            ["bike lane", "certified vendor", "attorney hiring", "truman college"],
        )


class TestDropOverlappingTerms(unittest.TestCase):
    def test_drops_terms_that_are_part_of_a_kept_phrase(self) -> None:
        kept = drop_overlapping_terms(
            ["labor day", "labor", "day weekend", "senior fest", "fest"],
            lambda term: term,
        )
        self.assertEqual(kept, ["labor day", "senior fest"])

    def test_keeps_distinct_phrases_that_share_a_word(self) -> None:
        ranked = ["labor day", "election day", "next week", "next superintendent"]
        self.assertEqual(drop_overlapping_terms(ranked, lambda term: term), ranked)


if __name__ == "__main__":
    unittest.main()
