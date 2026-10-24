"""Unit tests for email parsing and source matching logic."""

import unittest

from config.privacy_patterns import PRIVACY_PATTERNS_DICT
from ingest.email.email_parser import (
    clean_html_content,
    email_matches_pattern,
    lookup_source_by_email,
    parse_newsletter,
)
from tests.fixtures.mock_helpers import create_mock_mail_message, create_mock_supabase
from tests.fixtures.newsletter_factory import (
    create_test_email_mapping,
    create_test_source,
)
from tests.fixtures.quiet_logging import quiet_logger


def setUpModule() -> None:
    quiet_logger("ingest.email.email_parser")


class TestEmailMatchesPattern(unittest.TestCase):
    """Tests for email_matches_pattern() pure matching function."""

    def test_exact_match(self) -> None:
        self.assertTrue(
            email_matches_pattern("info@the1stward.com", "info@the1stward.com")
        )

    def test_exact_pattern_rejects_substring_of_sender(self) -> None:
        """Exact patterns must not match senders that merely contain them."""
        self.assertFalse(
            email_matches_pattern("info@the1stward.com.evil.io", "info@the1stward.com")
        )
        self.assertFalse(
            email_matches_pattern("xinfo@the1stward.com", "info@the1stward.com")
        )

    def test_exact_pattern_rejects_sender_that_is_substring_of_pattern(self) -> None:
        self.assertFalse(email_matches_pattern("ward09", "ward09@cityofchicago.org"))

    def test_leading_wildcard(self) -> None:
        self.assertTrue(
            email_matches_pattern("ward27@redburnett.com", "%@redburnett.com")
        )

    def test_leading_wildcard_rejects_domain_suffix_overmatch(self) -> None:
        self.assertFalse(
            email_matches_pattern("x@redburnett.com.evil.io", "%@redburnett.com")
        )

    def test_leading_wildcard_rejects_lookalike_domain(self) -> None:
        """'.' in the pattern is literal, not a regex any-character."""
        self.assertFalse(email_matches_pattern("x@redburnettxcom", "%@redburnett.com"))

    def test_trailing_wildcard(self) -> None:
        self.assertTrue(email_matches_pattern("ward23@cityofchicago.org", "ward23@%"))
        self.assertFalse(email_matches_pattern("xward23@cityofchicago.org", "ward23@%"))

    def test_mid_pattern_wildcard(self) -> None:
        pattern = "nicolelee11thwardchi%@shared1.ccsend.com"
        self.assertTrue(
            email_matches_pattern(
                "nicolelee11thwardchi-gmail.com@shared1.ccsend.com", pattern
            )
        )
        self.assertFalse(
            email_matches_pattern(
                "nicolelee11thwardchi-gmail.com@shared1.ccsend.com.evil.io", pattern
            )
        )

    def test_multiple_wildcards(self) -> None:
        self.assertTrue(
            email_matches_pattern(
                "nicolelee11thwardchi-gmail.com@ward11.ccsend.com",
                "nicolelee11thwardchi%@%.ccsend.com",
            )
        )

    def test_wildcard_matches_empty_run(self) -> None:
        self.assertTrue(
            email_matches_pattern("ward@chicago14.com", "ward%@chicago14.com")
        )

    def test_case_insensitive(self) -> None:
        self.assertTrue(
            email_matches_pattern(
                "Ward23@CityOfChicago.org", "ward23@cityofchicago.org"
            )
        )
        self.assertTrue(email_matches_pattern("info@40thward.org", "%@40THWARD.ORG"))

    def test_surrounding_whitespace_ignored(self) -> None:
        self.assertTrue(
            email_matches_pattern(" x@aldermanervin.com ", " %@aldermanervin.com")
        )

    def test_regex_metacharacters_are_literal(self) -> None:
        pattern = "yourvoice+newsletter@ward43.org"
        self.assertTrue(
            email_matches_pattern("yourvoice+newsletter@ward43.org", pattern)
        )
        self.assertFalse(
            email_matches_pattern("yourvoiceeenewsletter@ward43.org", pattern)
        )
        self.assertFalse(email_matches_pattern("ward1@x.org", "ward[0-9]@x.org"))
        self.assertTrue(email_matches_pattern("ward[0-9]@x.org", "ward[0-9]@x.org"))

    def test_underscore_is_literal_not_wildcard(self) -> None:
        self.assertTrue(email_matches_pattern("ward_1@x.org", "ward_1@x.org"))
        self.assertFalse(email_matches_pattern("wardA1@x.org", "ward_1@x.org"))

    def test_empty_email_never_matches(self) -> None:
        self.assertFalse(email_matches_pattern("", "info@the1stward.com"))
        self.assertFalse(email_matches_pattern("", "%"))

    def test_empty_pattern_never_matches(self) -> None:
        self.assertFalse(email_matches_pattern("info@the1stward.com", ""))


class TestLookupSourceByEmail(unittest.TestCase):
    """Tests for lookup_source_by_email() function."""

    def test_exact_match(self) -> None:
        """Email exactly matches pattern."""
        source = create_test_source(source_id=1, name="Test Ward")
        mapping = create_test_email_mapping(
            email_pattern="alderman@ward1.org", source_id=1
        )
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("alderman@ward1.org", mock_supabase)

        assert result is not None
        self.assertEqual(result["id"], 1)
        self.assertEqual(result["name"], "Test Ward")

    def test_wildcard_prefix_match(self) -> None:
        """Email matches wildcard prefix pattern (%@ward1.org)."""
        source = create_test_source(source_id=1, name="Ward 1")
        mapping = create_test_email_mapping(email_pattern="%@ward1.org", source_id=1)
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("any@ward1.org", mock_supabase)

        assert result is not None
        self.assertEqual(result["id"], 1)

    def test_wildcard_suffix_match(self) -> None:
        """Email matches wildcard suffix pattern (%alderman@chicago.gov)."""
        source = create_test_source(source_id=2, name="Chicago Alderman")
        mapping = create_test_email_mapping(
            email_pattern="%alderman@chicago.gov", source_id=2
        )
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("ward1alderman@chicago.gov", mock_supabase)

        assert result is not None
        self.assertEqual(result["id"], 2)

    def test_wildcard_contains_match(self) -> None:
        """Email matches wildcard contains pattern (%ward25%)."""
        source = create_test_source(source_id=25, name="Ward 25")
        mapping = create_test_email_mapping(email_pattern="%ward25%", source_id=25)
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("info@ward25chicago.org", mock_supabase)

        assert result is not None
        self.assertEqual(result["id"], 25)

    def test_no_match_returns_none(self) -> None:
        """No pattern matches email."""
        mapping = create_test_email_mapping(email_pattern="%@ward1.org", source_id=1)
        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("unknown@example.com", mock_supabase)

        self.assertIsNone(result)

    def test_case_insensitive_matching(self) -> None:
        """Pattern matching is case-insensitive."""
        source = create_test_source(source_id=1)
        mapping = create_test_email_mapping(email_pattern="%@Ward1.ORG", source_id=1)
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("test@ward1.org", mock_supabase)

        assert result is not None
        self.assertEqual(result["id"], 1)

    def test_multiple_patterns_first_match_wins(self) -> None:
        """When multiple patterns match, first one wins."""
        source1 = create_test_source(source_id=1, name="First Match")
        source2 = create_test_source(source_id=2, name="Second Match")

        mapping1 = create_test_email_mapping(email_pattern="%@ward1.org", source_id=1)
        mapping1["sources"] = source1

        mapping2 = create_test_email_mapping(email_pattern="%ward%", source_id=2)
        mapping2["sources"] = source2

        mock_supabase = create_mock_supabase(return_data=[mapping1, mapping2])

        result = lookup_source_by_email("test@ward1.org", mock_supabase)

        assert result is not None
        self.assertEqual(result["name"], "First Match")

    def test_mid_pattern_wildcard_match(self) -> None:
        """Wildcard in the middle of a pattern resolves the source."""
        source = create_test_source(source_id=11, name="Ward 11")
        mapping = create_test_email_mapping(
            email_pattern="nicolelee11thwardchi%@shared1.ccsend.com", source_id=11
        )
        mapping["sources"] = source
        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email(
            "nicolelee11thwardchi-gmail.com@shared1.ccsend.com", mock_supabase
        )

        assert result is not None
        self.assertEqual(result["id"], 11)

    def test_exact_pattern_does_not_substring_match(self) -> None:
        """Exact patterns no longer match senders that merely contain them."""
        mapping = create_test_email_mapping(
            email_pattern="info@the1stward.com", source_id=1
        )
        mapping["sources"] = create_test_source(source_id=1)
        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("info@the1stward.com.evil.io", mock_supabase)

        self.assertIsNone(result)

    def test_empty_email_does_not_match_exact_pattern(self) -> None:
        """Empty sender must not match exact patterns (was a substring bug)."""
        mapping = create_test_email_mapping(
            email_pattern="info@the1stward.com", source_id=1
        )
        mapping["sources"] = create_test_source(source_id=1)
        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("", mock_supabase)

        self.assertIsNone(result)

    def test_empty_email_returns_none(self) -> None:
        """Empty string email returns None."""
        mapping = create_test_email_mapping(email_pattern="%@ward.org", source_id=1)
        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("", mock_supabase)

        self.assertIsNone(result)

    def test_no_mappings_in_db_returns_none(self) -> None:
        """Database with no email mappings returns None."""
        mock_supabase = create_mock_supabase(return_data=[])

        result = lookup_source_by_email("test@example.com", mock_supabase)

        self.assertIsNone(result)


class TestCleanHtmlContent(unittest.TestCase):
    """Tests for clean_html_content() function."""

    def test_basic_html_conversion(self) -> None:
        """Simple HTML converts to plain text."""
        result = clean_html_content("<p>Hello world</p>")

        self.assertIn("Hello world", result)
        self.assertNotIn("<p>", result)

    def test_excessive_whitespace_removal(self) -> None:
        """Multiple newlines reduced to double newline."""
        result = clean_html_content("<p>Para 1</p>\n\n\n\n<p>Para 2</p>")

        # html2text adds newlines, but excessive ones should be reduced
        self.assertNotIn("\n\n\n\n", result)

    def test_empty_html_returns_empty(self) -> None:
        """Empty string returns empty string."""
        result = clean_html_content("")

        self.assertEqual(result, "")

    def test_malformed_html_handled_gracefully(self) -> None:
        """Broken HTML doesn't crash."""
        result = clean_html_content("<div><p>Unclosed tags<div>")

        assert result is not None
        self.assertIn("Unclosed tags", result)

    def test_preserves_links_as_markdown(self) -> None:
        """Links converted to markdown format."""
        result = clean_html_content('<a href="http://example.com">Link</a>')

        # html2text converts links to markdown
        self.assertIn("Link", result)
        self.assertIn("http://example.com", result)


class TestParseNewsletter(unittest.TestCase):
    """Tests for parse_newsletter() main parsing function."""

    def test_parse_with_matched_source(self) -> None:
        """Email with source match sets source_id."""
        source = create_test_source(source_id=1, name="Test Ward")
        mapping = create_test_email_mapping(email_pattern="%@ward1.org", source_id=1)
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])
        mock_message = create_mock_mail_message(
            from_="alderman@ward1.org",
            subject="Test Subject",
            html="<p>Test content</p>",
        )

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertEqual(result["source_id"], 1)
        self.assertEqual(result["subject"], "Test Subject")

    def test_parse_includes_ward_number(self) -> None:
        """Verify ward_number is included in parsed data from source."""
        source = create_test_source(source_id=1, name="Ward 10", ward_number=10)
        mapping = create_test_email_mapping(email_pattern="%@ward10.org", source_id=1)
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])
        mock_message = create_mock_mail_message(from_="alderman@ward10.org")

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertEqual(result["source_id"], 1)
        self.assertEqual(result["ward_number"], 10)

    def test_parse_with_unmapped_source(self) -> None:
        """Email without source match sets source_id=None."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message(
            from_="unknown@example.com", subject="Test"
        )

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertIsNone(result["source_id"])

    def test_parse_with_html_only(self) -> None:
        """Email with only HTML generates plain_text."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message(
            html="<p>Test content in HTML</p>", text=""
        )

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertIn("Test content", result["plain_text"])
        self.assertIn("<p>", result["raw_html"])

    def test_parse_with_plain_text_only(self) -> None:
        """Email with only plain text preserves it."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message(html="", text="Plain text content only")

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertEqual(result["plain_text"], "Plain text content only")
        self.assertEqual(result["raw_html"], "")

    def test_parse_with_both_html_and_text(self) -> None:
        """Email with both formats preserves both."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message(
            html="<p>HTML version</p>", text="Text version"
        )

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertIn("HTML", result["raw_html"])
        self.assertEqual(result["plain_text"], "Text version")

    def test_sanitization_applied(self) -> None:
        """Privacy sanitization removes unsubscribe links."""
        mock_supabase = create_mock_supabase(return_data=[])
        html_with_unsubscribe = """
        <p>Content</p>
        <a href="http://list-manage.com/unsubscribe">Unsubscribe</a>
        """
        mock_message = create_mock_mail_message(html=html_with_unsubscribe)

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        # Unsubscribe link should be removed
        self.assertNotIn("list-manage.com/unsubscribe", result["raw_html"])

    def test_plain_text_body_is_sanitized(self) -> None:
        """The email's own plain text part is sanitized, not only the HTML."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message(
            text="Content\nUnsubscribe\nhttps://x.list-manage.com/unsubscribe?u=1"
        )

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertEqual(result["plain_text"], "Content")

    def test_to_email_is_the_first_recipient(self) -> None:
        """to_email is the first recipient, or empty when there is none."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message(
            to=["first@example.com", "second@example.com"]
        )

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)
        mock_message.to = []
        no_recipient = parse_newsletter(
            mock_message, mock_supabase, PRIVACY_PATTERNS_DICT
        )

        self.assertEqual(result["to_email"], "first@example.com")
        self.assertEqual(no_recipient["to_email"], "")

    def test_missing_subject_defaults(self) -> None:
        """Email without subject gets default."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message(subject=None)

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertEqual(result["subject"], "(No subject)")

    def test_missing_date_handled(self) -> None:
        """Email with no date doesn't crash."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message()
        mock_message.date = None  # Explicitly set to None

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertIsNone(result["received_date"])


if __name__ == "__main__":
    unittest.main()
