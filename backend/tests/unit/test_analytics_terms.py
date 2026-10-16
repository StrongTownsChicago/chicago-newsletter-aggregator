"""Unit tests for analytics/terms.py term metrics."""

import unittest
from collections.abc import Set
from datetime import date
from typing import Any

from analytics.records import NewsletterRecord, SourceRecord
from analytics.terms import (
    NewsletterTerms,
    build_name_tokens_by_ward,
    build_newsletter_terms,
    build_term_index,
    compute_distinctive_terms,
    compute_rising_terms,
    contains_filler_word,
    count_newsletters_per_term,
    is_rising_candidate,
    score_distinctive_term,
    select_latest_complete_month,
    select_vocabulary,
    smoothed_share,
    term_mentions_name,
)


def doc(
    terms: Set[str],
    ward: str | None = "1",
    month: str = "2026-01",
    source_id: int | None = 1,
    newsletter_id: str = "n",
) -> NewsletterTerms:
    return NewsletterTerms(
        newsletter_id=newsletter_id,
        source_id=source_id,
        ward=ward,
        month=month,
        terms=frozenset(terms),
    )


class TestBuildNewsletterTerms(unittest.TestCase):
    def test_tokenizes_subject_and_body_and_attaches_bucket_keys(self) -> None:
        newsletter = NewsletterRecord(
            id="n1",
            received_date=date(2026, 3, 4),
            source_id=5,
            subject="Bike lanes",
            plain_text="Zoning hearing",
        )
        source = SourceRecord(id=5, name="A", ward="40", source_type="alderman")
        [document] = build_newsletter_terms([newsletter], {5: source})
        self.assertEqual(document.ward, "40")
        self.assertEqual(document.month, "2026-03")
        self.assertIn("bike lanes", document.terms)
        self.assertIn("zoning hearing", document.terms)
        # Subject and body are separate phrases.
        self.assertNotIn("lanes zoning", document.terms)

    def test_merges_plurals_under_the_most_common_written_form(self) -> None:
        texts = ["New speed humps", "More speed humps", "One speed hump"]
        newsletters = [
            NewsletterRecord(
                id=f"n{index}",
                received_date=date(2026, 3, 4),
                source_id=None,
                subject="",
                plain_text=text,
            )
            for index, text in enumerate(texts)
        ]
        documents = build_newsletter_terms(newsletters, {})
        self.assertTrue(all("speed humps" in document.terms for document in documents))
        self.assertTrue(
            all("speed hump" not in document.terms for document in documents)
        )


class TestVocabulary(unittest.TestCase):
    def test_counts_newsletters_not_occurrences(self) -> None:
        counts = count_newsletters_per_term([doc({"a", "b"}), doc({"a"})])
        self.assertEqual(counts["a"], 2)
        self.assertEqual(counts["b"], 1)

    def test_select_vocabulary_applies_minimum(self) -> None:
        documents = [doc({"a", "b"}), doc({"a"}), doc({"a", "c"})]
        self.assertEqual(select_vocabulary(documents, 2), {"a"})


class TestBuildTermIndex(unittest.TestCase):
    def test_compact_bucket_counts(self) -> None:
        documents = [
            doc({"bike", "rare"}, source_id=2, month="2026-02"),
            doc({"bike"}, source_id=1, month="2026-01"),
            doc({"bike"}, source_id=1, month="2026-01"),
        ]
        index = build_term_index(documents, {"bike"})
        self.assertEqual(index["months"], ["2026-01", "2026-02"])
        self.assertEqual(index["buckets"], [[1, 0], [2, 1]])
        self.assertEqual(index["terms"], {"bike": [0, 2, 1, 1]})

    def test_skips_newsletters_without_source(self) -> None:
        index = build_term_index([doc({"bike"}, source_id=None)], {"bike"})
        self.assertEqual(index, {"months": [], "buckets": [], "terms": {}})


class TestSmoothedShare(unittest.TestCase):
    def test_never_zero_and_close_to_raw_share_for_large_counts(self) -> None:
        self.assertGreater(smoothed_share(0, 10), 0)
        self.assertAlmostEqual(smoothed_share(500, 1000), 0.5)


class TestNameTokens(unittest.TestCase):
    def test_collects_name_words_per_ward(self) -> None:
        tokens = build_name_tokens_by_ward(
            [
                SourceRecord(1, "Pat Dowell", "3", "alderman"),
                SourceRecord(2, "Mayor", None, "mayor"),
            ]
        )
        self.assertEqual(tokens, {"3": {"pat", "dowell"}})

    def test_term_mentions_name(self) -> None:
        self.assertTrue(term_mentions_name("alderman dowell", {"dowell"}))
        self.assertFalse(term_mentions_name("bronzeville", {"dowell"}))

    def test_term_mentions_name_in_another_plural_form(self) -> None:
        # "Burns" and "burn" fold together, so either written form names the alderman.
        self.assertTrue(term_mentions_name("burn", {"burns"}))
        self.assertTrue(term_mentions_name("alderman hopkins", {"hopkins"}))


class TestDistinctiveTerms(unittest.TestCase):
    def setUp(self) -> None:
        # Ward 1: "wicker" in 60%, "signature" footer in 80%, "park" less than ward 2.
        ward_one = [doc({"wicker", "park", "city", "signature"}, ward="1")] * 3
        ward_one += [
            doc({"park", "city", "signature"}, ward="1"),
            doc({"city"}, ward="1"),
        ]
        ward_two = [doc({"city", "park"}, ward="2")] * 5
        self.documents = ward_one + ward_two
        self.vocabulary = {"wicker", "park", "city", "signature", "dowell"}

    def compute(self, **overrides: Any) -> dict[str, list[dict[str, Any]]]:
        params: dict[str, Any] = {
            "name_tokens_by_ward": {},
            "top_n": 10,
            "min_ward_newsletters": 2,
            "min_term_newsletters_in_ward": 2,
            "max_ward_share": 0.9,
            "min_nested_term_similarity": 0.8,
        }
        params.update(overrides)
        return compute_distinctive_terms(self.documents, self.vocabulary, **params)

    def test_ranks_ward_specific_terms_and_excludes_shared_terms(self) -> None:
        result = self.compute()
        ward_one_terms = [item["term"] for item in result["1"]]
        self.assertEqual(ward_one_terms, ["signature", "wicker"])
        self.assertNotIn("city", ward_one_terms)
        self.assertNotIn(
            "park", [item["term"] for item in result["2"]] + ward_one_terms
        )

    def test_skips_boilerplate_above_max_ward_share(self) -> None:
        result = self.compute(max_ward_share=0.75)
        self.assertNotIn("signature", [item["term"] for item in result["1"]])

    def test_skips_terms_with_own_source_names(self) -> None:
        result = self.compute(name_tokens_by_ward={"1": {"wicker"}})
        self.assertNotIn("wicker", [item["term"] for item in result["1"]])

    def test_omits_small_wards(self) -> None:
        self.assertNotIn("1", self.compute(min_ward_newsletters=6))

    def test_terms_from_the_same_newsletters_are_one_entry(self) -> None:
        # "wicker park" is in exactly the newsletters "wicker" is in.
        self.documents = [
            doc(item.terms | {"wicker park"}, ward=item.ward)
            if "wicker" in item.terms
            else item
            for item in self.documents
        ]
        self.vocabulary.add("wicker park")
        related = {item["term"]: item["related_terms"] for item in self.compute()["1"]}
        self.assertEqual(related, {"signature": 0, "wicker park": 1})

    def test_overlapping_unrelated_terms_stay_apart(self) -> None:
        # "signature" (4 newsletters) and "wicker" (3 of those 4): Jaccard 0.75
        # but not one phrase, so they stay apart even at a lower threshold.
        result = self.compute(min_nested_term_similarity=0.5)["1"]
        self.assertEqual([item["related_terms"] for item in result], [0, 0])

    def test_skips_terms_with_filler_words(self) -> None:
        self.documents = [
            doc(item.terms | {"stay informed"}, ward=item.ward)
            if "wicker" in item.terms
            else item
            for item in self.documents
        ]
        self.vocabulary.add("stay informed")
        terms = [item["term"] for item in self.compute()["1"]]
        self.assertNotIn("stay informed", terms)
        self.assertIn("wicker", terms)

    def test_score_fields(self) -> None:
        item = score_distinctive_term("wicker", 4, 5, 0, 5)
        self.assertEqual(item.ward_share, 0.8)
        self.assertEqual(item.rest_share, 0.0)
        self.assertGreater(item.lift, 1)
        self.assertGreater(item.score, 0)


class TestSelectLatestCompleteMonth(unittest.TestCase):
    def test_excludes_current_month(self) -> None:
        months = ["2026-08", "2026-09", "2026-10"]
        self.assertEqual(select_latest_complete_month(months, "2026-10"), "2026-09")

    def test_uses_last_data_month_when_data_stops_early(self) -> None:
        self.assertEqual(
            select_latest_complete_month(["2026-05"], "2026-10"), "2026-05"
        )

    def test_none_when_no_complete_month(self) -> None:
        self.assertIsNone(select_latest_complete_month(["2026-10"], "2026-10"))


class TestRisingTerms(unittest.TestCase):
    """Wards 1-6 send every month; the latest month is 2026-09."""

    def setUp(self) -> None:
        wards = [str(ward) for ward in range(1, 7)]
        documents = [
            doc({"budget"}, ward=ward, month=month)
            for month in ("2026-06", "2026-07", "2026-08", "2026-09")
            for ward in wards
        ]
        # Six wards newly mention "senior fest"; one ward did in July.
        documents += [doc({"senior fest"}, ward=w, month="2026-09") for w in wards]
        documents.append(doc({"senior fest"}, ward="1", month="2026-07"))
        # One ward sends "solo" ten times: many newsletters, but one ward.
        documents += [doc({"solo"}, ward="1", month="2026-09") for _ in range(10)]
        # Five wards mention "labor" and "labor day" together.
        for ward in wards[:5]:
            documents.append(doc({"labor day", "labor"}, ward=ward, month="2026-09"))
        documents.append(doc({"orphan"}, ward=None, month="2026-09"))
        self.documents = documents
        self.vocabulary = {"budget", "senior fest", "solo", "labor day", "labor"}

    def compute(self, **overrides: Any) -> dict[str, Any]:
        params: dict[str, Any] = {
            "latest_month": "2026-09",
            "baseline_months": 3,
            "min_latest_wards": 3,
            "min_ward_gain": 2,
            "top_n": 10,
            "min_phrase_words": 1,
        }
        params.update(overrides)
        return compute_rising_terms(self.documents, self.vocabulary, **params)

    def terms(self, **overrides: Any) -> list[str]:
        return [item["term"] for item in self.compute(**overrides)["terms"]]

    def test_ranks_by_gain_in_wards_and_reports_denominators(self) -> None:
        result = self.compute()
        self.assertEqual(result["baseline_months"], ["2026-06", "2026-07", "2026-08"])
        self.assertEqual(result["latest_active_wards"], 6)
        self.assertEqual(result["baseline_active_wards"], [6, 6, 6])
        top = result["terms"][0]
        self.assertEqual(top["term"], "senior fest")
        self.assertEqual(top["latest_wards"], 6)
        # Median of 0, 1, 0 wards: one ward's July mention does not set the baseline.
        self.assertEqual(top["baseline_month_wards"], [0, 1, 0])
        self.assertEqual(top["baseline_wards"], 0)
        self.assertEqual(top["ward_gain"], 6)
        self.assertEqual(top["latest_newsletters"], 6)

    def test_phrases_only_when_min_phrase_words_is_two(self) -> None:
        self.assertEqual(self.terms(min_phrase_words=2), ["senior fest", "labor day"])

    def test_tags_recurring_calendar_events_as_seasonal(self) -> None:
        seasonal = {item["term"]: item["seasonal"] for item in self.compute()["terms"]}
        self.assertEqual(seasonal, {"senior fest": True, "labor": False})

    def test_phrases_with_filler_words_are_excluded(self) -> None:
        terms = {"accessible throughout", "tenant ordinance"}
        documents = [doc(terms, ward="1", month="2026-08")]
        documents += [doc(terms, ward=w, month="2026-09") for w in "1234"]
        result = compute_rising_terms(
            documents,
            terms,
            latest_month="2026-09",
            baseline_months=1,
            min_latest_wards=3,
            min_ward_gain=2,
            top_n=10,
            min_phrase_words=2,
        )
        self.assertEqual(
            [item["term"] for item in result["terms"]], ["tenant ordinance"]
        )

    def test_one_prolific_ward_cannot_make_a_trend(self) -> None:
        self.assertNotIn("solo", self.terms())

    def test_steady_terms_are_excluded(self) -> None:
        self.assertNotIn("budget", self.terms())

    def test_overlapping_terms_keep_only_the_highest_ranked(self) -> None:
        terms = self.terms()
        self.assertIn("labor", terms)
        self.assertNotIn("labor day", terms)

    def test_minimum_wards_and_gain(self) -> None:
        self.assertEqual(self.terms(min_latest_wards=7), [])
        self.assertEqual(self.terms(min_ward_gain=6), ["senior fest"])

    def test_empty_when_baseline_has_no_wards(self) -> None:
        result = self.compute(latest_month="2026-06")
        self.assertEqual(result["terms"], [])
        self.assertEqual(result["baseline_active_wards"], [0, 0, 0])

    def test_months_before_the_archive_are_not_counted_as_zero(self) -> None:
        # The archive starts in June: April and May had no active ward at all.
        documents = [doc({"fest"}, ward="1", month="2026-06")]
        documents += [doc({"fest"}, ward=w, month="2026-07") for w in "1234"]
        result = compute_rising_terms(
            documents,
            {"fest"},
            latest_month="2026-07",
            baseline_months=3,
            min_latest_wards=3,
            min_ward_gain=2,
            top_n=10,
            min_phrase_words=1,
        )
        self.assertEqual(result["baseline_active_wards"], [0, 0, 1])
        (fest,) = result["terms"]
        self.assertEqual(fest["baseline_month_wards"], [0, 0, 1])
        # Median of June alone, not of 0, 0, 1.
        self.assertEqual(fest["baseline_wards"], 1)
        self.assertEqual(fest["ward_gain"], 3)


class TestContainsFillerWord(unittest.TestCase):
    def test_any_word_in_any_plural_form(self) -> None:
        self.assertTrue(contains_filler_word("chicago residents"))
        self.assertTrue(contains_filler_word("next weeks"))
        self.assertFalse(contains_filler_word("tenant ordinance"))


class TestIsRisingCandidate(unittest.TestCase):
    def test_requires_min_phrase_words(self) -> None:
        self.assertFalse(is_rising_candidate("fall", min_phrase_words=2))
        self.assertTrue(is_rising_candidate("tenant ordinance", min_phrase_words=2))
        self.assertTrue(is_rising_candidate("fall", min_phrase_words=1))

    def test_rejects_phrases_with_filler_words_in_any_plural_form(self) -> None:
        for term in ("accessible throughout", "next week", "two weeks"):
            self.assertFalse(is_rising_candidate(term, min_phrase_words=2), term)
        self.assertFalse(is_rising_candidate("chicago residents", min_phrase_words=2))
