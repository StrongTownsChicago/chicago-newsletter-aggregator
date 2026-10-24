"""Property-based tests: digest emails never turn newsletter or user text into markup."""

import unittest
from html.parser import HTMLParser
from typing import Any

from hypothesis import given
from hypothesis import strategies as st

from notifications.digest_config import DigestType
from notifications.digest_html import build_digest_html
from tests.fixtures.property_settings import PROPERTY_SETTINGS

# Subjects, summaries, source and rule names come from senders, the LLM and
# users; include the characters that would break out of text or an attribute.
FIELD_TEXT = st.text(
    alphabet=st.one_of(st.sampled_from("<>&\"'=/ "), st.characters(codec="utf-8")),
    max_size=40,
).filter(lambda text: text.strip() == text and "\n" not in text)
OPTIONAL_TEXT = st.one_of(st.just(""), FIELD_TEXT)


class TagCollector(HTMLParser):
    """Records each start tag with its attribute names, and all text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.tags: list[tuple[str, tuple[str, ...]]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append((tag, tuple(sorted(name for name, _ in attrs))))

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def parse(html: str) -> TagCollector:
    collector = TagCollector()
    collector.feed(html)
    collector.close()
    return collector


def neutralize(value: Any) -> Any:
    """The same data with every non-empty string replaced by plain text."""
    if isinstance(value, str):
        return "x" if value else ""
    if isinstance(value, list):
        return [neutralize(item) for item in value]
    if isinstance(value, dict):
        return {key: neutralize(item) for key, item in value.items()}
    return value


DAILY_NEWSLETTERS = st.lists(
    st.fixed_dictionaries(
        {
            "title": FIELD_TEXT,
            "source_name": FIELD_TEXT,
            "ward_text": OPTIONAL_TEXT,
            "date_formatted": FIELD_TEXT,
            "summary": OPTIONAL_TEXT,
            "topics": st.lists(FIELD_TEXT, max_size=6),
            "newsletter_url": FIELD_TEXT,
            "matched_rules": st.lists(FIELD_TEXT, max_size=3),
        }
    ),
    min_size=1,
    max_size=3,
)
WEEKLY_REPORTS = st.lists(
    st.fixed_dictionaries(
        {
            "topic": FIELD_TEXT,
            "topic_display": FIELD_TEXT,
            "summary": OPTIONAL_TEXT,
            "newsletter_count": st.integers(0, 50),
            "week_range": FIELD_TEXT,
            "week_id": FIELD_TEXT,
            "matched_rules": st.lists(FIELD_TEXT, min_size=1, max_size=3),
            "referenced_newsletters": st.lists(
                st.fixed_dictionaries(
                    {
                        "id": FIELD_TEXT,
                        "received_date": FIELD_TEXT,
                        "ward_number": st.one_of(st.none(), st.integers(1, 50)),
                        "subject": FIELD_TEXT,
                    }
                ),
                max_size=3,
            ),
        }
    ),
    min_size=1,
    max_size=3,
)
DIGESTS = st.one_of(
    st.tuples(DAILY_NEWSLETTERS, st.just(DigestType.DAILY)),
    st.tuples(WEEKLY_REPORTS, st.just(DigestType.WEEKLY)),
)


def render(prepared: list[dict[str, Any]], digest_type: DigestType, url: str) -> str:
    return build_digest_html(prepared, digest_type, url, url)


class TestDigestHtmlEscaping(unittest.TestCase):
    @PROPERTY_SETTINGS
    @given(DIGESTS, FIELD_TEXT)
    def test_field_text_never_changes_the_markup(
        self, digest: tuple[list[dict[str, Any]], DigestType], url: str
    ) -> None:
        prepared, digest_type = digest

        rendered = parse(render(prepared, digest_type, url))
        plain = parse(render(neutralize(prepared), digest_type, neutralize(url)))

        self.assertEqual(rendered.tags, plain.tags)

    @PROPERTY_SETTINGS
    @given(DAILY_NEWSLETTERS)
    def test_daily_text_reads_back_unchanged(
        self, prepared: list[dict[str, Any]]
    ) -> None:
        text = "".join(parse(render(prepared, DigestType.DAILY, "u")).text)

        for newsletter in prepared:
            for field in ("title", "source_name", "summary"):
                self.assertIn(newsletter[field], text)
            for topic in newsletter["topics"][:5]:
                self.assertIn(topic, text)

    @PROPERTY_SETTINGS
    @given(WEEKLY_REPORTS)
    def test_weekly_text_reads_back_unchanged(
        self, prepared: list[dict[str, Any]]
    ) -> None:
        text = "".join(parse(render(prepared, DigestType.WEEKLY, "u")).text)

        for report in prepared:
            self.assertIn(report["topic_display"], text)
            self.assertIn(report["summary"], text)
            for newsletter in report["referenced_newsletters"]:
                self.assertIn(newsletter["subject"], text)


if __name__ == "__main__":
    unittest.main()
