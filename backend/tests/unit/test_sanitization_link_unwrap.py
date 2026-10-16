"""Privacy sanitization of links: tracking links unwrapped, privacy links removed."""

import unittest

from config.privacy_patterns import PRIVACY_PATTERNS_DICT
from ingest.email.email_parser import sanitize_content


class TestSanitizationLinkUnwrap(unittest.TestCase):
    """Tracking links keep their content; purely functional privacy links go entirely."""

    def test_tracking_link_unwrap_with_image(self) -> None:
        """Verify that tracking links wrapping images are unwrapped (tag removed, image kept)."""
        html = '<a href="https://zsabxyiab.cc.rs6.net/tn.jsp?f=123"><img src="news_image.jpg"></a>'
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)
        self.assertNotIn("rs6.net", sanitized)
        self.assertNotIn("<a", sanitized)
        self.assertIn('<img src="news_image.jpg"', sanitized)

    def test_unsubscribe_link_decomposition(self) -> None:
        """Verify that purely functional privacy links are still completely removed (not unwrapped)."""
        html = '<a href="http://tracked.com">Unsubscribe</a>'
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS_DICT)
        self.assertNotIn("Unsubscribe", sanitized)
        self.assertNotIn("<a", sanitized)

    def test_tracking_link_unwrap_with_text(self) -> None:
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

    def test_privacy_link_double_match_decomposition(self) -> None:
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

    def test_mixed_content_scenarios(self) -> None:
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
