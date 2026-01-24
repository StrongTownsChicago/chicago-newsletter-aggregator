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


class TestUserCases(unittest.TestCase):
    """
    Integration tests based on real-world user examples and edge cases.
    Verifies that privacy sanitization robustly handles complex HTML structures found in actual newsletters.
    """

    def test_case_1_daniel_la_spata(self):
        """
        Verify removal of mailchimp-specific preference/unsubscribe links
        embedded in complex footer structures (1st Ward example).
        """
        html = """
        <td valign="top" class="mcnTextContent">
            <p><strong>REQUESTS:</strong> <a href="mailto:info@the1stward.com">info@the1stward.com</a><br>
            <br>
            <strong>NEWSLETTER FEEDBACK:</strong> <a href="mailto:sophiamayen@the1stward.com">sophiamayen@the1stward.com</a></p>

            Want to change how you receive these emails?<br>
            You can <a href="https://1st-ward-alderman-daniel-la-spata.mailchimpsites.com/manage/preferences?u=e4d2e8115e36fe98f1fbf8f5f&id=218af5f0b5&e=a6f6131d3d&c=2f7c309981">update your preferences</a> or <a href="https://the1stward.us4.list-manage.com/unsubscribe?u=e4d2e8115e36fe98f1fbf8f5f&id=218af5f0b5&t=b&e=a6f6131d3d&c=2f7c309981">unsubscribe from this list</a>.
        </td>
        """
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS)

        # Ensure sensitive links are removed based on their URL patterns
        self.assertNotIn(
            "1st-ward-alderman-daniel-la-spata.mailchimpsites.com/manage/preferences",
            sanitized,
        )
        self.assertNotIn("the1stward.us4.list-manage.com/unsubscribe", sanitized)

    def test_case_2_compliance_links(self):
        """
        Verify removal of Constant Contact 'complianceLinks' table which contains
        unsubscribe and profile update links.
        """
        html = """
        <table class="complianceLinks complianceLinks--padding-vertical" width="100%" border="0" cellpadding="0" cellspacing="0"> 
            <tr> 
                <td class="complianceLinks_content-cell content-padding-horizontal"> 
                    <p style="margin: 0;"> 
                        <a href="https://visitor.constantcontact.com/do?p=un&m=001r86HdJl4hkGTgDfzqSqKMg==..." data-track="false">Unsubscribe</a>
                        <span> | </span>
                        <a href="https://visitor.constantcontact.com/do?ch=d1ca2354-e8de-11f0-9b67-024270638287&p=oo..." data-track="false">Update Profile</a>
                        <span> | </span>
                        <a href="https://www.constantcontact.com/legal/customer-contact-data-notice" data-track="false">Constant Contact Data Notice</a>
                    </p> 
                </td> 
            </tr> 
        </table>
        """
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS)

        # The container and specific links should be removed
        self.assertNotIn("complianceLinks", sanitized)
        self.assertNotIn("Unsubscribe", sanitized)
        self.assertNotIn("Update Profile", sanitized)

    def test_case_3_constant_contact_footer(self):
        """
        Test handling of generic Constant Contact footer images/logos.
        Currently, these benign logos are expected to match if they contain tracked links,
        or be preserved if they are just images. This test primarily ensures no exceptions occur.
        """
        html = """
        <table class="image_container-caption text" width="100%" border="0" cellpadding="0" cellspacing="0"> 
            <tr> 
                <td class="text_content-cell"> 
                    <a href="https://www.constantcontact.com/landing1/vr/home?cc=nge..." data-trackable="false">
                        <img class="image_content" src="https://imgssl.constantcontact.com/letters/images/CPE/referralLogos/H-Stacked-FC-WhiteBG-Email-Footer.png" alt="Constant Contact" align="center">
                    </a>  
                </td> 
            </tr> 
        </table>
        """
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS)
        # No specific removal assertion required for generic logos unless they become a privacy issue.
        self.assertIsNotNone(sanitized)

    def test_case_4_view_in_browser(self):
        """
        Verify removal of 'View in browser' links, a common pattern in newsletters.
        """
        html = """
        <p class="last-child">
            <a href="https://mailchi.mp/example?e=123">View this email in your browser</a>
        </p>
        """
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS)

        # Both the link URL and the anchor tag should be removed
        self.assertNotIn("mailchi.mp", sanitized)
        self.assertNotIn("<a href=", sanitized)

    def test_case_5_artifacts(self):
        """
        Verify robustness against artifacting.
        With the safer sanitization approach, we assert that SENSITIVE URLs are removed,
        but we explicitly accept that some surrounding text (like 'You can') may remain
        to avoid the risk of over-sanitizing valid content.
        """
        html = """
        <p>You can <a href="http://list-manage.com/profile">update your preferences</a> or <a href="http://list-manage.com/unsubscribe">unsubscribe</a></p>
        """
        sanitized = sanitize_content(html, "html", PRIVACY_PATTERNS)

        # Sensitive URLs must be gone
        self.assertNotIn("list-manage.com/profile", sanitized)
        self.assertNotIn("list-manage.com/unsubscribe", sanitized)

        # We accept that surrounding text might remain (Safe Fail)
        self.assertIn("You can", sanitized)


if __name__ == "__main__":
    unittest.main()
