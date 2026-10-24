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
STRIP_PHRASE_NAMES = [
    "Jane Roe",
    "personal@example.com",
    "3125551234",
    "Ted",
    "Ed",
    "Act",
    "Dee",
]

WORDS = st.text(alphabet="abcdefghijklmnopqrstuvwxyz ", min_size=1, max_size=20)


def matches_any(patterns: list[str], value: str) -> bool:
    return any(re.search(pattern, value, re.IGNORECASE) for pattern in patterns)


def find_whole_phrase(text: str, phrases: list[str]) -> str | None:
    """
    Return the first phrase a reader can still see in text, if any.

    Read as rendered: whitespace runs count as one space, redaction markers
    hide what they replaced, and a phrase is only part of a longer word when
    a letter touches its first or last letter.
    """
    readable = re.sub(r"\s+", " ", text.replace("[REDACTED]", "|"))
    for phrase in phrases:
        before = r"(?<![^\W\d_])" if phrase[0].isalpha() else ""
        after = r"(?![^\W\d_])" if phrase[-1].isalpha() else ""
        words = re.escape(" ".join(phrase.split()))
        if re.search(before + words + after, readable, re.IGNORECASE):
            return phrase
    return None


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


# Pieces of a strip phrase, so a phrase ends up split around a link or inside
# inline tags, and entity-encoded forms of it.
INLINE_TEXT = st.one_of(
    ESCAPED_TEXT,
    st.sampled_from(
        [
            "Jane",
            "Jane ",
            " Roe",
            "Roe",
            "J<i>ane</i>",
            "<b>Roe</b>",
            "J&#97;ne R&#x6F;e",
            # Neighbours that must not hide a phrase: html2text emphasis, a
            # phone prefix, a block ending in a letter, a wrapped source line.
            "_Jane Roe_",
            "+13125551234",
            "<p>Contact</p>",
            "Jane\n   Roe",
        ]
    ),
)


def html_documents(leaves: st.SearchStrategy[str]) -> st.SearchStrategy[str]:
    """Nested divs and paragraphs around the given leaf fragments.

    Paragraphs mix loose text with leaves, as newsletters put links mid-sentence.
    """
    paragraphs = st.lists(st.one_of(leaves, INLINE_TEXT), min_size=1, max_size=6).map(
        lambda parts: f"<p>{''.join(parts)}</p>"
    )
    fragments = st.recursive(
        st.one_of(leaves, paragraphs),
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


@st.composite
def obfuscated_privacy_urls(draw: st.DrawFn) -> str:
    """A privacy URL as a browser would still follow it: tabs or newlines inside,
    percent-escaped characters, and mixed case."""
    url = draw(st.sampled_from(PRIVACY_URLS))
    scheme, rest = url.split("://", 1)
    characters = []
    for character in rest:
        if character.isalnum() and draw(st.booleans()):
            character = f"%{ord(character):02X}"
        elif draw(st.integers(0, 9)) == 0:
            character = draw(st.sampled_from(["\t", "\n"])) + character
        characters.append(character.upper() if draw(st.booleans()) else character)
    return f"{scheme}://{''.join(characters)}"


# Each line is generated as privacy-sensitive or not, so the expected output
# comes from how a line was made rather than from re-running the patterns.
# Plain text drops a line only when a privacy phrase is the whole line, so
# "unsubscribe from this list" and "Add us to your address book" stay.
STANDALONE_PRIVACY_TEXTS = [
    "Unsubscribe",
    "Update your profile",
    "Manage your preferences",
    "Forward to a friend",
    "View this email in your browser",
]
PRIVACY_LINES = st.one_of(
    st.sampled_from(STANDALONE_PRIVACY_TEXTS + PRIVACY_URLS),
    obfuscated_privacy_urls().map(lambda url: url.replace("\n", "")),
    st.builds(
        lambda words, url: f"{words} {url}", WORDS, st.sampled_from(PRIVACY_URLS)
    ),
)
BENIGN_LINES = st.one_of(BENIGN_TEXT, st.sampled_from(BENIGN_URLS))
TAGGED_TEXT_LINES = st.lists(
    st.one_of(
        PRIVACY_LINES.map(lambda line: (line, True)),
        BENIGN_LINES.map(lambda line: (line, False)),
    ),
    min_size=1,
    max_size=15,
)


def join_lines(tagged_lines: list[tuple[str, bool]]) -> str:
    return "\n".join(line for line, _ in tagged_lines)


TEXT_DOCUMENTS = TAGGED_TEXT_LINES.map(join_lines)
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


# Tests that expect no redaction must not inherit phrases from a developer's .env.
@patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": ""})
class TestHtmlSanitizationProperties(unittest.TestCase):
    @PROPERTY_SETTINGS
    @given(st.lists(obfuscated_privacy_urls(), min_size=1, max_size=4))
    def test_obfuscated_privacy_links_do_not_survive(self, urls: list[str]) -> None:
        document = "".join(f"<p>{link(url, 'here')}</p>" for url in urls)

        soup = BeautifulSoup(
            sanitize_content(document, "html", PRIVACY_PATTERNS_DICT), "html.parser"
        )

        self.assertEqual(soup.find_all("a"), [])

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

    @PROPERTY_SETTINGS
    @given(
        html_documents(LINKS),
        st.lists(st.sampled_from(STRIP_PHRASE_NAMES), min_size=1),
    )
    def test_strip_phrases_never_survive_in_a_text_or_attribute(
        self, document: str, phrases: list[str]
    ) -> None:
        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": ",".join(phrases)}):
            sanitized = sanitize_content(document, "html", PRIVACY_PATTERNS_DICT)

        soup = BeautifulSoup(sanitized, "html.parser")
        # The visible text joined with and without spaces at tag edges, plus
        # each string and attribute.
        values = [
            soup.get_text(""),
            soup.get_text(" "),
            *(str(text) for text in soup.find_all(string=True)),
            *(
                value if isinstance(value, str) else " ".join(value)
                for tag in soup.find_all(True)
                for value in tag.attrs.values()
            ),
        ]
        for value in values:
            self.assertIsNone(find_whole_phrase(value, phrases))


def with_neighbours(phrases: list[str]) -> str:
    """Each phrase plain, in html2text emphasis, after a phone prefix and in brackets."""
    return " ".join(f"{phrase} _{phrase}_ +1{phrase} ({phrase})" for phrase in phrases)


@patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": ""})
class TestTextSanitizationProperties(unittest.TestCase):
    @PROPERTY_SETTINGS
    @given(TAGGED_TEXT_LINES)
    def test_privacy_lines_go_and_other_lines_stay_in_order(
        self, tagged_lines: list[tuple[str, bool]]
    ) -> None:
        sanitized = sanitize_content(
            join_lines(tagged_lines), "text", PRIVACY_PATTERNS_DICT
        )

        expected = [line for line, is_private in tagged_lines if not is_private]
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
                f"{document}\n{with_neighbours(phrases)}", "text", PRIVACY_PATTERNS_DICT
            )

        self.assertIsNone(find_whole_phrase(sanitized, phrases))


if __name__ == "__main__":
    unittest.main()
