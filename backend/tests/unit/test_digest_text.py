"""Unit tests for notifications/digest_text.py plain-text digest bodies."""

import unittest

from notifications.digest_config import DigestType
from notifications.digest_text import build_digest_text


class TestBuildDigestText(unittest.TestCase):
    """Tests for build_digest_text() plain text template."""

    def test_plain_text_structure(self) -> None:
        """Plain text has header, numbered list, footer."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "Test summary",
                "topics": ["zoning"],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": ["Rule 1"],
            }
        ]

        text = build_digest_text(
            prepared,
            DigestType.DAILY,
            "http://example.com/prefs",
            "http://example.com/unsub",
        )

        self.assertIn("DAILY NEWSLETTER DIGEST", text)
        self.assertIn("1.", text)
        self.assertIn("---", text)

    def test_includes_all_newsletters(self) -> None:
        """All newsletters included in numbered list."""
        prepared = [
            {
                "title": "Newsletter 1",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://example.com/nl1",
                "matched_rules": [],
            },
            {
                "title": "Newsletter 2",
                "source_name": "Ward 2",
                "ward_text": "",
                "date_formatted": "January 23, 2026",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://example.com/nl2",
                "matched_rules": [],
            },
        ]

        text = build_digest_text(
            prepared,
            DigestType.DAILY,
            "http://example.com/prefs",
            "http://example.com/unsub",
        )

        self.assertIn("1. Newsletter 1", text)
        self.assertIn("2. Newsletter 2", text)

    def test_includes_matched_rules(self) -> None:
        """Rule names shown in plain text."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": ["Zoning Updates"],
            }
        ]

        text = build_digest_text(
            prepared,
            DigestType.DAILY,
            "http://example.com/prefs",
            "http://example.com/unsub",
        )

        self.assertIn("Zoning Updates", text)

    def test_includes_topics(self) -> None:
        """Topics listed in plain text."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": ["zoning", "transit"],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": [],
            }
        ]

        text = build_digest_text(
            prepared,
            DigestType.DAILY,
            "http://example.com/prefs",
            "http://example.com/unsub",
        )

        self.assertIn("zoning", text)
        self.assertIn("transit", text)

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

        text = build_digest_text(
            prepared,
            DigestType.DAILY,
            "http://example.com/prefs",
            "http://example.com/unsub",
        )

        self.assertIn("http://example.com/prefs", text)


if __name__ == "__main__":
    unittest.main()
