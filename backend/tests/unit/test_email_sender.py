"""
Unit tests for notifications/email_sender.py

Tests email digest preparation, HTML/text template generation,
and Resend API integration.
"""

import unittest
from unittest.mock import patch

from notifications.email_sender import (
    _prepare_newsletter_data,
    send_daily_digest,
    _build_digest_html,
    _build_digest_text,
)
from tests.fixtures.newsletter_factory import create_test_newsletter, create_test_source


class TestPrepareNewsletterData(unittest.TestCase):
    """Tests for _prepare_newsletter_data() function."""

    def test_groups_by_newsletter(self):
        """Multiple rules matching same newsletter are grouped."""
        newsletter = create_test_newsletter(id="nl_123", subject="Test Newsletter")

        notifications = [
            {
                "newsletter": newsletter,
                "rule": {"name": "Rule 1"},
            },
            {
                "newsletter": newsletter,
                "rule": {"name": "Rule 2"},
            },
        ]

        result = _prepare_newsletter_data(notifications)

        self.assertEqual(len(result), 1)
        self.assertEqual(len(result[0]["matched_rules"]), 2)
        self.assertIn("Rule 1", result[0]["matched_rules"])
        self.assertIn("Rule 2", result[0]["matched_rules"])

    def test_extracts_source_info(self):
        """Source name and ward number extracted correctly."""
        source = create_test_source(source_id=1, name="Test Alderman", ward_number=25)
        newsletter = create_test_newsletter(source_id=1)
        newsletter["source"] = source

        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = _prepare_newsletter_data(notifications)

        self.assertEqual(result[0]["source_name"], "Test Alderman")
        self.assertEqual(result[0]["ward_text"], " (Ward 25)")

    def test_formats_date(self):
        """ISO format date converted to readable format."""
        newsletter = create_test_newsletter(received_date="2026-01-24T12:30:00+00:00")

        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = _prepare_newsletter_data(notifications)

        self.assertEqual(result[0]["date_formatted"], "January 24, 2026")

    def test_handles_missing_date(self):
        """Missing date defaults to 'Unknown date'."""
        # Use overrides to bypass the factory's default logic
        newsletter = create_test_newsletter()
        newsletter["received_date"] = ""  # Set to empty string after creation

        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = _prepare_newsletter_data(notifications)

        self.assertEqual(result[0]["date_formatted"], "Unknown date")

    def test_handles_missing_source(self):
        """Missing source defaults to 'Unknown Source'."""
        newsletter = create_test_newsletter(source_id=None)
        newsletter["source"] = None

        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = _prepare_newsletter_data(notifications)

        self.assertEqual(result[0]["source_name"], "Unknown Source")
        self.assertEqual(result[0]["ward_text"], "")

    def test_builds_newsletter_url(self):
        """Newsletter URL constructed with FRONTEND_BASE_URL."""
        newsletter = create_test_newsletter(id="nl_abc123")

        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = _prepare_newsletter_data(notifications)

        self.assertIn("nl_abc123", result[0]["newsletter_url"])

    def test_sorts_by_received_date(self):
        """Newsletters sorted by received date, most recent first."""
        newsletter1 = create_test_newsletter(
            id="nl_1", received_date="2026-01-24T10:00:00"
        )
        newsletter2 = create_test_newsletter(
            id="nl_2", received_date="2026-01-24T14:00:00"
        )

        notifications = [
            {"newsletter": newsletter1, "rule": {"name": "Rule 1"}},
            {"newsletter": newsletter2, "rule": {"name": "Rule 1"}},
        ]

        result = _prepare_newsletter_data(notifications)

        # Most recent should be first
        self.assertIn("nl_2", result[0]["newsletter_url"])
        self.assertIn("nl_1", result[1]["newsletter_url"])

    def test_collects_matched_rules(self):
        """Rule names collected for each newsletter."""
        newsletter = create_test_newsletter()

        notifications = [
            {"newsletter": newsletter, "rule": {"name": "Zoning Updates"}},
            {"newsletter": newsletter, "rule": {"name": "Bike Lanes"}},
        ]

        result = _prepare_newsletter_data(notifications)

        self.assertIn("Zoning Updates", result[0]["matched_rules"])
        self.assertIn("Bike Lanes", result[0]["matched_rules"])

    def test_empty_notifications_returns_empty(self):
        """Empty notifications list returns empty result."""
        result = _prepare_newsletter_data([])

        self.assertEqual(result, [])


class TestSendDailyDigest(unittest.TestCase):
    """Tests for send_daily_digest() function."""

    @patch("notifications.email_sender.resend.Emails.send")
    def test_send_success(self, mock_send):
        """Email sent successfully via Resend API."""
        mock_send.return_value = {"id": "email_123"}

        newsletter = create_test_newsletter()
        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = send_daily_digest("user@example.com", notifications)

        self.assertTrue(result["success"])
        self.assertEqual(result["email_id"], "email_123")
        mock_send.assert_called_once()

    @patch("notifications.email_sender.resend.Emails.send")
    def test_send_failure(self, mock_send):
        """Resend API error handled gracefully."""
        mock_send.side_effect = Exception("API Error")

        newsletter = create_test_newsletter()
        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        result = send_daily_digest("user@example.com", notifications)

        self.assertFalse(result["success"])
        self.assertIn("API Error", result["error"])

    def test_empty_notifications_returns_error(self):
        """Empty notifications list returns error."""
        result = send_daily_digest("user@example.com", [])

        self.assertFalse(result["success"])
        self.assertIn("No notifications", result["error"])

    @patch("notifications.email_sender.resend.Emails.send")
    def test_uses_default_preferences_url(self, mock_send):
        """Default preferences URL used when not provided."""
        mock_send.return_value = {"id": "email_123"}

        newsletter = create_test_newsletter()
        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        send_daily_digest("user@example.com", notifications)

        # Check that HTML contains preferences link
        call_args = mock_send.call_args[0][0]
        self.assertIn("/preferences", call_args["html"])

    @patch("notifications.email_sender.resend.Emails.send")
    def test_uses_custom_preferences_url(self, mock_send):
        """Custom preferences URL used when provided."""
        mock_send.return_value = {"id": "email_123"}

        newsletter = create_test_newsletter()
        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        send_daily_digest(
            "user@example.com",
            notifications,
            preferences_url="https://custom.com/prefs",
        )

        call_args = mock_send.call_args[0][0]
        self.assertIn("https://custom.com/prefs", call_args["html"])

    @patch("notifications.email_sender.resend.Emails.send")
    def test_subject_includes_count(self, mock_send):
        """Subject line includes newsletter count."""
        mock_send.return_value = {"id": "email_123"}

        newsletter1 = create_test_newsletter(id="nl_1")
        newsletter2 = create_test_newsletter(id="nl_2")
        notifications = [
            {"newsletter": newsletter1, "rule": {"name": "Rule 1"}},
            {"newsletter": newsletter2, "rule": {"name": "Rule 1"}},
        ]

        send_daily_digest("user@example.com", notifications)

        call_args = mock_send.call_args[0][0]
        self.assertIn("2 newsletters", call_args["subject"])

    @patch("notifications.email_sender.resend.Emails.send")
    def test_calls_resend_api(self, mock_send):
        """Resend API called with correct parameters."""
        mock_send.return_value = {"id": "email_123"}

        newsletter = create_test_newsletter()
        notifications = [{"newsletter": newsletter, "rule": {"name": "Rule 1"}}]

        send_daily_digest("user@example.com", notifications)

        self.assertTrue(mock_send.called)
        call_args = mock_send.call_args[0][0]
        self.assertEqual(call_args["to"], "user@example.com")
        self.assertIn("from", call_args)
        self.assertIn("subject", call_args)
        self.assertIn("html", call_args)
        self.assertIn("text", call_args)


class TestBuildDigestHtml(unittest.TestCase):
    """Tests for _build_digest_html() template generation."""

    def test_includes_all_newsletters(self):
        """All newsletters included in HTML."""
        prepared = [
            {
                "title": "Newsletter 1",
                "source_name": "Ward 1",
                "ward_text": " (Ward 1)",
                "date_formatted": "January 24, 2026",
                "summary": "Summary 1",
                "topics": ["zoning"],
                "newsletter_url": "http://example.com/nl1",
                "matched_rules": ["Rule 1"],
            },
            {
                "title": "Newsletter 2",
                "source_name": "Ward 2",
                "ward_text": " (Ward 2)",
                "date_formatted": "January 23, 2026",
                "summary": "Summary 2",
                "topics": ["transit"],
                "newsletter_url": "http://example.com/nl2",
                "matched_rules": ["Rule 2"],
            },
        ]

        html = _build_digest_html(prepared, "http://example.com/prefs")

        self.assertIn("Newsletter 1", html)
        self.assertIn("Newsletter 2", html)

    def test_includes_matched_rules(self):
        """Matched rule names shown in HTML."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": ["Zoning Updates", "Bike Lanes"],
            }
        ]

        html = _build_digest_html(prepared, "http://example.com/prefs")

        self.assertIn("Zoning Updates", html)
        self.assertIn("Bike Lanes", html)

    def test_includes_topics(self):
        """Topics displayed in HTML."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": ["zoning", "transit", "bike_lanes"],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": [],
            }
        ]

        html = _build_digest_html(prepared, "http://example.com/prefs")

        self.assertIn("zoning", html)
        self.assertIn("transit", html)
        self.assertIn("bike_lanes", html)

    def test_limits_topics_to_five(self):
        """Only first 5 topics shown."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": ["topic1", "topic2", "topic3", "topic4", "topic5", "topic6"],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": [],
            }
        ]

        html = _build_digest_html(prepared, "http://example.com/prefs")

        self.assertIn("topic5", html)
        self.assertNotIn("topic6", html)

    def test_includes_preferences_link(self):
        """Preferences link present in footer."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": [],
            }
        ]

        html = _build_digest_html(prepared, "http://example.com/preferences")

        self.assertIn("http://example.com/preferences", html)


class TestBuildDigestText(unittest.TestCase):
    """Tests for _build_digest_text() plain text template."""

    def test_plain_text_structure(self):
        """Plain text has header, numbered list, footer."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "Test summary",
                "topics": ["zoning"],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": ["Rule 1"],
            }
        ]

        text = _build_digest_text(prepared, "http://example.com/prefs")

        self.assertIn("DAILY NEWSLETTER DIGEST", text)
        self.assertIn("1.", text)
        self.assertIn("---", text)

    def test_includes_all_newsletters(self):
        """All newsletters included in numbered list."""
        prepared = [
            {
                "title": "Newsletter 1",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://example.com/nl1",
                "matched_rules": [],
            },
            {
                "title": "Newsletter 2",
                "source_name": "Ward 2",
                "ward_text": "",
                "date_formatted": "January 23, 2026",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://example.com/nl2",
                "matched_rules": [],
            },
        ]

        text = _build_digest_text(prepared, "http://example.com/prefs")

        self.assertIn("1. Newsletter 1", text)
        self.assertIn("2. Newsletter 2", text)

    def test_includes_matched_rules(self):
        """Rule names shown in plain text."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": ["Zoning Updates"],
            }
        ]

        text = _build_digest_text(prepared, "http://example.com/prefs")

        self.assertIn("Zoning Updates", text)

    def test_includes_topics(self):
        """Topics listed in plain text."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": ["zoning", "transit"],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": [],
            }
        ]

        text = _build_digest_text(prepared, "http://example.com/prefs")

        self.assertIn("zoning", text)
        self.assertIn("transit", text)

    def test_includes_preferences_link(self):
        """Preferences link present in footer."""
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ward 1",
                "ward_text": "",
                "date_formatted": "January 24, 2026",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://example.com/nl",
                "matched_rules": [],
            }
        ]

        text = _build_digest_text(prepared, "http://example.com/prefs")

        self.assertIn("http://example.com/prefs", text)


if __name__ == "__main__":
    unittest.main()
