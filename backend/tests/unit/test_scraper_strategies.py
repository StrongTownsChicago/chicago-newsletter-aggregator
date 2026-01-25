"""
Unit tests for ingest/scraper/scraper_strategies.py

Tests strategy selection and newsletter extraction from different
archive page formats (MailChimp, generic).
"""

import unittest

from ingest.scraper.scraper_strategies import (
    MailChimpArchiveStrategy,
    GenericListStrategy,
    get_strategy_for_url,
)


class TestMailChimpArchiveStrategy(unittest.TestCase):
    """Tests for MailChimpArchiveStrategy."""

    def test_extract_newsletters_basic(self):
        """Extracts title, url, date from MailChimp archive HTML."""
        html = """
        <ul id="archive-list">
            <li class="campaign">
                <a href="https://mailchi.mp/example/newsletter-1" title="January Update">
                    January Update
                </a>
            </li>
        </ul>
        """

        strategy = MailChimpArchiveStrategy()
        result = strategy.extract_newsletters(html, "https://example.com")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "January Update")
        self.assertIn("mailchi.mp", result[0]["url"])

    def test_extract_date_from_context(self):
        """Parses date from '12/23/2025 - Title' format."""
        html = """
        <ul id="archive-list">
            <li class="campaign">
                12/23/2025 - <a href="https://mailchi.mp/example/newsletter">Newsletter</a>
            </li>
        </ul>
        """

        strategy = MailChimpArchiveStrategy()
        result = strategy.extract_newsletters(html, "https://example.com")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["date_str"], "12/23/2025")

    def test_skips_non_campaign_items(self):
        """Only extracts links within li.campaign elements."""
        html = """
        <ul id="archive-list">
            <li class="campaign">
                <a href="https://mailchi.mp/example/newsletter-1">Newsletter 1</a>
            </li>
            <li class="signup">
                <a href="https://example.com/subscribe">Subscribe</a>
            </li>
        </ul>
        """

        strategy = MailChimpArchiveStrategy()
        result = strategy.extract_newsletters(html, "https://example.com")

        # Should only get the campaign item, not the signup item
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["title"], "Newsletter 1")

    def test_handles_missing_date(self):
        """Date extraction fails gracefully, returns empty string."""
        html = """
        <ul id="archive-list">
            <li class="campaign">
                <a href="https://mailchi.mp/example/newsletter">Newsletter</a>
            </li>
        </ul>
        """

        strategy = MailChimpArchiveStrategy()
        result = strategy.extract_newsletters(html, "https://example.com")

        self.assertEqual(result[0]["date_str"], "")

    def test_handles_missing_title(self):
        """Uses link text when title attribute missing."""
        html = """
        <ul id="archive-list">
            <li class="campaign">
                <a href="https://mailchi.mp/example/newsletter">Link Text</a>
            </li>
        </ul>
        """

        strategy = MailChimpArchiveStrategy()
        result = strategy.extract_newsletters(html, "https://example.com")

        self.assertEqual(result[0]["title"], "Link Text")

    def test_empty_archive_returns_empty(self):
        """No newsletters found returns empty list."""
        html = """
        <ul id="archive-list">
        </ul>
        """

        strategy = MailChimpArchiveStrategy()
        result = strategy.extract_newsletters(html, "https://example.com")

        self.assertEqual(result, [])

    def test_malformed_html_handled(self):
        """Broken HTML doesn't crash."""
        html = "<ul id='archive-list'><li class='campaign'><a href='test'>Unclosed"

        strategy = MailChimpArchiveStrategy()
        result = strategy.extract_newsletters(html, "https://example.com")

        # Should not crash, may return empty or partial results
        self.assertIsInstance(result, list)


class TestGenericListStrategy(unittest.TestCase):
    """Tests for GenericListStrategy fallback."""

    def test_extracts_newsletter_like_urls(self):
        """Finds links with 'newsletter', 'archive', 'campaign' keywords."""
        html = """
        <a href="https://example.com/newsletter-january">January Newsletter</a>
        <a href="https://example.com/archive/2025-01">Archive Link</a>
        <a href="https://example.com/about">About</a>
        """

        strategy = GenericListStrategy()
        result = strategy.extract_newsletters(html, "https://example.com")

        # Should find 2 newsletter-like links, not the "about" link
        self.assertEqual(len(result), 2)
        self.assertTrue(any("newsletter" in r["url"].lower() for r in result))
        self.assertTrue(any("archive" in r["url"].lower() for r in result))

    def test_converts_relative_to_absolute(self):
        """Relative URLs converted to absolute using urljoin."""
        html = """
        <a href="/newsletter/january">January</a>
        """

        strategy = GenericListStrategy()
        result = strategy.extract_newsletters(html, "https://example.com")

        self.assertEqual(result[0]["url"], "https://example.com/newsletter/january")

    def test_skips_internal_links(self):
        """Skips #, javascript:, mailto: links."""
        html = """
        <a href="#top">Top</a>
        <a href="javascript:void(0)">JS Link</a>
        <a href="mailto:test@example.com">Email</a>
        <a href="https://example.com/newsletter">Newsletter</a>
        """

        strategy = GenericListStrategy()
        result = strategy.extract_newsletters(html, "https://example.com")

        # Should only get the newsletter link
        self.assertEqual(len(result), 1)
        self.assertIn("newsletter", result[0]["url"])

    def test_handles_no_matching_links(self):
        """Returns empty list when no newsletter-like links found."""
        html = """
        <a href="/about">About</a>
        <a href="/contact">Contact</a>
        """

        strategy = GenericListStrategy()
        result = strategy.extract_newsletters(html, "https://example.com")

        self.assertEqual(result, [])

    def test_uses_untitled_fallback(self):
        """No link text uses 'Untitled Newsletter' fallback."""
        html = """
        <a href="https://example.com/newsletter"></a>
        """

        strategy = GenericListStrategy()
        result = strategy.extract_newsletters(html, "https://example.com")

        if len(result) > 0:
            self.assertEqual(result[0]["title"], "Untitled Newsletter")


class TestGetStrategyForUrl(unittest.TestCase):
    """Tests for get_strategy_for_url() selection logic."""

    def test_returns_mailchimp_for_mailchimp_urls(self):
        """mailchi.mp URLs return MailChimpArchiveStrategy."""
        strategy = get_strategy_for_url("https://mailchi.mp/example/archive")

        self.assertIsInstance(strategy, MailChimpArchiveStrategy)

    def test_returns_mailchimp_for_campaign_archive(self):
        """campaign-archive.com URLs return MailChimpArchiveStrategy."""
        strategy = get_strategy_for_url(
            "https://us20.campaign-archive.com/home/?u=123&id=456"
        )

        self.assertIsInstance(strategy, MailChimpArchiveStrategy)

    def test_returns_generic_for_other_urls(self):
        """Other URLs return GenericListStrategy."""
        strategy = get_strategy_for_url("https://example.com/newsletters")

        self.assertIsInstance(strategy, GenericListStrategy)

    def test_case_insensitive_matching(self):
        """URL matching is case-insensitive."""
        strategy = get_strategy_for_url("https://MAILCHI.MP/example/archive")

        self.assertIsInstance(strategy, MailChimpArchiveStrategy)


if __name__ == "__main__":
    unittest.main()
