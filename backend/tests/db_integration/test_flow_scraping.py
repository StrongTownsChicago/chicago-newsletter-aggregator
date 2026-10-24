"""Archive scraping (cli.process_scraped_newsletters) into the real database."""

import io
from contextlib import redirect_stdout
from datetime import datetime
from typing import ClassVar
from unittest.mock import Mock, patch

import cli.process_scraped_newsletters as scraper_cli
from shared.dates import CHICAGO_TIMEZONE
from tests.db_integration.local_supabase import TEST_PASSWORD, LocalSupabaseTestCase
from tests.fixtures.mock_helpers import create_mock_requests_response
from tests.fixtures.newsletter_factory import insert_source
from tests.fixtures.user_factory import create_auth_user, insert_rule

ARCHIVE_URL = "https://us1.campaign-archive.com/home/?u=1&id=ward9"
ISSUES = {  # newsletter URL -> (archive date, subject)
    "https://mailchi.mp/ward9/issue-1": ("09/15/2026", "Ward 9 Update: Street Fair"),
    "https://mailchi.mp/ward9/issue-2": ("10/01/2026", "Ward 9 Update: Leaf Pickup"),
}
ARCHIVE_HTML = (
    '<ul id="archive-list">'
    + "".join(
        f'<li class="campaign">{date} - <a href="{url}" title="{subject}">{subject}</a></li>'
        for url, (date, subject) in ISSUES.items()
    )
    + "</ul>"
)


def fake_http_get(url: str, **_options: object) -> Mock:
    """The archive site: the archive page and one page per issue."""
    if url == ARCHIVE_URL:
        return create_mock_requests_response(text=ARCHIVE_HTML)
    _date, subject = ISSUES[url]
    return create_mock_requests_response(
        text=f"<html><head><title>{subject}</title></head>"
        f"<body><p>{subject}: details inside.</p></body></html>"
    )


class TestScrapeAllSources(LocalSupabaseTestCase):
    archived_source: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.archived_source = insert_source(
            cls.db,
            name="Ward 9 Office",
            ward_number=9,
            newsletter_archive_url=ARCHIVE_URL,
        )["id"]
        insert_source(cls.db, name="Ward 8 Office", ward_number=8)
        # A rule every newsletter matches: scraping must still queue nothing.
        user_id = create_auth_user(cls.db, "everything@example.test", TEST_PASSWORD)
        insert_rule(cls.db, user_id, name="Everything")

    def setUp(self) -> None:
        self.http_get = Mock(side_effect=fake_http_get)
        for patcher in (
            patch.object(scraper_cli.scraper.session, "get", self.http_get),
            patch.object(scraper_cli, "pause_politely"),
            patch.object(scraper_cli, "ENABLE_LLM", False),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def scrape(self) -> None:
        with redirect_stdout(io.StringIO()):
            scraper_cli.scrape_all_sources(self.db)

    def test_scrapes_archived_sources_once_and_queues_nothing(self) -> None:
        self.scrape()
        self.scrape()

        rows = self.rows("newsletters")
        self.assertCountEqual(
            [row["subject"] for row in rows],
            [subject for _date, subject in ISSUES.values()],
        )
        for row in rows:
            self.assertEqual(row["source_id"], self.archived_source)
            self.assertIsNone(row["email_uid"])
            self.assertIn("details inside", row["plain_text"])
        self.assertEqual(
            {call.args[0] for call in self.http_get.call_args_list},
            {ARCHIVE_URL, *ISSUES},
        )
        self.assertEqual(self.rows("notification_queue"), [])

    def test_received_date_is_the_archive_date_in_chicago(self) -> None:
        self.scrape()

        dates_by_subject = {
            row["subject"]: datetime.fromisoformat(row["received_date"])
            .astimezone(CHICAGO_TIMEZONE)
            .strftime("%m/%d/%Y")
            for row in self.rows("newsletters")
        }
        self.assertEqual(
            dates_by_subject,
            {subject: date for date, subject in ISSUES.values()},
        )
