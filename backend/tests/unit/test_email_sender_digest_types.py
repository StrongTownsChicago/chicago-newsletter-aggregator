"""
Unit tests for generic digest system in notifications/email_sender.py

Tests DigestType enum, unified send_digest function, and template rendering.
"""

import unittest
from unittest.mock import patch
from notifications.email_sender import (
    DigestType,
    send_digest,
    _render_daily_content_html,
    _render_weekly_content_html,
    _build_digest_html,
    _build_digest_text,
)


class TestDigestType(unittest.TestCase):
    """Tests for DigestType enum."""

    def test_has_daily_and_weekly_types(self):
        """Enum contains DAILY and WEEKLY."""
        self.assertEqual(DigestType.DAILY.value, "daily")
        self.assertEqual(DigestType.WEEKLY.value, "weekly")


class TestSendDigest(unittest.TestCase):
    """Tests for unified send_digest() function."""

    @patch("notifications.email_sender.resend.Emails.send")
    @patch("notifications.email_sender._prepare_newsletter_data")
    @patch("notifications.email_sender.generate_unsubscribe_token")
    def test_sends_daily_digest(self, mock_token, mock_prepare, mock_resend):
        """Daily digest sent with correct type."""
        # Arrange
        mock_token.return_value = "test-token"
        mock_prepare.return_value = [
            {
                "title": "Test",
                "source_name": "Test",
                "ward_text": "",
                "date_formatted": "Jan 1",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://test.com",
                "matched_rules": [],
            }
        ]
        mock_resend.return_value = {"id": "email-123"}

        notifications = [{"newsletter": {}, "rule": {}}]

        # Act
        result = send_digest(
            "user-1",
            "test@example.com",
            notifications,
            DigestType.DAILY,
            "http://prefs.com",
        )

        # Assert
        self.assertTrue(result["success"])
        self.assertEqual(result["email_id"], "email-123")
        mock_resend.assert_called_once()

        # Verify subject line
        call_args = mock_resend.call_args[0][0]
        self.assertIn("Daily", call_args["subject"])

    @patch("notifications.email_sender.resend.Emails.send")
    @patch("notifications.email_sender._prepare_weekly_report_data")
    @patch("notifications.email_sender.generate_unsubscribe_token")
    def test_sends_weekly_digest(self, mock_token, mock_prepare, mock_resend):
        """Weekly digest sent with correct type."""
        # Arrange
        mock_token.return_value = "test-token"
        mock_prepare.return_value = [
            {
                "topic": "bike_lanes",
                "topic_display": "Bike Lanes",
                "summary": "Summary",
                "newsletter_count": 5,
                "week_range": "Jan 1-7",
                "week_id": "2026-W01",
                "matched_rules": ["Test Rule"],
            }
        ]
        mock_resend.return_value = {"id": "email-456"}

        notifications = [{"report": {}, "rule": {}}]

        # Act
        result = send_digest(
            "user-2",
            "test@example.com",
            notifications,
            DigestType.WEEKLY,
            "http://prefs.com",
        )

        # Assert
        self.assertTrue(result["success"])
        self.assertEqual(result["email_id"], "email-456")

        # Verify subject line
        call_args = mock_resend.call_args[0][0]
        self.assertIn("Weekly", call_args["subject"])
        self.assertIn("Topic", call_args["subject"])

    @patch("notifications.email_sender.resend.Emails.send")
    @patch("notifications.email_sender._prepare_newsletter_data")
    @patch("notifications.email_sender.generate_unsubscribe_token")
    def test_handles_sending_failure(self, mock_token, mock_prepare, mock_resend):
        """Returns error on Resend failure."""
        # Arrange
        mock_token.return_value = "test-token"
        mock_prepare.return_value = [
            {
                "title": "Test",
                "source_name": "Test",
                "ward_text": "",
                "date_formatted": "Jan 1",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://test.com",
                "matched_rules": [],
            }
        ]
        mock_resend.side_effect = Exception("Resend API error")

        notifications = [{"newsletter": {}, "rule": {}}]

        # Act
        result = send_digest(
            "user-3", "test@example.com", notifications, DigestType.DAILY
        )

        # Assert
        self.assertFalse(result["success"])
        self.assertIn("error", result)
        self.assertIn("Resend API error", result["error"])


class TestRenderDailyContentHtml(unittest.TestCase):
    """Tests for _render_daily_content_html() function."""

    def test_renders_newsletter_cards(self):
        """Newsletter data rendered as HTML cards."""
        # Arrange
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Ald. Smith",
                "ward_text": " (Ward 10)",
                "date_formatted": "January 25, 2026",
                "summary": "Test summary",
                "topics": ["bike_lanes", "transit"],
                "newsletter_url": "http://example.com/nl/1",
                "matched_rules": ["Rule 1"],
            }
        ]

        # Act
        html = _render_daily_content_html(prepared)

        # Assert
        self.assertIn("Test Newsletter", html)
        self.assertIn("Ald. Smith", html)
        self.assertIn("Ward 10", html)
        self.assertIn("Test summary", html)
        self.assertIn("bike_lanes", html)
        self.assertIn("Rule 1", html)

    def test_limits_topics_to_five(self):
        """Only first 5 topics rendered."""
        # Arrange
        prepared = [
            {
                "title": "Test",
                "source_name": "Test",
                "ward_text": "",
                "date_formatted": "Jan 1",
                "summary": "",
                "topics": ["t1", "t2", "t3", "t4", "t5", "t6", "t7"],
                "newsletter_url": "http://test.com",
                "matched_rules": [],
            }
        ]

        # Act
        html = _render_daily_content_html(prepared)

        # Assert
        self.assertIn("t5", html)
        self.assertNotIn("t6", html)


class TestRenderWeeklyContentHtml(unittest.TestCase):
    """Tests for _render_weekly_content_html() function."""

    def test_renders_topic_reports(self):
        """Topic report data rendered as HTML."""
        # Arrange
        prepared = [
            {
                "topic": "bike_lanes",
                "topic_display": "Bike Lanes and Cycling Infrastructure",
                "summary": "This week saw progress on bike lanes in multiple wards.",
                "newsletter_count": 8,
                "week_range": "January 20-26, 2026",
                "week_id": "2026-W04",
                "matched_rules": ["My Bike Rule"],
            }
        ]

        # Act
        html = _render_weekly_content_html(prepared)

        # Assert
        self.assertIn("Bike Lanes and Cycling Infrastructure", html)
        self.assertIn("8 newsletters", html)
        self.assertIn("January 20-26, 2026", html)
        self.assertIn("progress on bike lanes", html)
        self.assertIn("My Bike Rule", html)

    def test_includes_search_link(self):
        """Search link for topic included."""
        # Arrange
        prepared = [
            {
                "topic": "transit_funding",
                "topic_display": "Transit",
                "summary": "Summary",
                "newsletter_count": 3,
                "week_range": "Jan 1-7",
                "week_id": "2026-W01",
                "matched_rules": [],
            }
        ]

        # Act
        html = _render_weekly_content_html(prepared)

        # Assert
        self.assertIn("/search?topic=transit_funding", html)


class TestBuildDigestHtml(unittest.TestCase):
    """Tests for unified _build_digest_html() function."""

    def test_uses_daily_template_for_daily_type(self):
        """Daily digest type uses daily template."""
        # Arrange
        prepared = [
            {
                "title": "Test",
                "source_name": "Test",
                "ward_text": "",
                "date_formatted": "Jan 1",
                "summary": "",
                "topics": [],
                "newsletter_url": "http://test.com",
                "matched_rules": [],
            }
        ]

        # Act
        html = _build_digest_html(
            prepared,
            DigestType.DAILY,
            "http://prefs.com",
            "http://unsub.com",
        )

        # Assert
        self.assertIn("Daily Chicago Aldermen Newsletter Digest", html)
        self.assertIn('class="newsletter"', html)

    def test_uses_weekly_template_for_weekly_type(self):
        """Weekly digest type uses weekly template."""
        # Arrange
        prepared = [
            {
                "topic": "bike_lanes",
                "topic_display": "Bike Lanes",
                "summary": "Summary",
                "newsletter_count": 5,
                "week_range": "Jan 1-7",
                "week_id": "2026-W01",
                "matched_rules": [],
            }
        ]

        # Act
        html = _build_digest_html(
            prepared,
            DigestType.WEEKLY,
            "http://prefs.com",
            "http://unsub.com",
        )

        # Assert
        self.assertIn("Weekly Topic Digest", html)
        self.assertIn('class="topic-report"', html)

    def test_includes_preferences_and_unsubscribe_links(self):
        """Footer includes both links."""
        # Arrange
        prepared = []

        # Act
        html = _build_digest_html(
            prepared,
            DigestType.DAILY,
            "http://my-prefs.com",
            "http://my-unsub.com",
        )

        # Assert
        self.assertIn("http://my-prefs.com", html)
        self.assertIn("http://my-unsub.com", html)


class TestBuildDigestText(unittest.TestCase):
    """Tests for unified _build_digest_text() function."""

    def test_uses_daily_format_for_daily_type(self):
        """Daily digest type uses daily text format."""
        # Arrange
        prepared = [
            {
                "title": "Test Newsletter",
                "source_name": "Test",
                "ward_text": "",
                "date_formatted": "Jan 1",
                "summary": "Summary",
                "topics": ["bike_lanes"],
                "newsletter_url": "http://test.com",
                "matched_rules": ["Rule 1"],
            }
        ]

        # Act
        text = _build_digest_text(
            prepared,
            DigestType.DAILY,
            "http://prefs.com",
            "http://unsub.com",
        )

        # Assert
        self.assertIn("DAILY NEWSLETTER DIGEST", text)
        self.assertIn("1. Test Newsletter", text)
        self.assertIn("Rule 1", text)

    def test_uses_weekly_format_for_weekly_type(self):
        """Weekly digest type uses weekly text format."""
        # Arrange
        prepared = [
            {
                "topic": "transit_funding",
                "topic_display": "Public Transit",
                "summary": "Transit summary",
                "newsletter_count": 7,
                "week_range": "Jan 1-7",
                "week_id": "2026-W01",
                "matched_rules": ["Transit Rule"],
            }
        ]

        # Act
        text = _build_digest_text(
            prepared,
            DigestType.WEEKLY,
            "http://prefs.com",
            "http://unsub.com",
        )

        # Assert
        self.assertIn("WEEKLY TOPIC DIGEST", text)
        self.assertIn("1. Public Transit", text)
        self.assertIn("7 newsletters", text)
        self.assertIn("Transit Rule", text)


if __name__ == "__main__":
    unittest.main()
