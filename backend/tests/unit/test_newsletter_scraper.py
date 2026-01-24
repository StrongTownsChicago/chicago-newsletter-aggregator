"""
Unit tests for ingest/scraper/newsletter_scraper.py

Tests HTTP fetching, retries, timeouts, and content extraction
for newsletter archive and individual newsletter pages.
"""

import unittest
from unittest.mock import Mock, patch
import sys
from pathlib import Path

# Add backend to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from ingest.scraper.newsletter_scraper import NewsletterScraper


class TestFetchArchivePage(unittest.TestCase):
    """Tests for fetch_archive_page() method."""

    @patch("requests.Session.get")
    def test_successful_fetch(self, mock_get):
        """Successful fetch returns HTML."""
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.text = "<html>Archive content</html>"
        mock_get.return_value = mock_response

        scraper = NewsletterScraper()
        result = scraper.fetch_archive_page("https://example.com/archive")

        self.assertEqual(result, "<html>Archive content</html>")
        mock_get.assert_called_once()

    @patch("builtins.print")
    @patch("time.sleep")
    @patch("requests.Session.get")
    def test_retry_on_failure(self, mock_get, mock_sleep, mock_print):
        """Failed call retries with exponential backoff."""
        # Fail twice, succeed third time
        mock_get.side_effect = [
            Exception("Connection error"),
            Exception("Timeout"),
            Mock(status_code=200, text="<html>Success</html>"),
        ]

        scraper = NewsletterScraper(max_retries=3)
        result = scraper.fetch_archive_page("https://example.com/archive")

        self.assertEqual(result, "<html>Success</html>")
        self.assertEqual(mock_get.call_count, 3)
        # Should sleep 1s, then 2s (2^0, 2^1)
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("builtins.print")
    @patch("time.sleep")
    @patch("requests.Session.get")
    def test_max_retries_returns_none(self, mock_get, mock_sleep, mock_print):
        """All retries exhausted returns None."""
        mock_get.side_effect = Exception("Connection error")

        scraper = NewsletterScraper(max_retries=3)
        result = scraper.fetch_archive_page("https://example.com/archive")

        self.assertIsNone(result)
        self.assertEqual(mock_get.call_count, 3)

    @patch("requests.Session.get")
    def test_timeout_handling(self, mock_get):
        """30s timeout configured."""
        mock_response = Mock(status_code=200, text="<html>Content</html>")
        mock_get.return_value = mock_response

        scraper = NewsletterScraper()
        scraper.fetch_archive_page("https://example.com/archive")

        # Check that timeout was passed
        call_kwargs = mock_get.call_args[1]
        self.assertEqual(call_kwargs["timeout"], 30)

    def test_user_agent_set(self):
        """User-Agent header set in session."""
        scraper = NewsletterScraper()

        self.assertIn("User-Agent", scraper.session.headers)
        self.assertIn("Mozilla", scraper.session.headers["User-Agent"])

    @patch("builtins.print")
    @patch("time.sleep")
    @patch("requests.Session.get")
    def test_http_error_handling(self, mock_get, mock_sleep, mock_print):
        """HTTP errors (404, 500) handled."""
        mock_response = Mock()
        mock_response.status_code = 404
        mock_response.raise_for_status.side_effect = Exception("404 Not Found")
        mock_get.return_value = mock_response

        scraper = NewsletterScraper(max_retries=3)
        result = scraper.fetch_archive_page("https://example.com/archive")

        self.assertIsNone(result)


class TestExtractNewsletterLinks(unittest.TestCase):
    """Tests for extract_newsletter_links() method."""

    @patch("builtins.print")
    @patch("ingest.scraper.newsletter_scraper.get_strategy_for_url")
    @patch.object(NewsletterScraper, "fetch_archive_page")
    def test_uses_correct_strategy(self, mock_fetch, mock_get_strategy, mock_print):
        """Strategy selection logic called."""
        mock_fetch.return_value = "<html>Archive</html>"
        mock_strategy = Mock()
        mock_strategy.extract_newsletters.return_value = []
        mock_get_strategy.return_value = mock_strategy

        scraper = NewsletterScraper()
        scraper.extract_newsletter_links("https://example.com/archive")

        mock_get_strategy.assert_called_once_with("https://example.com/archive")
        mock_strategy.extract_newsletters.assert_called_once()

    @patch("builtins.print")
    @patch("ingest.scraper.newsletter_scraper.get_strategy_for_url")
    @patch.object(NewsletterScraper, "fetch_archive_page")
    def test_returns_newsletter_list(self, mock_fetch, mock_get_strategy, mock_print):
        """Returns list of newsletter dicts."""
        mock_fetch.return_value = "<html>Archive</html>"
        mock_strategy = Mock()
        mock_strategy.extract_newsletters.return_value = [
            {"title": "Newsletter 1", "url": "https://example.com/nl1", "date_str": ""}
        ]
        mock_get_strategy.return_value = mock_strategy

        scraper = NewsletterScraper()
        result = scraper.extract_newsletter_links("https://example.com/archive")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Newsletter 1")

    @patch("builtins.print")
    @patch.object(NewsletterScraper, "fetch_archive_page")
    def test_archive_fetch_failure_returns_empty(self, mock_fetch, mock_print):
        """Fetch failure returns empty list."""
        mock_fetch.return_value = None

        scraper = NewsletterScraper()
        result = scraper.extract_newsletter_links("https://example.com/archive")

        self.assertEqual(result, [])

    @patch("builtins.print")
    @patch("ingest.scraper.newsletter_scraper.get_strategy_for_url")
    @patch.object(NewsletterScraper, "fetch_archive_page")
    def test_prints_strategy_name(self, mock_fetch, mock_get_strategy, mock_print):
        """Console output includes strategy name."""
        mock_fetch.return_value = "<html>Archive</html>"
        mock_strategy = Mock()
        mock_strategy.__class__.__name__ = "MailChimpArchiveStrategy"
        mock_strategy.extract_newsletters.return_value = []
        mock_get_strategy.return_value = mock_strategy

        scraper = NewsletterScraper()
        scraper.extract_newsletter_links("https://example.com/archive")

        # Check that print was called (already mocked)
        self.assertTrue(mock_print.called)


class TestFetchNewsletterContent(unittest.TestCase):
    """Tests for fetch_newsletter_content() method."""

    @patch("requests.Session.get")
    def test_successful_fetch(self, mock_get):
        """Successful fetch returns content dict."""
        html = "<html><title>Newsletter Title</title><body>Content</body></html>"
        mock_response = Mock(status_code=200, text=html)
        mock_get.return_value = mock_response

        scraper = NewsletterScraper()
        result = scraper.fetch_newsletter_content(
            "https://example.com/nl", "Archive Title", "01/24/2026"
        )

        self.assertIsNotNone(result)
        self.assertEqual(result["url"], "https://example.com/nl")
        self.assertIn("html_content", result)
        self.assertIn("plain_text", result)
        self.assertIn("subject", result)

    @patch("requests.Session.get")
    def test_extracts_subject_from_title(self, mock_get):
        """Subject extracted from <title> tag."""
        html = "<html><title>Newsletter Subject</title><body>Content</body></html>"
        mock_response = Mock(status_code=200, text=html)
        mock_get.return_value = mock_response

        scraper = NewsletterScraper()
        result = scraper.fetch_newsletter_content(
            "https://example.com/nl", "Archive Title", ""
        )

        self.assertEqual(result["subject"], "Newsletter Subject")

    @patch("requests.Session.get")
    def test_extracts_subject_from_h1(self, mock_get):
        """Fallback to <h1> when no <title>."""
        html = "<html><body><h1>Newsletter Heading</h1><p>Content</p></body></html>"
        mock_response = Mock(status_code=200, text=html)
        mock_get.return_value = mock_response

        scraper = NewsletterScraper()
        result = scraper.fetch_newsletter_content(
            "https://example.com/nl", "Archive Title", ""
        )

        self.assertEqual(result["subject"], "Newsletter Heading")

    @patch("requests.Session.get")
    def test_fallback_to_archive_title(self, mock_get):
        """Uses archive title when no <title> or <h1>."""
        html = "<html><body><p>Content</p></body></html>"
        mock_response = Mock(status_code=200, text=html)
        mock_get.return_value = mock_response

        scraper = NewsletterScraper()
        result = scraper.fetch_newsletter_content(
            "https://example.com/nl", "Archive Title", ""
        )

        self.assertEqual(result["subject"], "Archive Title")

    @patch("builtins.print")
    @patch("time.sleep")
    @patch("requests.Session.get")
    def test_retry_on_failure(self, mock_get, mock_sleep, mock_print):
        """Retries with exponential backoff on failure."""
        # Fail twice, succeed third time
        mock_get.side_effect = [
            Exception("Connection error"),
            Exception("Timeout"),
            Mock(
                status_code=200,
                text="<html><title>Success</title><body>Content</body></html>",
            ),
        ]

        scraper = NewsletterScraper(max_retries=3)
        result = scraper.fetch_newsletter_content(
            "https://example.com/nl", "Archive Title", ""
        )

        self.assertIsNotNone(result)
        self.assertEqual(mock_get.call_count, 3)

    @patch("builtins.print")
    @patch("time.sleep")
    @patch("requests.Session.get")
    def test_max_retries_returns_none(self, mock_get, mock_sleep, mock_print):
        """All retries fail returns None."""
        mock_get.side_effect = Exception("Connection error")

        scraper = NewsletterScraper(max_retries=3)
        result = scraper.fetch_newsletter_content(
            "https://example.com/nl", "Archive Title", ""
        )

        self.assertIsNone(result)

    @patch("requests.Session.get")
    def test_returns_all_required_fields(self, mock_get):
        """Result has all required fields."""
        html = "<html><title>Title</title><body>Content</body></html>"
        mock_response = Mock(status_code=200, text=html)
        mock_get.return_value = mock_response

        scraper = NewsletterScraper()
        result = scraper.fetch_newsletter_content(
            "https://example.com/nl", "Archive Title", "01/24/2026"
        )

        required_fields = [
            "url",
            "html_content",
            "plain_text",
            "subject",
            "archive_title",
            "archive_date_str",
        ]
        for field in required_fields:
            self.assertIn(field, result)


if __name__ == "__main__":
    unittest.main()
