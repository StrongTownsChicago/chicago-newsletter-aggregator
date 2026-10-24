import os
import unittest
from unittest.mock import patch

from config.privacy_patterns import PRIVACY_PATTERNS_DICT
from ingest.email.email_parser import sanitize_content


class TestSanitizationComprehensive(unittest.TestCase):
    """
    Comprehensive test suite for the privacy sanitization logic.
    Uses parameterized cases to verify all configured patterns and potential edge cases.
    """

    def test_url_domain_patterns(self) -> None:
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

    def test_link_text_keyword_matches(self) -> None:
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

    def test_css_selectors(self) -> None:
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
                # We look for a fragment of the snippet that shouldn't be there
                # (Simple check: find a unique attribute or the text)
                if should_remove and "class=" in snippet:
                    attr = snippet.split('class="')[1].split('"')[0]
                    self.assertNotIn(attr, sanitized)
                self.assertIn("Content", sanitized)

    def test_keyword_safety_in_regular_text(self) -> None:
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

    def test_plain_text_sanitization(self) -> None:
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

    def test_sensitive_phrase_redaction(self) -> None:
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

    def test_redaction_never_rewrites_an_earlier_marker(self) -> None:
        """A phrase found inside "[REDACTED]" ("Ted", "Act") leaves markers whole, even on a second pass."""
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Jane,Ted,Act"}):
            once = sanitize_content("Jane met Ted", "text", PRIVACY_PATTERNS_DICT)
            twice = sanitize_content(once, "text", PRIVACY_PATTERNS_DICT)

        self.assertEqual(once, "[REDACTED] met [REDACTED]")
        self.assertEqual(twice, once)

    def test_longer_phrases_are_redacted_whole(self) -> None:
        """A phrase that contains a shorter one ("Jane Roe", "Jane") is redacted entirely."""
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Jane,Jane Roe"}):
            sanitized = sanitize_content("From Jane Roe", "text", PRIVACY_PATTERNS_DICT)

        self.assertEqual(sanitized, "From [REDACTED]")

    def test_html_parser_failure_falls_back_to_redacted_original(self) -> None:
        """If the HTML sanitizer raises, the original content is kept, still redacted."""
        html = '<a href="https://x.list-manage.com/unsubscribe">Jane</a>'
        with (
            patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Jane"}),
            patch(
                "ingest.email.email_parser.BeautifulSoup",
                side_effect=ValueError("parser failed"),
            ),
            patch("builtins.print"),
        ):
            sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)

        self.assertEqual(
            sanitized, '<a href="https://x.list-manage.com/unsubscribe">[REDACTED]</a>'
        )

    def test_unknown_content_type_is_only_redacted(self) -> None:
        """Content that is neither HTML nor text skips link and line filtering."""
        content = "Tom & Jerry\nUnsubscribe"
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Jerry"}):
            for content_type in ("csv", "markdown", "xml"):
                with self.subTest(content_type=content_type):
                    self.assertEqual(
                        sanitize_content(content, content_type, PRIVACY_PATTERNS_DICT),
                        "Tom & [REDACTED]\nUnsubscribe",
                    )

    def test_phrase_split_by_a_removed_link_is_redacted(self) -> None:
        """Text either side of an unwrapped or removed element is matched as one."""
        cases = [
            '<p>Contact <a href="https://x.list-manage.com/track/click?u=1">Jane</a> Doe</p>',
            '<p>Email <a href="https://x.list-manage.com/track/click">jane</a>@doe.com</p>',
            '<p>Jane<span class="complianceLinks">x</span> Doe</p>',
        ]
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Jane Doe,jane@doe.com"}):
            for html in cases:
                with self.subTest(html=html):
                    sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)
                    self.assertNotIn("jane", sanitized.lower())
                    self.assertIn("[REDACTED]", sanitized)

    def test_phrase_split_by_inline_tags_is_redacted(self) -> None:
        """A phrase readers see whole is redacted even when tags split it."""
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Jane Doe"}):
            sanitized = sanitize_content(
                "<p>Contact Jane <b>Doe</b> or J<i>ane</i> Doe today</p>",
                "html",
                PRIVACY_PATTERNS_DICT,
            )

        self.assertEqual(
            sanitized, "<p>Contact [REDACTED]<b></b> or [REDACTED]<i></i> today</p>"
        )

    def test_phrases_match_whole_words_only(self) -> None:
        """Short names redact the name, possessives included, but not words containing it."""
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Ted,Ed"}):
            sanitized = sanitize_content(
                "Ted started; Ed's edits needed Ted.", "text", PRIVACY_PATTERNS_DICT
            )

        self.assertEqual(
            sanitized, "[REDACTED] started; [REDACTED]'s edits needed [REDACTED]."
        )

    def test_underscores_digits_and_prefixes_do_not_hide_a_phrase(self) -> None:
        """Only letters make a phrase part of a longer word."""
        phrases = "Jane Doe,3125551234,jane@example.com"
        cases = {
            "Thanks to _Jane Doe_ for help": "Thanks to _[REDACTED]_ for help",
            "Call +13125551234 today": "Call +1[REDACTED] today",
            "Write jane@example.com_ now": "Write [REDACTED]_ now",
        }
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": phrases}):
            for text, expected in cases.items():
                with self.subTest(text=text):
                    self.assertEqual(
                        sanitize_content(text, "text", PRIVACY_PATTERNS_DICT), expected
                    )
            html = sanitize_content(
                '<a href="tel:+13125551234">call</a><img alt="_Jane Doe_" src="a.png">',
                "html",
                PRIVACY_PATTERNS_DICT,
            )

        self.assertEqual(
            html,
            '<a href="tel:+1[REDACTED]">call</a><img alt="_[REDACTED]_" src="a.png"/>',
        )

    def test_block_ending_in_a_letter_does_not_hide_the_next_phrase(self) -> None:
        """Minified HTML puts blocks side by side; each block's text is its own word run."""
        cases = {
            "<p>Contact</p><p>Jane <b>Doe</b> today</p>": "<p>Contact</p><p>[REDACTED]<b></b> today</p>",
            "<td>Thanks</td><td>Jane Doe</td>": "<td>Thanks</td><td>[REDACTED]</td>",
            '<p><b>Contact</b>Jane <a href="https://x.list-manage.com/profile?u=1">Doe</a></p>': "<p><b>Contact</b>[REDACTED]</p>",
        }
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Jane Doe"}):
            for html, expected in cases.items():
                with self.subTest(html=html):
                    once = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)
                    self.assertEqual(once, expected)
                    self.assertEqual(
                        sanitize_content(once, "html", PRIVACY_PATTERNS_DICT), once
                    )

    def test_name_wrapped_across_source_lines_is_redacted(self) -> None:
        """Browsers render "Jane\\n  Doe" as "Jane Doe", so it is redacted the same."""
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Jane Doe"}):
            sanitized = sanitize_content(
                "<p>Contact Jane\n   Doe today</p>", "html", PRIVACY_PATTERNS_DICT
            )

        self.assertEqual(sanitized, "<p>Contact [REDACTED] today</p>")

    def test_percent_encoded_email_in_a_link_is_redacted(self) -> None:
        """mailto: links often percent-encode the @."""
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "jane@example.com"}):
            sanitized = sanitize_content(
                '<a href="mailto:jane%40example.com">Email</a>',
                "html",
                PRIVACY_PATTERNS_DICT,
            )

        self.assertEqual(sanitized, '<a href="mailto:[REDACTED]">Email</a>')

    def test_preformatted_whitespace_is_kept_when_a_phrase_is_removed(self) -> None:
        """Whitespace left by redaction collapses as the parser would, except in <pre>."""
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Jane Doe"}):
            sanitized = sanitize_content(
                "<p>Jane <i>Doe   </i></p><pre>Jane <i>Doe   </i></pre>",
                "html",
                PRIVACY_PATTERNS_DICT,
            )

        self.assertEqual(
            sanitized, "<p>[REDACTED]<i> </i></p><pre>[REDACTED]<i>   </i></pre>"
        )

    def test_obfuscated_privacy_urls_are_matched_as_a_browser_reads_them(self) -> None:
        """Tabs, newlines and percent-escapes inside a URL don't hide it."""
        hrefs = [
            "https://x.list-man&#9;age.com/unsubscribe?u=1",
            "https://x.list-man&#10;age.com/unsubscribe?u=1",
            "https://x.list-manage.com/un%73ubscribe?u=1",
            "https://x.list%2Dmanage.com/unsubscribe",
            " HTTPS://X.LIST-MANAGE.COM/UNSUBSCRIBE",
        ]
        for href in hrefs:
            with self.subTest(href=href):
                sanitized = sanitize_content(
                    f'<p><a href="{href}">here</a></p>', "html", PRIVACY_PATTERNS_DICT
                )
                self.assertEqual(sanitized, "<p>here</p>")

        text = "News\nhttps://x.list-manage.com/un%73ubscribe?u=1"
        self.assertEqual(sanitize_content(text, "text", PRIVACY_PATTERNS_DICT), "News")

    def test_phrase_across_class_tokens_is_redacted(self) -> None:
        """Multi-valued attributes are matched as written, not token by token."""
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Jane Doe"}):
            sanitized = sanitize_content(
                '<p class="Jane Doe">hi</p>', "html", PRIVACY_PATTERNS_DICT
            )

        self.assertEqual(sanitized, '<p class="[REDACTED]">hi</p>')

    def test_phrases_that_match_nothing_change_nothing(self) -> None:
        """Configured phrases absent from the content leave the output as without them."""
        html = '<meta charset="windows-1252"><p class="a b">Ward news</p>'
        without_phrases = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "zzzz"}):
            with_phrases = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)

        self.assertEqual(with_phrases, without_phrases)

    def test_html_redaction_leaves_markup_intact(self) -> None:
        """Phrases are redacted in text and attribute values, never in tag or attribute names."""
        html = '<p align="center" title="From Al"><!-- Al -->Al wrote</p>'
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Al"}):
            sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)

        self.assertEqual(
            sanitized,
            '<p align="center" title="From [REDACTED]"><!-- [REDACTED] -->'
            "[REDACTED] wrote</p>",
        )
