"""Property-based tests for privacy sanitization over generated newsletters."""

import html
import os
import re
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
from hypothesis import given
from hypothesis import strategies as st

from config.privacy_patterns import (
    PRIVACY_PATTERNS_DICT,
    SELECTORS,
    TEXT_PATTERNS,
    URL_PATTERNS,
)
from ingest.email.email_parser import sanitize_content
from tests.fixtures.property_settings import PROPERTY_SETTINGS

# One realistic URL per URL_PATTERNS entry; a test below keeps the two in step.
PRIVACY_URLS = [
    "https://40thward.us1.list-manage.com/unsubscribe?u=abc123&id=def456",
    "https://40thward.us1.list-manage.com/profile?u=abc123&id=def456",
    "https://us1.list-manage.com/about?u=abc123",
    "https://40thward.us1.list-manage.com/vcard?u=abc123",
    "https://40thward.us1.list-manage.com/track/click?u=abc&id=1&e=2",
    "https://visitor.constantcontact.com/do?mse=001&p=un&m=123",
    "https://visitor.constantcontact.com/do?mse=001&p=oo&m=123",
    "https://www.constantcontact.com/legal/customer-contact-data-notice",
    "https://40thward.mailchimpsites.com/manage/preferences?u=abc",
    "https://mailchi.mp/40thward/newsletter?e=abc123",
    "https://click.sparkpostmail.com/f/a/xyz/unsubscribe",
    "https://www.forward-to-friend.com/forward?u=abc",
    "https://r20.rs6.net/tn.jsp?f=001abc",
    "https://www.constantcontact.com/landing1/vr/home",
    "https://login.mailchimp.com/signup/?source=footer",
    "https://us1.campaign-archive.com/?u=abc&id=def",
]
PRIVACY_LINK_TEXTS = [
    "Unsubscribe",
    "unsubscribe from this list",
    "Update your profile",
    "Manage your preferences",
    "Update subscription preferences",
    "Forward to a friend",
    "View this email in your browser",
    "Read it in your browser",
    "Add us to your address book",
]
BENIGN_URLS = [
    "https://www.chicago.gov/city/en/depts/cdot.html",
    "https://40thward.org/events",
    "https://www.cityofchicago.org/311",
    "mailto:ward40@cityofchicago.org",
]
BENIGN_CLASSES = ["content", "header", "mcnTextContent"]
STRIP_PHRASE_NAMES = ["Jane Roe", "personal@example.com", "Ted", "Ed", "Act", "Dee"]

WORDS = st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=20)


def matches_any(patterns: list[str], value: str) -> bool:
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)


def is_standalone_keyword(line: str) -> bool:
    return any(
        re.match(rf"^\s*{pattern}\s*$", line, re.IGNORECASE)
        for pattern in TEXT_PATTERNS
    )


BENIGN_TEXT = WORDS.filter(lambda text: not matches_any(TEXT_PATTERNS, text))


def link(href: str, inner_html: str) -> str:
    return f'<a href="{html.escape(href)}">{inner_html}</a>'


IMAGE = st.just('<img src="photo.jpg" alt="">')
ESCAPED_TEXT = WORDS.map(html.escape)
LINK_TEXT = st.one_of(st.sampled_from(PRIVACY_LINK_TEXTS), BENIGN_TEXT).map(html.escape)
LINKS = st.builds(
    link,
    st.one_of(st.sampled_from(PRIVACY_URLS), st.sampled_from(BENIGN_URLS)),
    st.one_of(LINK_TEXT, IMAGE),
)
BENIGN_LINKS = st.builds(
    link, st.sampled_from(BENIGN_URLS), st.one_of(BENIGN_TEXT.map(html.escape), IMAGE)
)


def container(css_class: str, children: list[str]) -> str:
    """Wrap children in a div whose class or id is the selector's name."""
    attribute = "id" if css_class.startswith("#") else "class"
    return f'<div {attribute}="{css_class.lstrip(".#")}">{"".join(children)}</div>'


def html_documents(leaves: st.SearchStrategy[str]) -> st.SearchStrategy[str]:
    """Nested divs and paragraphs around the given leaf fragments."""
    fragments = st.recursive(
        st.one_of(leaves, ESCAPED_TEXT.map(lambda text: f"<p>{text}</p>")),
        lambda children: st.builds(
            container,
            st.sampled_from(BENIGN_CLASSES + SELECTORS),
            st.lists(children, min_size=1, max_size=4),
        ),
        max_leaves=12,
    )
    return st.lists(fragments, min_size=1, max_size=6).map(
        lambda parts: f"<html><body>{''.join(parts)}</body></html>"
    )


def benign_documents() -> st.SearchStrategy[str]:
    """Documents with no privacy links and no selector containers."""
    fragments = st.recursive(
        st.one_of(BENIGN_LINKS, ESCAPED_TEXT.map(lambda text: f"<p>{text}</p>")),
        lambda children: st.builds(
            container,
            st.sampled_from(BENIGN_CLASSES),
            st.lists(children, min_size=1, max_size=4),
        ),
        max_leaves=12,
    )
    return st.lists(fragments, min_size=1, max_size=6).map("".join)


TEXT_LINES = st.one_of(
    WORDS,
    st.sampled_from(PRIVACY_LINK_TEXTS),
    st.sampled_from(PRIVACY_URLS + BENIGN_URLS),
    st.builds(
        lambda words, url: f"{words} {url}", WORDS, st.sampled_from(PRIVACY_URLS)
    ),
)
TEXT_DOCUMENTS = st.lists(TEXT_LINES, min_size=1, max_size=15).map("\n".join)
STRIP_PHRASES = st.lists(
    st.one_of(st.sampled_from(STRIP_PHRASE_NAMES), WORDS), max_size=3
).map(",".join)


class TestPrivacyFixtureSamples(unittest.TestCase):
    """The generators exercise every configured privacy pattern."""

    def test_every_url_pattern_has_a_sample_url(self) -> None:
        for pattern in URL_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertTrue(matches_any([pattern], " ".join(PRIVACY_URLS)))

    def test_every_text_pattern_has_a_sample_link_text(self) -> None:
        for pattern in TEXT_PATTERNS:
            with self.subTest(pattern=pattern):
                self.assertTrue(
                    any(matches_any([pattern], text) for text in PRIVACY_LINK_TEXTS)
                )

    def test_benign_samples_match_no_pattern(self) -> None:
        for url in BENIGN_URLS:
            with self.subTest(url=url):
                self.assertFalse(matches_any(URL_PATTERNS, url))


class TestHtmlSanitizationProperties(unittest.TestCase):
    @PROPERTY_SETTINGS
    @given(html_documents(LINKS))
    def test_no_privacy_link_or_container_survives(self, document: str) -> None:
        soup = BeautifulSoup(
            sanitize_content(document, "html", PRIVACY_PATTERNS_DICT), "html.parser"
        )

        for anchor in soup.find_all("a", href=True):
            self.assertFalse(matches_any(URL_PATTERNS, str(anchor["href"])))
            self.assertFalse(
                matches_any(TEXT_PATTERNS, anchor.get_text(" ", strip=True))
            )
        for selector in SELECTORS:
            self.assertEqual(soup.select(selector), [])

    @PROPERTY_SETTINGS
    @given(benign_documents())
    def test_benign_links_are_kept(self, document: str) -> None:
        def hrefs(markup: str) -> list[str]:
            soup = BeautifulSoup(markup, "html.parser")
            return [str(anchor["href"]) for anchor in soup.find_all("a", href=True)]

        sanitized = sanitize_content(document, "html", PRIVACY_PATTERNS_DICT)

        self.assertEqual(hrefs(sanitized), hrefs(document))

    @PROPERTY_SETTINGS
    @given(html_documents(LINKS), STRIP_PHRASES)
    def test_sanitizing_twice_changes_nothing(
        self, document: str, strip_phrases: str
    ) -> None:
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": strip_phrases}):
            once = sanitize_content(document, "html", PRIVACY_PATTERNS_DICT)
            twice = sanitize_content(once, "html", PRIVACY_PATTERNS_DICT)

        self.assertEqual(twice, once)


class TestTextSanitizationProperties(unittest.TestCase):
    @PROPERTY_SETTINGS
    @given(TEXT_DOCUMENTS)
    def test_no_privacy_line_survives(self, document: str) -> None:
        sanitized = sanitize_content(document, "text", PRIVACY_PATTERNS_DICT)

        for line in sanitized.splitlines():
            self.assertFalse(matches_any(URL_PATTERNS, line))
            self.assertFalse(is_standalone_keyword(line))

    @PROPERTY_SETTINGS
    @given(TEXT_DOCUMENTS)
    def test_other_lines_are_kept_in_order(self, document: str) -> None:
        expected = [
            line
            for line in document.splitlines()
            if not matches_any(URL_PATTERNS, line) and not is_standalone_keyword(line)
        ]

        sanitized = sanitize_content(document, "text", PRIVACY_PATTERNS_DICT)

        self.assertEqual(sanitized.splitlines(), expected)

    @PROPERTY_SETTINGS
    @given(TEXT_DOCUMENTS, STRIP_PHRASES)
    def test_sanitizing_twice_changes_nothing(
        self, document: str, strip_phrases: str
    ) -> None:
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": strip_phrases}):
            once = sanitize_content(document, "text", PRIVACY_PATTERNS_DICT)
            twice = sanitize_content(once, "text", PRIVACY_PATTERNS_DICT)

        self.assertEqual(twice, once)

    @PROPERTY_SETTINGS
    @given(TEXT_DOCUMENTS, st.lists(st.sampled_from(STRIP_PHRASE_NAMES), min_size=1))
    def test_strip_phrases_never_survive(
        self, document: str, phrases: list[str]
    ) -> None:
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": ",".join(phrases)}):
            sanitized = sanitize_content(
                f"{document}\n{' '.join(phrases)}", "text", PRIVACY_PATTERNS_DICT
            )

        unredacted_spans = sanitized.lower().split("[redacted]")
        for phrase in phrases:
            for span in unredacted_spans:
                self.assertNotIn(phrase.lower(), span)


if __name__ == "__main__":
    unittest.main()
