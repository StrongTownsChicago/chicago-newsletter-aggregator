"""Property-based tests for the markup sanitizer over generated tag soup."""

import os
import re
import unittest
from unittest.mock import patch

from bs4 import BeautifulSoup
from hypothesis import given
from hypothesis import strategies as st

from config.privacy_patterns import PRIVACY_PATTERNS_DICT
from ingest.email.email_parser import sanitize_newsletter_html
from ingest.markup_sanitizer import (
    ALLOWED_ATTRIBUTES,
    ALLOWED_TAGS,
    ALLOWED_URL_SCHEMES,
    sanitize_markup,
)
from tests.fixtures.property_settings import PROPERTY_SETTINGS
from tests.unit.test_sanitization_properties import (
    LINKS,
    STRIP_PHRASES,
    html_documents,
)

TAG_NAMES = st.sampled_from(
    [
        "p",
        "a",
        "img",
        "div",
        "table",
        "td",
        "font",
        "script",
        "style",
        "iframe",
        "svg",
        "math",
        "form",
        "input",
        "object",
        "noscript",
        "template",
        "title",
        "base",
        "meta",
    ]
)
ATTRIBUTE_NAMES = st.sampled_from(
    ["href", "src", "style", "class", "id", "onerror", "onclick", "xlink:href"]
)
URL_SCHEMES = st.sampled_from(
    ["https:", "javascript:", "JaVaScRiPt:", " java\tscript:", "data:", "", "/"]
)
ATTRIBUTE_VALUES = st.one_of(
    st.builds(lambda scheme, rest: scheme + rest, URL_SCHEMES, st.text(max_size=12)),
    st.sampled_from(["position:fixed;color:red", "alert(1)"]),
)
TEXT = st.text(alphabet="ab <>&\"'=/", max_size=10)


@st.composite
def tags(draw: st.DrawFn) -> str:
    """One opening tag with arbitrary attributes, text, and maybe its closing tag."""
    name = draw(TAG_NAMES)
    attributes = draw(
        st.lists(st.tuples(ATTRIBUTE_NAMES, ATTRIBUTE_VALUES), max_size=3)
    )
    rendered = "".join(
        f' {attribute}="{value.replace(chr(34), "&quot;")}"'
        for attribute, value in attributes
    )
    closing = f"</{name}>" if draw(st.booleans()) else ""
    return f"<{name}{rendered}>{draw(TEXT)}{closing}"


TAG_SOUP = st.lists(st.one_of(tags(), TEXT), max_size=12).map("".join)


def url_scheme(url: str) -> str | None:
    """The scheme a browser would read from url, lowercased; None if relative."""
    url = re.sub(r"[\t\n\r]", "", url).lstrip("".join(map(chr, range(0x21))))
    match = re.match(r"([a-zA-Z][a-zA-Z0-9+.-]*):", url)
    return match.group(1).lower() if match else None


class TestMarkupSanitizerProperties(unittest.TestCase):
    @PROPERTY_SETTINGS
    @given(TAG_SOUP)
    def test_only_allowed_tags_and_attributes_survive(self, html: str) -> None:
        soup = BeautifulSoup(sanitize_markup(html), "html.parser")

        for tag in soup.find_all(True):
            self.assertIn(tag.name, ALLOWED_TAGS)
            for attribute, value in tag.attrs.items():
                if attribute == "rel":  # set by the sanitizer on every link
                    continue
                self.assertIn(attribute, ALLOWED_ATTRIBUTES[tag.name])
                if attribute in ("href", "src"):
                    scheme = url_scheme(str(value))
                    self.assertTrue(scheme is None or scheme in ALLOWED_URL_SCHEMES)

    @PROPERTY_SETTINGS
    @given(TAG_SOUP)
    def test_sanitizing_twice_changes_nothing(self, html: str) -> None:
        once = sanitize_markup(html)
        self.assertEqual(sanitize_markup(once), once)

    @PROPERTY_SETTINGS
    @given(html_documents(LINKS), STRIP_PHRASES)
    def test_storage_pipeline_is_idempotent(
        self, document: str, strip_phrases: str
    ) -> None:
        """Reprocessing stored rows (privacy, then markup) changes nothing the second time."""

        with patch.dict(os.environ, {"PRIVACY_STRIP_PHRASES": strip_phrases}):
            once = sanitize_newsletter_html(document, PRIVACY_PATTERNS_DICT)
            self.assertEqual(
                sanitize_newsletter_html(once, PRIVACY_PATTERNS_DICT), once
            )


if __name__ == "__main__":
    unittest.main()
