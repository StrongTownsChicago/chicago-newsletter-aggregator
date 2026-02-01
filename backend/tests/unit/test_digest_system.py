"""
Unit tests for generic digest system (email_sender.py + process_notification_queue.py)

Tests template selection, business rules, error handling.
"""

import unittest
from unittest.mock import patch
from datetime import datetime
from zoneinfo import ZoneInfo

from notifications.email_sender import (
    DigestType,
    send_digest,
    _build_digest_html,
    _build_digest_text,
)
from notifications.process_notification_queue import (
    _calculate_daily_batch_id,
    _calculate_weekly_batch_id,
    process_digests,
)


class TestDigestEmailTemplates(unittest.TestCase):
    """Tests for template-based digest generation."""

    def test_daily_uses_newsletter_template(self):
        """Daily digest uses newsletter card template."""
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

        html = _build_digest_html(
            prepared, DigestType.DAILY, "http://prefs.com", "http://unsub.com"
        )

        self.assertIn("Daily Chicago Aldermen Newsletter Digest", html)
        self.assertIn('class="newsletter"', html)

    def test_weekly_uses_topic_report_template(self):
        """Weekly digest uses topic report template."""
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

        html = _build_digest_html(
            prepared, DigestType.WEEKLY, "http://prefs.com", "http://unsub.com"
        )

        self.assertIn("Weekly Topic Digest", html)
        self.assertIn('class="topic-report"', html)

    def test_daily_text_format_differs_from_weekly(self):
        """Daily and weekly text formats are distinct."""
        daily_data = [
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

        weekly_data = [
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

        daily_text = _build_digest_text(
            daily_data, DigestType.DAILY, "http://p.com", "http://u.com"
        )
        weekly_text = _build_digest_text(
            weekly_data, DigestType.WEEKLY, "http://p.com", "http://u.com"
        )

        self.assertIn("DAILY NEWSLETTER DIGEST", daily_text)
        self.assertIn("WEEKLY TOPIC DIGEST", weekly_text)

    def test_topic_limit_business_rule(self):
        """Only first 5 topics shown (business rule enforcement)."""
        from notifications.email_sender import _render_daily_content_html

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

        html = _render_daily_content_html(prepared)

        # Business rule: max 5 topics displayed
        self.assertIn("t5", html)
        self.assertNotIn("t6", html)


class TestDigestSending(unittest.TestCase):
    """Tests for unified send_digest() function."""

    @patch("notifications.email_sender.resend.Emails.send")
    @patch("notifications.email_sender._prepare_newsletter_data")
    @patch("notifications.email_sender.generate_unsubscribe_token")
    def test_sends_correct_digest_type(self, mock_token, mock_prepare, mock_resend):
        """Correct digest type reflected in subject and routing."""
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

        # Act - Send DAILY
        result = send_digest(
            "user-1",
            "test@example.com",
            [{"newsletter": {}, "rule": {}}],
            DigestType.DAILY,
        )

        # Assert
        self.assertTrue(result["success"])
        call_args = mock_resend.call_args[0][0]
        self.assertIn("Daily", call_args["subject"])

    @patch("notifications.email_sender.resend.Emails.send")
    @patch("notifications.email_sender._prepare_newsletter_data")
    @patch("notifications.email_sender.generate_unsubscribe_token")
    def test_handles_sending_errors_gracefully(
        self, mock_token, mock_prepare, mock_resend
    ):
        """Email sending errors don't crash, return error dict."""
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

        # Act
        result = send_digest(
            "user-1",
            "test@example.com",
            [{"newsletter": {}, "rule": {}}],
            DigestType.DAILY,
        )

        # Assert
        self.assertFalse(result["success"])
        self.assertIn("Resend API error", result["error"])


class TestBatchIdCalculation(unittest.TestCase):
    """Tests for batch ID calculation functions."""

    @patch("notifications.process_notification_queue.datetime")
    def test_calculates_yesterday_chicago_time(self, mock_datetime):
        """Daily batch ID is yesterday in Chicago timezone."""
        chicago_tz = ZoneInfo("America/Chicago")
        mock_now = datetime(2026, 1, 26, 10, 0, 0, tzinfo=chicago_tz)
        mock_datetime.now.return_value = mock_now

        result = _calculate_daily_batch_id()

        self.assertEqual(result, "2026-01-25")

    @patch("notifications.process_notification_queue.datetime")
    def test_calculates_previous_iso_week(self, mock_datetime):
        """Weekly batch ID is previous week in ISO format."""
        chicago_tz = ZoneInfo("America/Chicago")
        mock_now = datetime(2026, 1, 26, 10, 0, 0, tzinfo=chicago_tz)  # Monday of W05
        mock_datetime.now.return_value = mock_now

        result = _calculate_weekly_batch_id()

        self.assertEqual(result, "2026-W04")  # Previous week


class TestDigestProcessing(unittest.TestCase):
    """Tests for process_digests() workflow."""

    def setUp(self):
        """Suppress print output."""
        import sys
        import io

        self.held_output = io.StringIO()
        sys.stdout = self.held_output

    def tearDown(self):
        """Restore stdout."""
        import sys

        sys.stdout = sys.__stdout__

    @patch("notifications.process_notification_queue.get_pending_notifications_by_user")
    def test_dry_run_counts_but_doesnt_send(self, mock_get_notifs):
        """Dry run mode processes notifications without sending emails."""
        mock_get_notifs.return_value = {
            "user-1": [{"id": "notif-1", "newsletter_id": "nl-1", "rule_id": "rule-1"}]
        }

        with patch("notifications.process_notification_queue.get_supabase_client"):
            with patch(
                "notifications.process_notification_queue.send_digest"
            ) as mock_send:
                result = process_digests(DigestType.DAILY, "2026-01-25", dry_run=True)

        # Assert - counted but not sent
        self.assertEqual(result["sent"], 1)
        mock_send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
