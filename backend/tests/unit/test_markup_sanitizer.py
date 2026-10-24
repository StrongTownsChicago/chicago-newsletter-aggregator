"""Tests for the allowlist sanitizer applied to stored newsletter HTML."""

import os
import unittest
from unittest.mock import patch

from config.privacy_patterns import PRIVACY_PATTERNS_DICT
from ingest.email.email_parser import sanitize_newsletter_html
from ingest.markup_sanitizer import sanitize_markup

# Payloads that run script, load a frame or submit a form, each paired with
# the markup that must not survive.
ATTACKS = {
    '<img src="x.png" onerror="alert(1)">': "onerror",
    "<body onload=alert(1)><p>Hi</p></body>": "onload",
    '<p onclick="alert(1)">Hi</p>': "onclick",
    "<script>alert(1)</script>": "alert",
    "<svg><script>alert(1)</script></svg>": "alert",
    '<svg onload="alert(1)"></svg>': "svg",
    '<a href="javascript:alert(1)">Link</a>': "javascript",
    '<a href="JaVaScRiPt:alert(1)">Link</a>': "alert",
    '<a href=" java&#x09;script:alert(1)">Link</a>': "alert",
    '<a href="data:text/html,<script>alert(1)</script>">Link</a>': "data:",
    '<a href="vbscript:msgbox(1)">Link</a>': "vbscript",
    '<iframe src="https://example.com"></iframe>': "iframe",
    '<object data="https://example.com/x.swf"></object>': "object",
    '<embed src="https://example.com/x.swf">': "embed",
    '<form action="https://example.com"><input name="password"></form>': "input",
    '<meta http-equiv="refresh" content="0;url=https://example.com">': "refresh",
    '<base href="https://example.com/">': "base",
    '<link rel="stylesheet" href="https://example.com/x.css">': "stylesheet",
    "<style>body { display: none }</style>": "display",
    '<math><mi xlink:href="javascript:alert(1)">x</mi></math>': "javascript",
    '<noscript><p title="</noscript><img src=x onerror=alert(1)>"></noscript>': (
        "onerror"
    ),
    "<template><img src=x onerror=alert(1)></template>": "onerror",
}


class TestUnsafeMarkupIsRemoved(unittest.TestCase):
    def test_attacks_do_not_survive(self) -> None:
        for html, marker in ATTACKS.items():
            with self.subTest(html=html):
                self.assertNotIn(marker, sanitize_markup(html).lower())

    def test_site_classes_and_ids_are_dropped(self) -> None:
        """A newsletter can't reuse the site's CSS classes or clobber globals by id."""
        sanitized = sanitize_markup('<div class="fixed inset-0" id="supabase">Hi</div>')
        self.assertEqual(sanitized, "<div>Hi</div>")

    def test_positioning_styles_are_dropped(self) -> None:
        sanitized = sanitize_markup(
            '<div style="position: fixed; top: 0; z-index: 99; color: red">Hi</div>'
        )
        self.assertEqual(sanitized, '<div style="color:red">Hi</div>')

    def test_negative_margins_are_dropped(self) -> None:
        """A negative margin would pull content up over the site's header."""
        for style in (
            "margin-top:-2000px",
            "margin:-10px 0",
            "MARGIN-LEFT:-9px",
            "margin-top:calc(-1 * 900px)",
            "margin-top:/**/-9px",
            "color:red;/**/margin-top:-9px",
            r"m\argin-top:-9px",
        ):
            with self.subTest(style=style):
                self.assertNotIn(
                    "margin", sanitize_markup(f'<div style="{style}">Hi</div>')
                )

    def test_layout_margins_are_kept(self) -> None:
        for style in ("margin:0 auto", "margin:10px 0 !important", "margin-top:1.5em"):
            with self.subTest(style=style):
                once = sanitize_markup(f'<div style="{style}">Hi</div>')
                self.assertIn("margin", once)
                self.assertEqual(sanitize_markup(once), once)

    def test_document_head_is_dropped_with_its_text(self) -> None:
        """Scraped archive pages are whole documents; only the body's text remains."""
        page = (
            "<!DOCTYPE html><html><head><title>Ward 6 News</title>"
            '<meta charset="utf-8"><script>track()</script></head>'
            "<body><p>Leaf pickup starts Monday.</p></body></html>"
        )
        self.assertEqual(sanitize_markup(page), "<p>Leaf pickup starts Monday.</p>")

    def test_comments_are_dropped(self) -> None:
        self.assertEqual(sanitize_markup("<!--[if mso]><table><![endif]-->Hi"), "Hi")


class TestNewsletterMarkupIsKept(unittest.TestCase):
    def test_email_table_layout_is_kept(self) -> None:
        html = (
            '<table width="600" border="0" cellpadding="0" cellspacing="0" align="center">'
            '<tbody><tr><td valign="top" bgcolor="#ffffff" style="padding:10px">'
            '<font color="#333333" face="Arial">Leaf pickup</font></td></tr></tbody>'
            "</table>"
        )
        self.assertEqual(sanitize_markup(html), html)

    def test_links_and_images_are_kept(self) -> None:
        html = (
            '<a href="https://www.chicago.gov/311">311</a>'
            '<a href="mailto:ward06@example.org">Email</a>'
            '<a href="tel:+13125550100">Call</a>'
            '<img src="https://example.org/photo.jpg" alt="Park" width="300">'
        )
        sanitized = sanitize_markup(html)
        for kept in (
            'href="https://www.chicago.gov/311"',
            'href="mailto:ward06@example.org"',
            'href="tel:+13125550100"',
            'src="https://example.org/photo.jpg"',
            'alt="Park"',
        ):
            with self.subTest(kept=kept):
                self.assertIn(kept, sanitized)

    def test_links_cannot_reach_the_opener(self) -> None:
        sanitized = sanitize_markup('<a href="https://example.org">x</a>')
        self.assertIn('rel="noopener noreferrer"', sanitized)

    def test_text_is_kept_escaped(self) -> None:
        self.assertEqual(
            sanitize_markup("<p>Fish &amp; chips &lt;3</p>"),
            "<p>Fish &amp; chips &lt;3</p>",
        )

    def test_empty_input_is_empty(self) -> None:
        self.assertEqual(sanitize_markup(""), "")


class TestStoredNewsletterHtml(unittest.TestCase):
    """sanitize_newsletter_html: privacy redaction sees the markup a browser renders."""

    # A phrase split in the source that the HTML parser joins: text moved out of
    # a table, and a NUL dropped.
    JOINED_BY_THE_PARSER = (
        "<table>Jane<tr><td>x</td></tr> Doe</table>",
        "<li>Jane</li><table><caption>x</caption>Doe</table>",
        "<p>Ja\x00ne Doe</p>",
    )

    def test_phrases_joined_by_the_parser_are_redacted(self) -> None:
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": "Jane Doe"}):
            for html in self.JOINED_BY_THE_PARSER:
                with self.subTest(html=html):
                    once = sanitize_newsletter_html(html, PRIVACY_PATTERNS_DICT)
                    self.assertNotIn("Doe", once)
                    self.assertEqual(
                        sanitize_newsletter_html(once, PRIVACY_PATTERNS_DICT), once
                    )


if __name__ == "__main__":
    unittest.main()
