import unittest
import os

from ingest.email.email_parser import sanitize_content
from config.privacy_patterns import PRIVACY_PATTERNS_DICT


class TestSanitizationComprehensive(unittest.TestCase):
    """
    Comprehensive test suite for the privacy sanitization logic.
    Uses parameterized cases to verify all configured patterns and potential edge cases.
    """

    def test_url_domain_patterns(self):
        """Verify removal of specific known newsletter service domains in hrefs."""
        cases = [
            (
                "Mailchimp Unsubscribe",
                "https://ward49.us18.list-manage.com/unsubscribe?u=123",
                True,
            ),
            (
                "Mailchimp Profile",
                "https://ward49.us18.list-manage.com/profile?u=123",
                True,
            ),
            (
                "Mailchimp About",
                "https://ward49.us18.list-manage.com/about?u=123",
                True,
            ),
            (
                "Mailchimp vCard",
                "https://ward49.us18.list-manage.com/vcard?u=123",
                True,
            ),
            (
                "Mailchimp Track",
                "https://ward49.us18.list-manage.com/track/click?u=123",
                True,
            ),
            (
                "Constant Contact Unsub",
                "https://visitor.constantcontact.com/do?p=un&m=123",
                True,
            ),
            (
                "Constant Contact Profile",
                "https://visitor.constantcontact.com/do?p=oo&m=123",
                True,
            ),
            (
                "Constant Contact Data Notice",
                "https://www.constantcontact.com/legal/customer-contact-data-notice",
                True,
            ),
            (
                "Mailchimp Sites Prefs",
                "https://foo-bar.mailchimpsites.com/manage/preferences",
                True,
            ),
            ("Mailchimp View in Browser", "https://mailchi.mp/123/abc?e=456", True),
            (
                "SparkPost Unsubscribe",
                "https://go.sparkpostmail.com/f/a/123/unsubscribe",
                True,
            ),
            (
                "Forward to Friend",
                "https://us13.forward-to-friend.com/forward?u=123",
                True,
            ),
            (
                "Constant Contact track",
                "https://zsabxyiab.cc.rs6.net/tn.jsp?f=123",
                True,
            ),
            (
                "Constant Contact Marketing",
                "https://www.constantcontact.com/landing1/vr/home?cc=nge&utm_campaign=nge&rmc=VF21_CPE&utm_medium=VF21_CPE&utm_source=viral&nav=ae0af980-9211-45e7-b6f6-4732794b18e5",
                True,
            ),
            (
                "Mailchimp Referral",
                "https://login.mailchimp.com/signup/email-referral/?aid=8b318f91a566aafb49537c87f",
                True,
            ),
            (
                "Mailchimp Archive",
                "https://us20.campaign-archive.com/?e=2e35bed8c6&u=15bbb3d16e48313aee73541bb&id=ee9edab2e3",
                True,
            ),
            # False Positives (Should NOT be removed)
            ("Chicago Gov", "https://www.chicago.gov/city/en/depts/mayor.html", False),
            ("Google Maps", "https://www.google.com/maps/dir/...", False),
            (
                "Ordinary News",
                "https://blockclubchicago.org/2026/01/23/news-item",
                False,
            ),
        ]

        for name, url, should_remove in cases:
            with self.subTest(name=name):
                html = f'<p>Check <a href="{url}">this link</a> for info.</p>'
                sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)
                if should_remove:
                    # URL should be removed from sanitized output
                    self.assertNotIn(
                        url, sanitized, f"URL {url} should have been removed"
                    )
                    # For URL-only matches (tracking links), verify text is preserved
                    self.assertIn(
                        "this link",
                        sanitized,
                        f"Link text should be preserved when unwrapping {url}",
                    )
                    # Anchor tag should be removed
                    self.assertNotIn(
                        "<a",
                        sanitized,
                        f"Anchor tag for {url} should have been removed",
                    )
                else:
                    self.assertIn(
                        url, sanitized, f"URL {url} should have been preserved"
                    )
                    self.assertIn(
                        "<a",
                        sanitized,
                        f"Anchor tag for {url} should have been preserved",
                    )

    def test_link_text_keyword_matches(self):
        """Verify removal of links based on their text content, catching obscured tracking URLs."""
        cases = [
            ("Unsubscribe text", "Unsubscribe", True),
            ("Unsubscribe phrase", "unsubscribe from this list", True),
            ("Safe Unsub", "Safe Unsubscribe", True),
            ("Manage Prefs", "manage preferences", True),
            ("Update Profile", "update your profile", True),
            ("View in browser", "View this email in your browser", True),
            ("Forward to friend", "Forward to a friend", True),
            ("Address book", "Add us to your address book", True),
            # False Positives
            ("Valid Report Link", "Read the five-year blueprint", False),
            ("Normal Contact", "Contact our office", False),
        ]

        for name, text, should_remove in cases:
            with self.subTest(name=name):
                # Using a generic tracking-looking URL that doesn't match any domain pattern
                url = "https://t.co/random-tracking-id"
                html = f'<p>To quit, <a href="{url}">{text}</a> here.</p>'
                sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)
                if should_remove:
                    self.assertNotIn(
                        text,
                        sanitized,
                        f"Link with text '{text}' should have been removed",
                    )
                    self.assertNotIn(
                        "<a",
                        sanitized,
                        f"Anchor tag for '{text}' should have been removed",
                    )
                else:
                    self.assertIn(
                        text,
                        sanitized,
                        f"Link with text '{text}' should have been preserved",
                    )
                    self.assertIn(
                        "<a",
                        sanitized,
                        f"Anchor tag for '{text}' should have been preserved",
                    )

    def test_css_selectors(self):
        """Verify removal of entire containers via CSS selectors."""
        cases = [
            (
                "Compliance Links Table",
                '<table class="complianceLinks"><tr><td>Unsub</td></tr></table>',
                True,
            ),
            (
                "Footer Links Div",
                '<div class="footer-links"><a href="foo">Link</a></div>',
                True,
            ),
            ("Unsubscribe Class", '<p class="unsubscribe">Text</p>', True),
            (
                "MCN View In Browser",
                '<div class="mcnViewInBrowser">View Online</div>',
                True,
            ),
            ("MCN View ID", '<div id="mcnViewInBrowser">View Online</div>', True),
        ]

        for name, snippet, should_remove in cases:
            with self.subTest(name=name):
                html = f"<body><div>Content</div>{snippet}</body>"
                sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)
                if should_remove:
                    # We look for a fragment of the snippet that shouldn't be there
                    # (Simple check: find a unique attribute or the text)
                    if "class=" in snippet:
                        attr = snippet.split('class="')[1].split('"')[0]
                        self.assertNotIn(attr, sanitized)
                self.assertIn("Content", sanitized)

    def test_keyword_safety_in_regular_text(self):
        """Verify that keywords like 'unsubscribe' are NOT removed when part of normal sentence text."""
        # In HTML, only <a> tags should be checked for these keywords
        html = """
        <p>If you want to unsubscribe, you can do so in the settings.</p>
        <p>I want to update my profile picture today.</p>
        <a href="http://tracked.com">Unsubscribe and Manage Preferences</a>
        """
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)
        self.assertIn(
            "If you want to unsubscribe",
            sanitized,
            "Normal paragraph text should be preserved",
        )
        self.assertIn(
            "update my profile picture",
            sanitized,
            "Normal paragraph text should be preserved",
        )
        self.assertNotIn(
            "tracked.com", sanitized, "The link itself should still be removed"
        )

    def test_plain_text_sanitization(self):
        """Verify basic line-stripping and keyword removal in plain text content."""
        text = """
Keep this line.
Unsubscribe
http://list-manage.com/unsubscribe
Manage Preferences
Keep this sentence: I will not unsubscribe from your great news.
"""
        sanitized = sanitize_content(text, "text", PRIVACY_PATTERNS_DICT)
        self.assertIn("Keep this line.", sanitized)
        self.assertIn("I will not unsubscribe from your great news.", sanitized)
        self.assertNotIn("\nUnsubscribe\n", sanitized)
        self.assertNotIn("list-manage.com", sanitized)
        # Note: 'Manage Preferences' is currently only removed if it matches the hardcoded
        # heuristic 'unsubscribe|update profile|manage preferences' exactly as a line.
        self.assertNotIn("\nManage Preferences\n", sanitized)

    def test_sensitive_phrase_redaction(self):
        """Verify that specific phrases (names/emails) from env var are redacted."""
        from unittest.mock import patch

        test_phrases = "personal@example.com, John Doe"
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": test_phrases}):
            # Test HTML
            html = """
            <div>Contact John Doe at <a href="mailto:personal@example.com">personal@example.com</a></div>
            """
            sanitized_html = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)
            self.assertNotIn("personal@example.com", sanitized_html)
            self.assertNotIn("John Doe", sanitized_html)
            self.assertIn("[REDACTED]", sanitized_html)
            # count [REDACTED]: 1 for name, 1 for mailto link, 1 for anchor text = 3
            self.assertEqual(sanitized_html.count("[REDACTED]"), 3)

            # Test Text
            text = "My name is John Doe and my email is personal@example.com"
            sanitized_text = sanitize_content(text, "text", PRIVACY_PATTERNS_DICT)
            self.assertNotIn("personal@example.com", sanitized_text)
            self.assertNotIn("John Doe", sanitized_text)
            self.assertIn("[REDACTED]", sanitized_text)
            self.assertEqual(sanitized_text.count("[REDACTED]"), 2)

    def test_tracking_link_unwrap_with_image(self):
        """Verify that tracking links wrapping images are unwrapped (tag removed, image kept)."""
        html = '<a href="https://zsabxyiab.cc.rs6.net/tn.jsp?f=123"><img src="news_image.jpg"></a>'
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)
        self.assertNotIn("rs6.net", sanitized)
        self.assertNotIn("<a", sanitized)
        self.assertIn('<img src="news_image.jpg"', sanitized)

    def test_unsubscribe_link_decomposition(self):
        """Verify that purely functional privacy links are still completely removed (not unwrapped)."""
        html = '<a href="http://tracked.com">Unsubscribe</a>'
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)
        self.assertNotIn("Unsubscribe", sanitized)
        self.assertNotIn("<a", sanitized)

    def test_tracking_link_unwrap_with_text(self):
        """Verify that tracking links with text content preserve the text while removing the link."""
        cases = [
            (
                "Constant Contact tracking with street name",
                '<p>Project at <a href="https://zsabxyiab.cc.rs6.net/tn.jsp?f=123">Cermak Rd</a> continues.</p>',
                "Cermak Rd",  # Text should be preserved
                "rs6.net",  # URL should be removed
            ),
            (
                "Mailchimp tracking with event title",
                '<p>Join us for <a href="https://mailchi.mp/abc123?e=456">Community Meeting</a> next week.</p>',
                "Community Meeting",
                "mailchi.mp",
            ),
            (
                "Mailchimp tracking link with location",
                '<p>Event at <a href="https://mailchi.mp/abc123def456?e=789">Harold Washington Library</a> tonight.</p>',
                "Harold Washington Library",
                "mailchi.mp",
            ),
            (
                "Multiple tracking links in paragraph",
                '<p>From <a href="https://rs6.net/tn.jsp?f=1">26th St</a> to <a href="https://rs6.net/tn.jsp?f=2">31st St</a>.</p>',
                ["26th St", "31st St"],  # Both texts should be preserved
                "rs6.net",
            ),
            (
                "Campaign archive link with content",
                '<a href="https://us20.campaign-archive.com/?e=123&u=456&id=789">Read full newsletter</a>',
                "Read full newsletter",
                "campaign-archive.com",
            ),
        ]

        for name, html, expected_text, removed_url in cases:
            with self.subTest(name=name):
                sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)

                # Handle both single text and list of texts
                if isinstance(expected_text, list):
                    for text in expected_text:
                        self.assertIn(
                            text,
                            sanitized,
                            f"Text '{text}' should be preserved when unwrapping tracking link",
                        )
                else:
                    # Text content should be preserved
                    self.assertIn(
                        expected_text,
                        sanitized,
                        f"Text '{expected_text}' should be preserved when unwrapping tracking link",
                    )

                # Tracking URL should be removed
                self.assertNotIn(
                    removed_url,
                    sanitized,
                    f"Tracking URL '{removed_url}' should have been removed",
                )

                # Anchor tags for tracking links should be removed
                # Note: We can't just check for no '<a' as legitimate links might exist
                # Instead verify the tracking URL isn't in an anchor tag
                if (
                    f'href="{removed_url}' in html
                    or f'href="https://{removed_url}' in html
                    or removed_url in html
                ):
                    # The tracking link specifically should not have <a> tags
                    self.assertNotIn(
                        f'<a href="https://{removed_url}',
                        sanitized,
                        "Tracking link anchor tag should be removed",
                    )

    def test_privacy_link_double_match_decomposition(self):
        """Verify that links matching both URL and text patterns are completely removed."""
        cases = [
            (
                "Mailchimp unsubscribe (double match)",
                '<p><a href="https://ward49.us18.list-manage.com/unsubscribe?u=123">Unsubscribe from this list</a></p>',
                "Unsubscribe from this list",  # Should be removed
                "list-manage.com",  # Should be removed
            ),
            (
                "Constant Contact profile (double match)",
                '<p><a href="https://visitor.constantcontact.com/do?p=oo&m=123">Update your profile</a></p>',
                "Update your profile",
                "constantcontact.com",
            ),
            (
                "Mailchimp preferences (double match)",
                '<p><a href="https://example.mailchimpsites.com/manage/preferences">Manage preferences</a></p>',
                "Manage preferences",
                "mailchimpsites.com",
            ),
            (
                "Forward to friend (double match)",
                '<p><a href="https://us13.forward-to-friend.com/forward?u=123">Forward to a friend</a></p>',
                "Forward to a friend",
                "forward-to-friend.com",
            ),
            (
                "View in browser with matching URL",
                '<p><a href="https://mailchi.mp/abc?e=123">View this email in your browser</a></p>',
                "View this email in your browser",
                "mailchi.mp",
            ),
        ]

        for name, html, removed_text, removed_url in cases:
            with self.subTest(name=name):
                sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)

                # Both text and URL should be removed
                self.assertNotIn(
                    removed_text,
                    sanitized,
                    f"Privacy link text '{removed_text}' should be completely removed",
                )
                self.assertNotIn(
                    removed_url,
                    sanitized,
                    f"Privacy URL '{removed_url}' should be removed",
                )

                # Anchor tags should be removed
                # More lenient check - just ensure this specific text isn't in a link
                if "<a" in sanitized and removed_text in sanitized:
                    self.fail(
                        f"Privacy link should be completely removed, but text '{removed_text}' still present"
                    )

    def test_mixed_content_scenarios(self):
        """Verify complex scenarios with legitimate links, tracking links, and privacy links."""
        html = """
        <div>
            <p>Visit <a href="https://www.chicago.gov">City of Chicago</a> for information.</p>
            <p>Project at <a href="https://rs6.net/tn.jsp?f=123">1234 W Cermak Rd</a> is approved.</p>
            <p>Contact us at <a href="mailto:ward@chicago.gov">ward@chicago.gov</a>.</p>
            <p><a href="https://ward49.us18.list-manage.com/unsubscribe?u=123">Unsubscribe</a></p>
            <p><a href="https://example.com">View this email in your browser</a></p>
        </div>
        """

        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)

        # Legitimate links should be preserved
        self.assertIn(
            "chicago.gov", sanitized, "Legitimate city website link should be preserved"
        )
        self.assertIn(
            "City of Chicago", sanitized, "Legitimate link text should be preserved"
        )
        self.assertIn(
            "mailto:ward@chicago.gov", sanitized, "Mailto link should be preserved"
        )

        # Tracking link text should be preserved, but link removed
        self.assertIn(
            "1234 W Cermak Rd", sanitized, "Tracking link text should be preserved"
        )
        self.assertNotIn("rs6.net", sanitized, "Tracking URL should be removed")

        # Privacy links should be completely removed
        self.assertNotIn(
            "Unsubscribe", sanitized, "Unsubscribe link should be completely removed"
        )
        self.assertNotIn(
            "list-manage.com/unsubscribe",
            sanitized,
            "Unsubscribe URL should be removed",
        )
        self.assertNotIn(
            "View this email in your browser",
            sanitized,
            "Browser view link should be removed",
        )

        # Verify paragraph tags remain (structure preservation)
        self.assertIn("<p>", sanitized, "HTML structure should be preserved")


if __name__ == "__main__":
    unittest.main()
