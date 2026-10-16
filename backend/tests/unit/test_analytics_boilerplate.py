"""Unit tests for analytics/boilerplate.py per-source boilerplate removal."""

import unittest
from datetime import date

from analytics.boilerplate import (
    REMOVED_SPAN_REPLACEMENT,
    SHINGLE_WORDS,
    Word,
    build_shingles,
    find_covered_spans,
    find_recurring_shingles,
    find_words,
    remove_source_boilerplate,
    remove_spans,
)
from analytics.records import NewsletterRecord
from analytics.text import extract_terms

FOOTER = (
    "Alderman Office | 123 Main St | Chicago, IL 60601 US "
    "Unsubscribe | Update Profile | Constant Contact Data Notice"
)


def make_newsletter(
    newsletter_id: str, plain_text: str, source_id: int | None = 1
) -> NewsletterRecord:
    return NewsletterRecord(
        id=newsletter_id,
        received_date=date(2026, 3, 1),
        source_id=source_id,
        subject="Update",
        plain_text=plain_text,
    )


class TestFindWords(unittest.TestCase):
    def test_lowercases_words_and_keeps_original_positions(self) -> None:
        text = "Hello, Ward Office"
        words = find_words(text)
        self.assertEqual([word.text for word in words], ["hello", "ward", "office"])
        self.assertEqual(text[words[1].start : words[1].end], "Ward")

    def test_skips_urls_and_emails_without_shifting_positions(self) -> None:
        text = "Visit https://x.org/track?id=9 or mail info@ward.org today"
        words = find_words(text)
        self.assertEqual(
            [word.text for word in words], ["visit", "or", "mail", "today"]
        )
        self.assertEqual(text[words[-1].start : words[-1].end], "today")

    def test_unifies_curly_apostrophes(self) -> None:
        self.assertEqual([word.text for word in find_words("Ward’s")], ["ward's"])


class TestBuildShingles(unittest.TestCase):
    def test_returns_each_run_of_consecutive_words(self) -> None:
        words = find_words("one two three four")
        self.assertEqual(build_shingles(words, 3), ["one two three", "two three four"])

    def test_text_shorter_than_a_shingle_has_none(self) -> None:
        self.assertEqual(build_shingles(find_words("one two"), 3), [])


class TestFindRecurringShingles(unittest.TestCase):
    def test_keeps_shingles_at_or_above_the_share(self) -> None:
        recurring = find_recurring_shingles(
            [["footer", "a"], ["footer", "b"], ["c"], ["d"]], min_share_percent=50
        )
        self.assertEqual(recurring, {"footer"})

    def test_counts_a_shingle_once_per_newsletter(self) -> None:
        recurring = find_recurring_shingles(
            [["echo", "echo", "echo"], ["x"], ["y"]], min_share_percent=50
        )
        self.assertEqual(recurring, set())

    def test_share_threshold_is_exact_at_round_numbers(self) -> None:
        # 30% of 10 is exactly 3, so a shingle in 3 of 10 newsletters recurs.
        shingles = [["standing"]] * 3 + [["other"]] * 7
        self.assertIn("standing", find_recurring_shingles(shingles, 30))


class TestFindCoveredSpans(unittest.TestCase):
    def test_merges_overlapping_shingles_into_one_span(self) -> None:
        words = [Word(0, 1, "a"), Word(2, 3, "b"), Word(4, 5, "c"), Word(6, 7, "d")]
        shingles = build_shingles(words, 2)  # "a b", "b c", "c d"
        spans = find_covered_spans(words, shingles, {"a b", "b c"}, 2)
        self.assertEqual(spans, [(0, 5)])

    def test_separate_stretches_give_separate_spans(self) -> None:
        words = [Word(0, 1, "a"), Word(2, 3, "b"), Word(4, 5, "c"), Word(6, 7, "d")]
        shingles = build_shingles(words, 1)
        spans = find_covered_spans(words, shingles, {"a", "d"}, 1)
        self.assertEqual(spans, [(0, 1), (6, 7)])

    def test_nothing_recurring_gives_no_spans(self) -> None:
        words = find_words("plain unique content")
        self.assertEqual(
            find_covered_spans(words, build_shingles(words, 2), set(), 2), []
        )


class TestRemoveSpans(unittest.TestCase):
    def test_replaces_spans_with_a_phrase_boundary(self) -> None:
        self.assertEqual(
            remove_spans("keep CUT keep CUT end", [(5, 8), (14, 17)]),
            f"keep {REMOVED_SPAN_REPLACEMENT} keep {REMOVED_SPAN_REPLACEMENT} end",
        )

    def test_no_spans_returns_text_unchanged(self) -> None:
        self.assertEqual(remove_spans("unchanged", []), "unchanged")


class TestRemoveSourceBoilerplate(unittest.TestCase):
    def test_removes_a_footer_repeated_across_a_sources_issues(self) -> None:
        newsletters = [
            make_newsletter(str(index), f"Zoning hearing on item {index}. {FOOTER}")
            for index in range(10)
        ]
        cleaned = remove_source_boilerplate(
            newsletters, min_share_percent=30, min_source_newsletters=10
        )
        for newsletter in cleaned:
            terms = extract_terms(newsletter.plain_text)
            self.assertNotIn("data notice", terms)
            self.assertNotIn("constant contact", terms)
            self.assertIn("zoning hearing", terms)

    def test_matches_a_block_whose_links_and_formatting_differ(self) -> None:
        rendered = [
            "**Senator Durbin's website** (https://track.example/a?u=1) and "
            "Senator Duckworth's website for federal updates",
            "Senator Durbin’s website (https://track.example/b?u=2) and "
            "Senator Duckworth’s website for federal updates",
        ]
        newsletters = [
            make_newsletter(str(index), f"Unique item {index}.\n{rendered[index % 2]}")
            for index in range(10)
        ]
        cleaned = remove_source_boilerplate(newsletters, 30, 10)
        self.assertTrue(
            all("durbin" not in newsletter.plain_text.lower() for newsletter in cleaned)
        )

    def test_removing_a_span_does_not_join_the_words_around_it(self) -> None:
        repeated = "standing block with exactly enough words to form a shingle"
        newsletters = [make_newsletter("0", f"protected bike {repeated} lane closures")]
        newsletters += [
            make_newsletter(str(index), f"issue {index} {repeated} other text")
            for index in range(1, 10)
        ]
        [first, *_] = remove_source_boilerplate(newsletters, 30, 10)
        terms = extract_terms(first.plain_text)
        self.assertNotIn("standing", terms)
        self.assertIn("protected bike", terms)
        self.assertIn("lane closures", terms)
        self.assertNotIn("bike lane", terms)

    def test_keeps_text_below_the_share_threshold(self) -> None:
        announcement = "Senior fest returns on Saturday at the park fieldhouse"
        newsletters = [
            make_newsletter(
                str(index),
                f"Issue {index} news. {announcement if index < 2 else ''}",
            )
            for index in range(10)
        ]
        cleaned = remove_source_boilerplate(newsletters, 30, 10)
        self.assertEqual(cleaned, newsletters)

    def test_small_sources_are_left_untouched(self) -> None:
        newsletters = [make_newsletter(str(index), FOOTER) for index in range(9)]
        self.assertEqual(remove_source_boilerplate(newsletters, 30, 10), newsletters)

    def test_counts_recurrence_within_each_source_separately(self) -> None:
        own_footer = [make_newsletter(f"a{index}", FOOTER, 1) for index in range(10)]
        other_source = [
            make_newsletter(
                f"b{index}",
                f"Only once here {index}. {FOOTER}"
                if index == 0
                else f"Different text number {index}",
                2,
            )
            for index in range(10)
        ]
        cleaned = remove_source_boilerplate(own_footer + other_source, 30, 10)
        self.assertNotIn("Constant Contact", cleaned[0].plain_text)
        self.assertIn("Constant Contact", cleaned[10].plain_text)

    def test_newsletters_without_a_source_keep_their_text_and_order(self) -> None:
        newsletters = [make_newsletter(str(index), FOOTER, None) for index in range(12)]
        self.assertEqual(remove_source_boilerplate(newsletters, 30, 10), newsletters)

    def test_short_newsletters_without_a_full_shingle_are_kept(self) -> None:
        newsletters = [make_newsletter(str(index), "Short note") for index in range(10)]
        self.assertLess(len("Short note".split()), SHINGLE_WORDS)
        self.assertEqual(remove_source_boilerplate(newsletters, 30, 10), newsletters)


if __name__ == "__main__":
    unittest.main()
