"""Unit tests for cli/compute_analytics.py orchestration (no database)."""

import unittest
from datetime import date, datetime
from typing import ClassVar
from unittest.mock import patch

from analytics.facts import MIN_EXTRACTED_WORDS
from analytics.records import NewsletterRecord, SourceRecord
from cli.compute_analytics import (
    BOILERPLATE_MIN_SOURCE_NEWSLETTERS,
    LENS_MIN_MENTIONS,
    MATCH_LENSES_ON_CLEANED_TEXT,
    analyze_archive,
    compute_outputs,
    compute_site_outputs,
)


def make_newsletter(
    newsletter_id: str, day: date, source_id: int, text: str
) -> NewsletterRecord:
    return NewsletterRecord(
        id=newsletter_id,
        received_date=day,
        source_id=source_id,
        subject="Update",
        plain_text=text,
    )


class TestComputeOutputs(unittest.TestCase):
    def test_produces_every_output_file(self) -> None:
        sources = [
            SourceRecord(1, "Ada Alder", "1", "alderman"),
            SourceRecord(2, "Bo Alder", "2", "alderman"),
        ]
        newsletters = [
            make_newsletter("a", date(2026, 8, 3), 1, "Protected bike lanes"),
            make_newsletter("b", date(2026, 9, 3), 2, "Protected bike lanes"),
            # An October newsletter shows the snapshot holds all of September.
            make_newsletter("c", date(2026, 10, 2), 1, "Leaf pickup"),
        ]
        outputs = compute_outputs(
            analyze_archive(sources, newsletters, 2, datetime(2026, 10, 11))
        )

        self.assertEqual(
            set(outputs),
            {
                "metadata",
                "newsletters",
                "sources",
                "terms",
                "distinctive",
                "rising",
                "lenses",
            },
        )
        self.assertEqual(outputs["metadata"]["newsletter_count"], 3)
        self.assertEqual(len(outputs["newsletters"]["newsletters"]), 3)
        self.assertIn("bike lanes", outputs["terms"]["terms"])
        self.assertEqual(outputs["terms"]["min_newsletters"], 2)
        self.assertEqual(outputs["rising"]["latest_month"], "2026-09")

    def test_term_metrics_exclude_text_a_source_repeats_in_every_issue(self) -> None:
        sources = [SourceRecord(1, "Ada Alder", "1", "alderman")]
        footer = "Ada Alder | 1 Main St | Unsubscribe | Update Profile | Constant Contact Data Notice"
        newsletters = [
            make_newsletter(
                str(index),
                date(2026, 9, 1 + index),
                1,
                f"Zoning item {index}. {footer}",
            )
            for index in range(BOILERPLATE_MIN_SOURCE_NEWSLETTERS)
        ]
        outputs = compute_outputs(
            analyze_archive(sources, newsletters, 1, datetime(2026, 10, 11))
        )

        self.assertNotIn("data notice", outputs["terms"]["terms"])
        self.assertIn("zoning", outputs["terms"]["terms"])
        # Facts still describe the newsletter as received.
        fact_words = outputs["newsletters"]["newsletters"][0]["words"]
        self.assertEqual(fact_words, len(newsletters[0].plain_text.split()))

    def test_flags_each_newsletter_with_the_lenses_it_mentions(self) -> None:
        sources = [SourceRecord(1, "Ada Alder", "1", "alderman")]
        filler = "word " * MIN_EXTRACTED_WORDS
        mention = " ".join(["New speed humps."] * LENS_MIN_MENTIONS)
        newsletters = [
            make_newsletter("calming", date(2026, 9, 1), 1, f"{mention} {filler}"),
            make_newsletter("passing", date(2026, 9, 2), 1, f"A speed hump. {filler}"),
            # Image-only issue: too little text to say what it mentions.
            make_newsletter("image", date(2026, 9, 3), 1, mention),
        ]
        outputs = compute_outputs(
            analyze_archive(sources, newsletters, 1, datetime(2026, 10, 11))
        )

        lenses_by_id = {
            fact["id"]: fact["lenses"] for fact in outputs["newsletters"]["newsletters"]
        }
        self.assertIn("street_safety", lenses_by_id["calming"])
        self.assertEqual(lenses_by_id["passing"], [])
        self.assertEqual(lenses_by_id["image"], [])
        self.assertNotIn("topics", outputs["newsletters"]["newsletters"][0])

        summary = outputs["lenses"]
        self.assertEqual(summary["readable_newsletters"], 2)
        self.assertEqual(summary["min_mentions"], LENS_MIN_MENTIONS)
        street_safety = next(
            lens for lens in summary["lenses"] if lens["id"] == "street_safety"
        )
        self.assertEqual(street_safety["newsletters"], 1)

    @unittest.skipUnless(MATCH_LENSES_ON_CLEANED_TEXT, "lenses match raw text")
    def test_lenses_ignore_a_standing_block_repeated_in_every_issue(self) -> None:
        sources = [SourceRecord(1, "Ada Alder", "1", "alderman")]
        standing_block = (
            "Immigration resources: know your rights workshops for immigrant "
            "neighbors every week at the ward office on Main Street"
        )
        newsletters = [
            make_newsletter(
                str(index),
                date(2026, 9, 1 + index),
                1,
                f"Item {index} " + "word " * MIN_EXTRACTED_WORDS + standing_block,
            )
            for index in range(BOILERPLATE_MIN_SOURCE_NEWSLETTERS)
        ]
        outputs = compute_outputs(
            analyze_archive(sources, newsletters, 1, datetime(2026, 10, 11))
        )

        self.assertEqual(outputs["lenses"]["text"], "cleaned")
        for fact in outputs["newsletters"]["newsletters"]:
            self.assertNotIn("immigration", fact["lenses"])

    def test_handles_dataset_without_complete_month(self) -> None:
        sources = [SourceRecord(1, "Ada Alder", "1", "alderman")]
        newsletters = [make_newsletter("a", date(2026, 10, 3), 1, "Bike lanes")]
        outputs = compute_outputs(
            analyze_archive(sources, newsletters, 1, datetime(2026, 10, 11))
        )
        self.assertIsNone(outputs["rising"]["latest_month"])
        self.assertEqual(outputs["rising"]["terms"], [])


class TestComputeSiteOutputs(unittest.TestCase):
    sources: ClassVar = [
        SourceRecord(1, "Ada Alder", "1", "alderman"),
        SourceRecord(2, "Bo Alder", "2", "alderman"),
        SourceRecord(3, "Cy Alder", "3", "alderman"),
        SourceRecord(4, "Transit agency", None, "agency"),
    ]
    filler = "word " * MIN_EXTRACTED_WORDS
    mention = " ".join(["New speed humps."] * LENS_MIN_MENTIONS)

    def test_summarizes_wards_and_broad_complete_months(self) -> None:
        newsletters = [
            make_newsletter("a", date(2026, 8, 3), 1, self.filler),
            make_newsletter("b", date(2026, 9, 3), 1, f"{self.mention} {self.filler}"),
            make_newsletter("c", date(2026, 9, 4), 2, f"{self.mention} {self.filler}"),
            # The current month is incomplete, so it gets no report yet.
            make_newsletter("d", date(2026, 10, 2), 1, self.filler),
            make_newsletter("e", date(2026, 10, 2), 2, self.filler),
        ]
        with patch("cli.compute_analytics.REPORT_MIN_SENDING_WARDS", 2):
            outputs = compute_site_outputs(
                analyze_archive(self.sources, newsletters, 1, datetime(2026, 10, 11))
            )

        glance = outputs["ward-glance"]
        self.assertEqual(glance["data_through"], "2026-10-02")
        self.assertEqual(glance["latest_month"], "2026-09")
        self.assertEqual(set(glance["wards"]), {"1", "2"})
        self.assertEqual(
            glance["topics"]["street_safety"], "Street safety & traffic calming"
        )
        ward_one_topics = glance["wards"]["1"]["topics"]
        self.assertIn(
            {"id": "street_safety", "newsletters": 1, "city_wards": 2}, ward_one_topics
        )

        reports = outputs["monthly-reports"]["reports"]
        self.assertEqual([report["month"] for report in reports], ["2026-09"])
        self.assertEqual(reports[0]["sending_wards"], ["1", "2"])
        street_safety = next(
            topic for topic in reports[0]["topics"] if topic["id"] == "street_safety"
        )
        self.assertEqual(street_safety["wards"], 2)

    def test_without_a_complete_month_both_summaries_are_empty(self) -> None:
        newsletters = [make_newsletter("a", date(2026, 10, 3), 1, self.filler)]
        outputs = compute_site_outputs(
            analyze_archive(self.sources, newsletters, 1, datetime(2026, 10, 11))
        )
        self.assertEqual(outputs["ward-glance"]["wards"], {})
        self.assertIsNone(outputs["ward-glance"]["latest_month"])
        self.assertEqual(outputs["monthly-reports"]["reports"], [])

    def test_a_stale_snapshot_leaves_its_newest_month_out(self) -> None:
        # Refreshed mid-September but computed in October: September is partial.
        newsletters = [
            make_newsletter("a", date(2026, 8, 3), 1, self.filler),
            make_newsletter("b", date(2026, 8, 4), 2, self.filler),
            make_newsletter("c", date(2026, 9, 14), 1, self.filler),
            make_newsletter("d", date(2026, 9, 15), 2, self.filler),
        ]
        with patch("cli.compute_analytics.REPORT_MIN_SENDING_WARDS", 2):
            outputs = compute_site_outputs(
                analyze_archive(self.sources, newsletters, 1, datetime(2026, 10, 11))
            )
        self.assertEqual(outputs["ward-glance"]["latest_month"], "2026-08")
        self.assertEqual(
            [report["month"] for report in outputs["monthly-reports"]["reports"]],
            ["2026-08"],
        )
