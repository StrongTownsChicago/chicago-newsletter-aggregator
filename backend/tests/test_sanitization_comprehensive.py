
import unittest
import sys
import os

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest.email.email_parser import sanitize_content

class TestSanitizationComprehensive(unittest.TestCase):
    """
    Comprehensive test suite for the privacy sanitization logic.
    Uses parameterized cases to verify all configured patterns and potential edge cases.
    """

    def test_url_domain_patterns(self):
        """Verify removal of specific known newsletter service domains in hrefs."""
        cases = [
            ("Mailchimp Unsubscribe", "https://ward49.us18.list-manage.com/unsubscribe?u=123", True),
            ("Mailchimp Profile", "https://ward49.us18.list-manage.com/profile?u=123", True),
            ("Mailchimp About", "https://ward49.us18.list-manage.com/about?u=123", True),
            ("Mailchimp vCard", "https://ward49.us18.list-manage.com/vcard?u=123", True),
            ("Mailchimp Track", "https://ward49.us18.list-manage.com/track/click?u=123", True),
            ("Constant Contact Unsub", "https://visitor.constantcontact.com/do?p=un&m=123", True),
            ("Constant Contact Profile", "https://visitor.constantcontact.com/do?p=oo&m=123", True),
            ("Constant Contact Data Notice", "https://www.constantcontact.com/legal/customer-contact-data-notice", True),
            ("Mailchimp Sites Prefs", "https://foo-bar.mailchimpsites.com/manage/preferences", True),
            ("Mailchimp View in Browser", "https://mailchi.mp/123/abc?e=456", True),
            ("SparkPost Unsubscribe", "https://go.sparkpostmail.com/f/a/123/unsubscribe", True),
            ("Forward to Friend", "https://us13.forward-to-friend.com/forward?u=123", True),
            ("Constant Contact track", "https://zsabxyiab.cc.rs6.net/tn.jsp?f=123", True),
            ("Constant Contact Marketing", "https://www.constantcontact.com/landing1/vr/home?cc=nge&utm_campaign=nge&rmc=VF21_CPE&utm_medium=VF21_CPE&utm_source=viral&nav=ae0af980-9211-45e7-b6f6-4732794b18e5", True),
            ("Mailchimp Referral", "https://login.mailchimp.com/signup/email-referral/?aid=8b318f91a566aafb49537c87f", True),
            # False Positives (Should NOT be removed)
            ("Chicago Gov", "https://www.chicago.gov/city/en/depts/mayor.html", False),
            ("Google Maps", "https://www.google.com/maps/dir/...", False),
            ("Ordinary News", "https://blockclubchicago.org/2026/01/23/news-item", False),
        ]

        for name, url, should_remove in cases:
            with self.subTest(name=name):
                html = f'<p>Check <a href="{url}">this link</a> for info.</p>'
                sanitized = sanitize_content(html, 'html')
                if should_remove:
                    self.assertNotIn(url, sanitized, f"URL {url} should have been removed")
                    self.assertNotIn("<a", sanitized, f"Anchor tag for {url} should have been removed")
                else:
                    self.assertIn(url, sanitized, f"URL {url} should have been preserved")
                    self.assertIn("<a", sanitized, f"Anchor tag for {url} should have been preserved")

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
                sanitized = sanitize_content(html, 'html')
                if should_remove:
                    self.assertNotIn(text, sanitized, f"Link with text '{text}' should have been removed")
                    self.assertNotIn("<a", sanitized, f"Anchor tag for '{text}' should have been removed")
                else:
                    self.assertIn(text, sanitized, f"Link with text '{text}' should have been preserved")
                    self.assertIn("<a", sanitized, f"Anchor tag for '{text}' should have been preserved")

    def test_css_selectors(self):
        """Verify removal of entire containers via CSS selectors."""
        cases = [
            ("Compliance Links Table", '<table class="complianceLinks"><tr><td>Unsub</td></tr></table>', True),
            ("Footer Links Div", '<div class="footer-links"><a href="foo">Link</a></div>', True),
            ("Unsubscribe Class", '<p class="unsubscribe">Text</p>', True),
            ("MCN View In Browser", '<div class="mcnViewInBrowser">View Online</div>', True),
            ("MCN View ID", '<div id="mcnViewInBrowser">View Online</div>', True),
        ]

        for name, snippet, should_remove in cases:
            with self.subTest(name=name):
                html = f'<body><div>Content</div>{snippet}</body>'
                sanitized = sanitize_content(html, 'html')
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
        sanitized = sanitize_content(html, 'html')
        self.assertIn("If you want to unsubscribe", sanitized, "Normal paragraph text should be preserved")
        self.assertIn("update my profile picture", sanitized, "Normal paragraph text should be preserved")
        self.assertNotIn("tracked.com", sanitized, "The link itself should still be removed")

    def test_plain_text_sanitization(self):
        """Verify basic line-stripping and keyword removal in plain text content."""
        text = """
Keep this line.
Unsubscribe
http://list-manage.com/unsubscribe
Manage Preferences
Keep this sentence: I will not unsubscribe from your great news.
"""
        sanitized = sanitize_content(text, 'text')
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
            sanitized_html = sanitize_content(html, 'html')
            self.assertNotIn("personal@example.com", sanitized_html)
            self.assertNotIn("John Doe", sanitized_html)
            self.assertIn("[REDACTED]", sanitized_html)
            # count [REDACTED]: 1 for name, 1 for mailto link, 1 for anchor text = 3
            self.assertEqual(sanitized_html.count("[REDACTED]"), 3)

            # Test Text
            text = "My name is John Doe and my email is personal@example.com"
            sanitized_text = sanitize_content(text, 'text')
            self.assertNotIn("personal@example.com", sanitized_text)
            self.assertNotIn("John Doe", sanitized_text)
            self.assertIn("[REDACTED]", sanitized_text)
            self.assertEqual(sanitized_text.count("[REDACTED]"), 2)

    def test_tracking_link_unwrap_with_image(self):
        """Verify that tracking links wrapping images are unwrapped (tag removed, image kept)."""
        html = '<a href="https://zsabxyiab.cc.rs6.net/tn.jsp?f=123"><img src="news_image.jpg"></a>'
        sanitized = sanitize_content(html, 'html')
        self.assertNotIn("rs6.net", sanitized)
        self.assertNotIn("<a", sanitized)
        self.assertIn('<img src="news_image.jpg"', sanitized)

    def test_unsubscribe_link_decomposition(self):
        """Verify that purely functional privacy links are still completely removed (not unwrapped)."""
        html = '<a href="http://tracked.com">Unsubscribe</a>'
        sanitized = sanitize_content(html, 'html')
        self.assertNotIn("Unsubscribe", sanitized)
        self.assertNotIn("<a", sanitized)

if __name__ == '__main__':
    unittest.main()
