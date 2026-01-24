import unittest
import sys
import os
import json
from pathlib import Path

# Add parent directory to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ingest.email.email_parser import sanitize_content

# Load privacy patterns for tests
privacy_config_path = Path(__file__).parent.parent / "config" / "privacy_patterns.json"
with open(privacy_config_path, "r", encoding="utf-8") as f:
    PRIVACY_PATTERNS = json.load(f)


class TestSanitization(unittest.TestCase):
    """
    Unit tests for the sanitize_content function.
    Verifies the removal of privacy-sensitive elements across HTML and Text content
    using both CSS selectors and URL regex patterns.
    """

    def test_sanitize_html_unsubscribe_link(self):
        """Test removal of unsubscribe links identified by recognized list-management domains."""
        html = """
        <html>
            <body>
                <p>Here is some content.</p>
                <a href="http://list-manage.com/unsubscribe">Unsubscribe here</a>
                <p>More content.</p>
            </body>
        </html>
        """
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS)
        self.assertNotIn("list-manage.com/unsubscribe", sanitized)
        self.assertIn("Here is some content", sanitized)

    def test_sanitize_html_manage_preferences(self):
        """Test removal of 'Manage Preferences' links for Mailchimp sites."""
        html = """
        <div>
            <a href="http://mailchimpsites.com/manage/preferences">Manage Preferences</a>
        </div>
        """
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS)
        self.assertNotIn("mailchimpsites.com/manage/preferences", sanitized)

    def test_sanitize_html_manage_profile(self):
        """Test removal of 'Update Profile' links for generic list management."""
        html = """
        <div>
             <a href="http://list-manage.com/profile">Update Profile</a>
        </div>
        """
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS)
        self.assertNotIn("list-manage.com/profile", sanitized)

    def test_sanitize_text_regex(self):
        """Test removal of standalone unsubscribe lines in plain text content."""
        text = "Some content.\nUnsubscribe\nMore content."
        sanitized = sanitize_content(text, "text", PRIVACY_PATTERNS)
        self.assertNotIn("Unsubscribe", sanitized)
        self.assertIn("Some content", sanitized)

    def test_sanitize_footer_class(self):
        """Test removal of entire containers identified by specific CSS classes (e.g. .footer-links)."""
        html = """
        <div class="footer-links">
            <a href="foo">Some link</a>
        </div>
        """
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS)
        self.assertNotIn("footer-links", sanitized)  # Div should be removed
        self.assertNotIn("Some link", sanitized)

    def test_sanitize_constant_contact(self):
        """Test specific selectors for Constant Contact compliance blocks."""
        html = """
        <table class="complianceLinks">
            <tr>
                <td>
                    <a href="https://visitor.constantcontact.com/do?p=un&m=001...">Unsubscribe</a>
                    <a href="https://visitor.constantcontact.com/do?p=oo&m=001...">Update Profile</a>
                </td>
            </tr>
        </table>
        """
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS)
        self.assertNotIn("complianceLinks", sanitized)
        self.assertNotIn("Unsubscribe", sanitized)
        self.assertNotIn("Update Profile", sanitized)

    def test_sanitize_mailchimp(self):
        """Test specific removal of Mailchimp list management links."""
        html = """
        <p>
            <a href="https://49thward.us18.list-manage.com/unsubscribe?u=...">unsubscribe from this list</a>
            <a href="https://49thward.us18.list-manage.com/profile?u=...">update subscription preferences</a>
        </p>
        """
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS)
        self.assertNotIn("unsubscribe from this list", sanitized)
        self.assertNotIn("update subscription preferences", sanitized)


if __name__ == "__main__":
    unittest.main()
