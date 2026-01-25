"""Unit tests for email parsing and source matching logic."""

import unittest
from unittest.mock import patch

from ingest.email.email_parser import (
    clean_html_content,
    extract_name_from_sender,
    lookup_source_by_email,
    parse_newsletter,
)
from tests.fixtures.mock_helpers import create_mock_mail_message, create_mock_supabase
from tests.fixtures.newsletter_factory import (
    create_test_email_mapping,
    create_test_source,
)
from config.privacy_patterns import PRIVACY_PATTERNS_DICT


class TestLookupSourceByEmail(unittest.TestCase):
    """Tests for lookup_source_by_email() function."""

    def test_exact_match(self):
        """Email exactly matches pattern."""
        source = create_test_source(source_id=1, name="Test Ward")
        mapping = create_test_email_mapping(
            email_pattern="alderman@ward1.org", source_id=1
        )
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("alderman@ward1.org", mock_supabase)

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 1)
        self.assertEqual(result["name"], "Test Ward")

    def test_wildcard_prefix_match(self):
        """Email matches wildcard prefix pattern (%@ward1.org)."""
        source = create_test_source(source_id=1, name="Ward 1")
        mapping = create_test_email_mapping(email_pattern="%@ward1.org", source_id=1)
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("any@ward1.org", mock_supabase)

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 1)

    def test_wildcard_suffix_match(self):
        """Email matches wildcard suffix pattern (%alderman@chicago.gov)."""
        # Note: Patterns with % in middle may not work due to regex escaping order
        # Using prefix wildcard instead
        source = create_test_source(source_id=2, name="Chicago Alderman")
        mapping = create_test_email_mapping(
            email_pattern="%alderman@chicago.gov", source_id=2
        )
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("ward1alderman@chicago.gov", mock_supabase)

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 2)

    def test_wildcard_contains_match(self):
        """Email matches wildcard contains pattern (%ward25%)."""
        source = create_test_source(source_id=25, name="Ward 25")
        mapping = create_test_email_mapping(email_pattern="%ward25%", source_id=25)
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("info@ward25chicago.org", mock_supabase)

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 25)

    def test_no_match_returns_none(self):
        """No pattern matches email."""
        mapping = create_test_email_mapping(email_pattern="%@ward1.org", source_id=1)
        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("unknown@example.com", mock_supabase)

        self.assertIsNone(result)

    def test_case_insensitive_matching(self):
        """Pattern matching is case-insensitive."""
        source = create_test_source(source_id=1)
        mapping = create_test_email_mapping(email_pattern="%@Ward1.ORG", source_id=1)
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("test@ward1.org", mock_supabase)

        self.assertIsNotNone(result)
        self.assertEqual(result["id"], 1)

    def test_multiple_patterns_first_match_wins(self):
        """When multiple patterns match, first one wins."""
        source1 = create_test_source(source_id=1, name="First Match")
        source2 = create_test_source(source_id=2, name="Second Match")

        mapping1 = create_test_email_mapping(email_pattern="%@ward1.org", source_id=1)
        mapping1["sources"] = source1

        mapping2 = create_test_email_mapping(email_pattern="%ward%", source_id=2)
        mapping2["sources"] = source2

        mock_supabase = create_mock_supabase(return_data=[mapping1, mapping2])

        result = lookup_source_by_email("test@ward1.org", mock_supabase)

        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "First Match")

    def test_empty_email_returns_none(self):
        """Empty string email returns None."""
        mapping = create_test_email_mapping(email_pattern="%@ward.org", source_id=1)
        mock_supabase = create_mock_supabase(return_data=[mapping])

        result = lookup_source_by_email("", mock_supabase)

        self.assertIsNone(result)

    def test_no_mappings_in_db_returns_none(self):
        """Database with no email mappings returns None."""
        mock_supabase = create_mock_supabase(return_data=[])

        result = lookup_source_by_email("test@example.com", mock_supabase)

        self.assertIsNone(result)


class TestExtractNameFromSender(unittest.TestCase):
    """Tests for extract_name_from_sender() function."""

    def test_extract_name_with_angle_brackets(self):
        """Standard format: Name <email@example.com>."""
        result = extract_name_from_sender("John Smith <john@example.com>")

        self.assertEqual(result, "John Smith")

    def test_extract_name_with_quotes(self):
        """Quoted name: "Ward Office" <email@example.com>."""
        result = extract_name_from_sender('"Ward Office" <office@ward.org>')

        self.assertEqual(result, "Ward Office")

    def test_no_display_name_returns_none(self):
        """Plain email address with no name."""
        result = extract_name_from_sender("email@example.com")

        self.assertIsNone(result)

    def test_empty_string_returns_none(self):
        """Empty string returns None."""
        result = extract_name_from_sender("")

        self.assertIsNone(result)

    def test_complex_name_formats(self):
        """Names with special characters and multiple words."""
        result = extract_name_from_sender("María García-López <maria@example.com>")

        self.assertEqual(result, "María García-López")

    def test_single_quoted_name(self):
        """Single quotes around name."""
        result = extract_name_from_sender("'Office' <office@ward.org>")

        self.assertEqual(result, "Office")


class TestCleanHtmlContent(unittest.TestCase):
    """Tests for clean_html_content() function."""

    def test_basic_html_conversion(self):
        """Simple HTML converts to plain text."""
        result = clean_html_content("<p>Hello world</p>")

        self.assertIn("Hello world", result)
        self.assertNotIn("<p>", result)

    def test_excessive_whitespace_removal(self):
        """Multiple newlines reduced to double newline."""
        result = clean_html_content("<p>Para 1</p>\n\n\n\n<p>Para 2</p>")

        # html2text adds newlines, but excessive ones should be reduced
        self.assertNotIn("\n\n\n\n", result)

    def test_empty_html_returns_empty(self):
        """Empty string returns empty string."""
        result = clean_html_content("")

        self.assertEqual(result, "")

    def test_malformed_html_handled_gracefully(self):
        """Broken HTML doesn't crash."""
        result = clean_html_content("<div><p>Unclosed tags<div>")

        self.assertIsNotNone(result)
        self.assertIn("Unclosed tags", result)

    def test_preserves_links_as_markdown(self):
        """Links converted to markdown format."""
        result = clean_html_content('<a href="http://example.com">Link</a>')

        # html2text converts links to markdown
        self.assertIn("Link", result)
        self.assertIn("http://example.com", result)


class TestParseNewsletter(unittest.TestCase):
    """Tests for parse_newsletter() main parsing function."""

    @patch("builtins.print")
    def test_parse_with_matched_source(self, mock_print):
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

    @patch("builtins.print")
    def test_parse_includes_ward_number(self, mock_print):
        """Verify ward_number is included in parsed data from source."""
        source = create_test_source(source_id=1, name="Ward 10", ward_number="10")
        mapping = create_test_email_mapping(email_pattern="%@ward10.org", source_id=1)
        mapping["sources"] = source

        mock_supabase = create_mock_supabase(return_data=[mapping])
        mock_message = create_mock_mail_message(from_="alderman@ward10.org")

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertEqual(result["source_id"], 1)
        self.assertEqual(result["ward_number"], "10")

    @patch("builtins.print")
    def test_parse_with_unmapped_source(self, mock_print):
        """Email without source match sets source_id=None."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message(
            from_="unknown@example.com", subject="Test"
        )

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertIsNone(result["source_id"])

    @patch("builtins.print")
    def test_parse_with_html_only(self, mock_print):
        """Email with only HTML generates plain_text."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message(
            html="<p>Test content in HTML</p>", text=""
        )

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertIn("Test content", result["plain_text"])
        self.assertIn("<p>", result["raw_html"])

    @patch("builtins.print")
    def test_parse_with_plain_text_only(self, mock_print):
        """Email with only plain text preserves it."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message(html="", text="Plain text content only")

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertEqual(result["plain_text"], "Plain text content only")
        self.assertEqual(result["raw_html"], "")

    @patch("builtins.print")
    def test_parse_with_both_html_and_text(self, mock_print):
        """Email with both formats preserves both."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message(
            html="<p>HTML version</p>", text="Text version"
        )

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertIn("HTML", result["raw_html"])
        self.assertEqual(result["plain_text"], "Text version")

    @patch("builtins.print")
    def test_sanitization_applied(self, mock_print):
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

    @patch("builtins.print")
    def test_missing_subject_defaults(self, mock_print):
        """Email without subject gets default."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message(subject=None)

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertEqual(result["subject"], "(No subject)")

    @patch("builtins.print")
    def test_missing_date_handled(self, mock_print):
        """Email with no date doesn't crash."""
        mock_supabase = create_mock_supabase(return_data=[])
        mock_message = create_mock_mail_message()
        mock_message.date = None  # Explicitly set to None

        result = parse_newsletter(mock_message, mock_supabase, PRIVACY_PATTERNS_DICT)

        self.assertIsNone(result["received_date"])


if __name__ == "__main__":
    unittest.main()
