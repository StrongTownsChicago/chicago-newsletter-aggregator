"""Unit tests for notifications/digest_html.py HTML digest bodies."""

import unittest

from notifications.digest_config import DigestType
from notifications.digest_html import build_digest_html


class TestBuildDigestHtml(unittest.TestCase):
    """Tests for build_digest_html() template generation."""

    def test_includes_all_newsletters(self) -> None:
        """All newsletters included in HTML."""
        prepared = [
            {
                "title": "Newsletter 1",
                "source_name": "Ward 1",
                "ward_text": " (Ward 1)",
                "date_formatted": "January 24, 2026",
                "summary": "Summary 1",
                "topics": ["zoning"],
                "newsletter_url": "http://example.com/nl1",
                "matched_rules": ["Rule 1"],
            },
            {
                "title": "Newsletter 2",
                "source_name": "Ward 2",
                "ward_text": " (Ward 2)",
                "date_formatted": "January 23, 2026",
                "summary": "Summary 2",
                "topics": ["transit"],
                "newsletter_url": "http://example.com/nl2",
                "matched_rules": ["Rule 2"],
            },
        ]

        html = build_digest_html(
            prepared,
            DigestType.DAILY,
            "http://example.com/prefs",
            "http://example.com/unsub",
        )

        self.assertIn("Newsletter 1", html)
        self.assertIn("Newsletter 2", html)

    def test_includes_matched_rules(self) -> None:
        """Matched rule names shown in HTML."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": ["Zoning Updates", "Bike Lanes"],
            }
        ]

        html = build_digest_html(
            prepared,
            DigestType.DAILY,
            "http://example.com/prefs",
            "http://example.com/unsub",
        )

        self.assertIn("Zoning Updates", html)
        self.assertIn("Bike Lanes", html)

    def test_includes_topics(self) -> None:
        """Topics displayed in HTML."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": ["zoning", "transit", "bike_lanes"],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": [],
            }
        ]

        html = build_digest_html(
            prepared,
            DigestType.DAILY,
            "http://example.com/prefs",
            "http://example.com/unsub",
        )

        self.assertIn("zoning", html)
        self.assertIn("transit", html)
        self.assertIn("bike_lanes", html)

    def test_limits_topics_to_five(self) -> None:
        """Only first 5 topics shown."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": ["topic1", "topic2", "topic3", "topic4", "topic5", "topic6"],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": [],
            }
        ]

        html = build_digest_html(
            prepared,
            DigestType.DAILY,
            "http://example.com/prefs",
            "http://example.com/unsub",
        )

        self.assertIn("topic5", html)
        self.assertNotIn("topic6", html)

    def test_includes_preferences_link(self) -> None:
        """Preferences link present in footer."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": [],
            }
        ]

        html = build_digest_html(
            prepared,
            DigestType.DAILY,
            "http://example.com/preferences",
            "http://example.com/unsub",
        )

        self.assertIn("http://example.com/preferences", html)
