"""Characterization tests for archive scraping (cli.process_scraped_newsletters).

The scraper, Supabase, the LLM and the politeness delays are mocked. The tests
pin what gets stored, skipped and counted, and where the run keeps going.
"""

import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from typing import Any, cast
from unittest.mock import MagicMock, Mock, call, patch

from supabase import Client

import cli.process_scraped_newsletters as scraper_cli
from tests.fixtures.fake_supabase import ExecutedQuery, FakeSupabase

SOURCE = {"name": "Ward 1 Office", "newsletter_archive_url": "https://archive.test"}


def link(number: int) -> dict[str, str]:
    return {
        "url": f"https://archive.test/{number}",
        "title": f"Issue {number}",
        "date_str": "Oct 1, 2026",
    }


def content(number: int, archive_date: str = "October 1, 2026") -> dict[str, str]:
    return {
        "subject": f"Issue {number}",
        "html_content": f"<p>Issue {number}</p>",
        "plain_text": f"Issue {number} text",
        "archive_date_str": archive_date,
    }


class ScraperTestCase(unittest.TestCase):
    """Runs the scraper CLI against a fake archive and database."""

    def setUp(self) -> None:
        self.existing_subjects: set[str] = set()
        self.db = FakeSupabase(
            {
                ("sources", "select"): [SOURCE],
                ("newsletters", "select"): self.answer_existing,
            }
        )
        self.scraper = Mock()
        self.contents: dict[str, dict[str, str] | None] = {}
        self.scraper.fetch_newsletter_content.side_effect = (
            lambda url, *_: self.contents[url]
        )
        self.sleep = Mock()
        self.print_summary = Mock()
        for target, value in {
            "scraper": self.scraper,
            "ENABLE_LLM": False,
            "print_summary": self.print_summary,
        }.items():
            patcher = patch.object(scraper_cli, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        sleep_patcher = patch("cli.process_scraped_newsletters.time.sleep", self.sleep)
        sleep_patcher.start()
        self.addCleanup(sleep_patcher.stop)
        self.output = io.StringIO()

    def answer_existing(self, query: ExecutedQuery) -> list[dict[str, Any]]:
        subject = query.equal_filters["subject"]
        return [{"id": "existing"}] if subject in self.existing_subjects else []

    def archive(self, *items: tuple[int, dict[str, str] | None]) -> None:
        self.scraper.extract_newsletter_links.return_value = [
            link(number) for number, _ in items
        ]
        self.contents = {link(number)["url"]: item for number, item in items}

    def run_scrape(self, limit: int | None = None) -> str:
        with redirect_stdout(self.output):
            scraper_cli.process_scraped_newsletters(cast(Client, self.db), 1, limit)
        return self.output.getvalue()

    def stored(self) -> list[dict[str, Any]]:
        return [query.payload for query in self.db.writes("newsletters")]


class TestProcessScrapedNewsletters(ScraperTestCase):
    def test_stores_a_new_newsletter_with_its_archive_date(self) -> None:
        self.archive((1, content(1)))

        output = self.run_scrape()

        self.scraper.extract_newsletter_links.assert_called_once_with(
            "https://archive.test"
        )
        self.scraper.fetch_newsletter_content.assert_called_once_with(
            "https://archive.test/1", "Issue 1", "Oct 1, 2026"
        )
        self.assertEqual(
            self.stored(),
            [
                {
                    "source_id": 1,
                    "received_date": "2026-10-01T00:00:00-05:00",
                    "subject": "Issue 1",
                    "from_email": None,
                    "to_email": None,
                    "email_uid": None,
                    "raw_html": "<p>Issue 1</p>",
                    "plain_text": "Issue 1 text",
                }
            ],
        )
        self.print_summary.assert_called_once_with(1, 0, 0)
        self.assertIn("Source: Ward 1 Office", output)
        self.assertIn("[1/1] Oct 1, 2026 - Issue 1", output)
        self.assertIn("  ✓ Retrieved 12 chars", output)

    def test_duplicate_check_uses_source_and_subject(self) -> None:
        self.archive((1, content(1)))

        self.run_scrape()

        duplicate_check = self.db.executed[1]
        self.assertEqual(duplicate_check.table, "newsletters")
        self.assertEqual(
            duplicate_check.equal_filters, {"source_id": 1, "subject": "Issue 1"}
        )

    def test_unparseable_archive_date_falls_back_to_now(self) -> None:
        self.archive((1, content(1, archive_date="")))

        self.run_scrape()

        (row,) = self.stored()
        self.assertGreater(
            datetime.fromisoformat(row["received_date"]),
            datetime.fromisoformat("2026-01-01T00:00:00+00:00"),
        )

    def test_duplicate_is_skipped_after_a_delay(self) -> None:
        self.existing_subjects.add("Issue 1")
        self.archive((1, content(1)), (2, content(2)))

        output = self.run_scrape()

        self.assertEqual([row["subject"] for row in self.stored()], ["Issue 2"])
        self.print_summary.assert_called_once_with(1, 1, 0)
        self.assertEqual(self.sleep.call_count, 2)
        self.assertIn("  ⊘ Duplicate", output)

    def test_missing_content_counts_as_failed(self) -> None:
        self.archive((1, None), (2, content(2)))

        output = self.run_scrape()

        self.assertEqual([row["subject"] for row in self.stored()], ["Issue 2"])
        self.print_summary.assert_called_once_with(1, 0, 1)
        self.assertIn("  ✗ Failed to fetch content", output)

    def test_limit_keeps_only_the_first_links(self) -> None:
        self.archive((1, content(1)), (2, content(2)), (3, content(3)))

        self.run_scrape(limit=2)

        self.assertEqual(
            [row["subject"] for row in self.stored()], ["Issue 1", "Issue 2"]
        )

    def test_insert_failure_counts_as_failed_and_continues(self) -> None:
        self.db.responses[("newsletters", "insert")] = RuntimeError("db down")
        self.archive((1, content(1)), (2, content(2)))

        output = self.run_scrape()

        self.print_summary.assert_called_once_with(0, 0, 2)
        self.assertIn("  ✗ Error: db down", output)

    def test_unknown_source_raises(self) -> None:
        self.db.responses[("sources", "select")] = []

        with self.assertRaisesRegex(ValueError, "Source ID 1 not found"):
            self.run_scrape()

    def test_source_without_archive_raises(self) -> None:
        self.db.responses[("sources", "select")] = [
            {"name": "Ward 1 Office", "newsletter_archive_url": None}
        ]

        with self.assertRaisesRegex(ValueError, "has no newsletter_archive_url"):
            self.run_scrape()


@patch("processing.llm_processor.extract_newsletter_metadata")
class TestLlmStep(ScraperTestCase):
    def setUp(self) -> None:
        super().setUp()
        for target, value in {"ENABLE_LLM": True, "OLLAMA_MODEL": "test-model"}.items():
            patcher = patch.object(scraper_cli, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_llm_metadata_is_stored_without_a_delay(self, extract: MagicMock) -> None:
        extract.return_value = {"topics": ["bike_lanes"], "summary": "Short."}
        self.archive((1, content(1)))

        self.run_scrape()

        (row,) = self.stored()
        self.assertEqual(row["topics"], ["bike_lanes"])
        self.assertEqual(extract.call_args.args[1], "test-model")
        self.sleep.assert_not_called()

    def test_llm_failure_still_stores(self, extract: MagicMock) -> None:
        extract.side_effect = RuntimeError("model offline")
        self.archive((1, content(1)))

        output = self.run_scrape()

        self.assertEqual(len(self.stored()), 1)
        self.print_summary.assert_called_once_with(1, 0, 0)
        self.assertIn("  ⚠ LLM processing failed: model offline", output)


class TestScrapeAllSources(unittest.TestCase):
    def setUp(self) -> None:
        self.db = FakeSupabase(
            {
                ("sources", "select"): [
                    {"id": 1, "name": "One"},
                    {"id": 2, "name": "Two"},
                ]
            }
        )

    @patch.object(scraper_cli, "process_scraped_newsletters")
    def test_scrapes_each_archived_source_and_survives_a_failure(
        self, process: MagicMock
    ) -> None:
        process.side_effect = [RuntimeError("archive moved"), None]
        output = io.StringIO()

        with redirect_stdout(output):
            scraper_cli.scrape_all_sources(cast(Client, self.db))

        self.assertEqual(
            process.call_args_list,
            [
                call(self.db, source_id=1, limit=None),
                call(self.db, source_id=2, limit=None),
            ],
        )
        self.assertIn("✗ Error processing source One: archive moved", output.getvalue())
        self.assertIn(("not_", (), {}), self.db.executed[0].calls)

    @patch.object(scraper_cli, "process_scraped_newsletters")
    def test_no_archived_sources_scrapes_nothing(self, process: MagicMock) -> None:
        self.db.responses[("sources", "select")] = []
        output = io.StringIO()

        with redirect_stdout(output):
            scraper_cli.scrape_all_sources(cast(Client, self.db))

        process.assert_not_called()
        self.assertIn(
            "No sources with newsletter_archive_url found.", output.getvalue()
        )


if __name__ == "__main__":
    unittest.main()
