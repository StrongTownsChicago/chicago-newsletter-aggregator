"""Unit tests for analytics/terms.py term metrics."""

import unittest
from datetime import date

from analytics.records import NewsletterRecord, SourceRecord
from analytics.terms import (
    NewsletterTerms,
    build_name_tokens_by_ward,
    build_newsletter_terms,
    build_term_index,
    compute_distinctive_terms,
    compute_rising_terms,
    count_newsletters_per_term,
    score_distinctive_term,
    select_latest_complete_month,
    select_vocabulary,
    smoothed_share,
    term_mentions_name,
)


def doc(
    terms: set[str],
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
    def test_tokenizes_subject_and_body_and_attaches_bucket_keys(self):
        newsletter = NewsletterRecord(
            id="n1",
            received_date=date(2026, 3, 4),
            source_id=5,
            subject="Bike lanes",
            plain_text="Zoning hearing",
            topics=None,
        )
        source = SourceRecord(id=5, name="A", ward="40", source_type="alderman")
        [document] = build_newsletter_terms([newsletter], {5: source})
        self.assertEqual(document.ward, "40")
        self.assertEqual(document.month, "2026-03")
        self.assertIn("bike lanes", document.terms)
        self.assertIn("zoning hearing", document.terms)
        # Subject and body are separate phrases.
        self.assertNotIn("lanes zoning", document.terms)

    def test_merges_plurals_under_the_most_common_written_form(self):
        texts = ["New speed humps", "More speed humps", "One speed hump"]
        newsletters = [
            NewsletterRecord(
                id=f"n{index}",
                received_date=date(2026, 3, 4),
                source_id=None,
                subject="",
                plain_text=text,
                topics=None,
            )
            for index, text in enumerate(texts)
        ]
        documents = build_newsletter_terms(newsletters, {})
        self.assertTrue(all("speed humps" in document.terms for document in documents))
        self.assertTrue(
            all("speed hump" not in document.terms for document in documents)
        )


class TestVocabulary(unittest.TestCase):
    def test_counts_newsletters_not_occurrences(self):
        counts = count_newsletters_per_term([doc({"a", "b"}), doc({"a"})])
        self.assertEqual(counts["a"], 2)
        self.assertEqual(counts["b"], 1)

    def test_select_vocabulary_applies_minimum(self):
        documents = [doc({"a", "b"}), doc({"a"}), doc({"a", "c"})]
        self.assertEqual(select_vocabulary(documents, 2), {"a"})


class TestBuildTermIndex(unittest.TestCase):
    def test_compact_bucket_counts(self):
        documents = [
            doc({"bike", "rare"}, source_id=2, month="2026-02"),
            doc({"bike"}, source_id=1, month="2026-01"),
            doc({"bike"}, source_id=1, month="2026-01"),
        ]
        index = build_term_index(documents, {"bike"})
        self.assertEqual(index["months"], ["2026-01", "2026-02"])
        self.assertEqual(index["buckets"], [[1, 0], [2, 1]])
        self.assertEqual(index["terms"], {"bike": [0, 2, 1, 1]})

    def test_skips_newsletters_without_source(self):
        index = build_term_index([doc({"bike"}, source_id=None)], {"bike"})
        self.assertEqual(index, {"months": [], "buckets": [], "terms": {}})


class TestSmoothedShare(unittest.TestCase):
    def test_never_zero_and_close_to_raw_share_for_large_counts(self):
        self.assertGreater(smoothed_share(0, 10), 0)
        self.assertAlmostEqual(smoothed_share(500, 1000), 0.5)


class TestNameTokens(unittest.TestCase):
    def test_collects_name_words_per_ward(self):
        tokens = build_name_tokens_by_ward(
            [
                SourceRecord(1, "Pat Dowell", "3", "alderman"),
                SourceRecord(2, "Mayor", None, "mayor"),
            ]
        )
        self.assertEqual(tokens, {"3": {"pat", "dowell"}})

    def test_term_mentions_name(self):
        self.assertTrue(term_mentions_name("alderman dowell", {"dowell"}))
        self.assertFalse(term_mentions_name("bronzeville", {"dowell"}))

    def test_term_mentions_name_in_another_plural_form(self):
        # "Burns" and "burn" fold together, so either written form names the alderman.
        self.assertTrue(term_mentions_name("burn", {"burns"}))
        self.assertTrue(term_mentions_name("alderman hopkins", {"hopkins"}))


class TestDistinctiveTerms(unittest.TestCase):
    def setUp(self):
        # Ward 1: "wicker" in 60%, "signature" footer in 80%, "park" less than ward 2.
        ward_one = [doc({"wicker", "park", "city", "signature"}, ward="1")] * 3
        ward_one += [
            doc({"park", "city", "signature"}, ward="1"),
            doc({"city"}, ward="1"),
        ]
        ward_two = [doc({"city", "park"}, ward="2")] * 5
        self.documents = ward_one + ward_two
        self.vocabulary = {"wicker", "park", "city", "signature", "dowell"}

    def compute(self, **overrides):
        params = {
            "name_tokens_by_ward": {},
            "top_n": 10,
            "min_ward_newsletters": 2,
            "min_term_newsletters_in_ward": 2,
            "max_ward_share": 0.9,
        }
        params.update(overrides)
        return compute_distinctive_terms(self.documents, self.vocabulary, **params)

    def test_ranks_ward_specific_terms_and_excludes_shared_terms(self):
        result = self.compute()
        ward_one_terms = [item["term"] for item in result["1"]]
        self.assertEqual(ward_one_terms, ["signature", "wicker"])
        self.assertNotIn("city", ward_one_terms)
        self.assertNotIn(
            "park", [item["term"] for item in result["2"]] + ward_one_terms
        )

    def test_skips_boilerplate_above_max_ward_share(self):
        result = self.compute(max_ward_share=0.75)
        self.assertNotIn("signature", [item["term"] for item in result["1"]])

    def test_skips_terms_with_own_source_names(self):
        result = self.compute(name_tokens_by_ward={"1": {"wicker"}})
        self.assertNotIn("wicker", [item["term"] for item in result["1"]])

    def test_omits_small_wards(self):
        self.assertNotIn("1", self.compute(min_ward_newsletters=6))

    def test_score_fields(self):
        item = score_distinctive_term("wicker", 4, 5, 0, 5)
        self.assertEqual(item.ward_share, 0.8)
        self.assertEqual(item.rest_share, 0.0)
        self.assertGreater(item.lift, 1)
        self.assertGreater(item.score, 0)


class TestSelectLatestCompleteMonth(unittest.TestCase):
    def test_excludes_current_month(self):
        months = ["2026-08", "2026-09", "2026-10"]
        self.assertEqual(select_latest_complete_month(months, "2026-10"), "2026-09")

    def test_uses_last_data_month_when_data_stops_early(self):
        self.assertEqual(
            select_latest_complete_month(["2026-05"], "2026-10"), "2026-05"
        )

    def test_none_when_no_complete_month(self):
        self.assertIsNone(select_latest_complete_month(["2026-10"], "2026-10"))


class TestRisingTerms(unittest.TestCase):
    def setUp(self):
        baseline = [
            doc({"budget"}, month="2026-08", source_id=i % 3) for i in range(10)
        ]
        latest = [
            doc({"budget", "senior fest"}, month="2026-09", source_id=i % 3)
            for i in range(6)
        ]
        latest += [doc({"solo"}, month="2026-09", source_id=9) for _ in range(6)]
        old = [doc({"senior fest"}, month="2025-01")]
        self.documents = baseline + latest + old
        self.vocabulary = {"budget", "senior fest", "solo"}

    def compute(self, **overrides):
        params = {
            "latest_month": "2026-09",
            "baseline_months": 2,
            "min_latest_newsletters": 3,
            "min_latest_sources": 2,
            "top_n": 10,
        }
        params.update(overrides)
        return compute_rising_terms(self.documents, self.vocabulary, **params)

    def test_ranks_new_terms_and_reports_window(self):
        result = self.compute()
        self.assertEqual(result["baseline_months"], ["2026-07", "2026-08"])
        self.assertEqual(result["latest_newsletters"], 12)
        self.assertEqual(result["baseline_newsletters"], 10)
        top = result["terms"][0]
        self.assertEqual(top["term"], "senior fest")
        self.assertEqual(top["latest_newsletters"], 6)
        self.assertEqual(top["latest_sources"], 3)
        self.assertEqual(top["baseline_newsletters"], 0)

    def test_falling_terms_are_excluded(self):
        terms = [item["term"] for item in self.compute()["terms"]]
        self.assertNotIn("budget", terms)

    def test_single_source_terms_are_excluded(self):
        terms = [item["term"] for item in self.compute()["terms"]]
        self.assertNotIn("solo", terms)

    def test_minimum_count_floor(self):
        self.assertEqual(self.compute(min_latest_newsletters=7)["terms"], [])

    def test_empty_when_baseline_has_no_newsletters(self):
        result = self.compute(latest_month="2025-01")
        self.assertEqual(result["terms"], [])
        self.assertEqual(result["baseline_newsletters"], 0)


if __name__ == "__main__":
    unittest.main()
