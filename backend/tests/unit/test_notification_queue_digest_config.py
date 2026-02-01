"""
Unit tests for digest configuration system in process_notification_queue.py

Tests DigestConfig, DIGEST_CONFIGS, and unified process_digests function.
"""

import unittest
import sys
import io
from unittest.mock import patch, Mock
from datetime import datetime
from zoneinfo import ZoneInfo

from notifications.process_notification_queue import (
    DIGEST_CONFIGS,
    _calculate_daily_batch_id,
    _calculate_weekly_batch_id,
    process_digests,
)
from notifications.email_sender import DigestType


class TestDigestConfig(unittest.TestCase):
    """Tests for DigestConfig dataclass."""

    def test_has_all_required_fields(self):
        """DigestConfig contains all necessary configuration fields."""
        # Arrange
        config = DIGEST_CONFIGS[DigestType.DAILY]

        # Assert
        self.assertIsNotNone(config.digest_type)
        self.assertIsNotNone(config.notification_type)
        self.assertIsNotNone(config.delivery_type)
        self.assertIsNotNone(config.batch_id_calculator)
        self.assertIsNotNone(config.fetch_notifications)


class TestDigestConfigs(unittest.TestCase):
    """Tests for DIGEST_CONFIGS dictionary."""

    def test_contains_daily_and_weekly_configs(self):
        """Config exists for both digest types."""
        self.assertIn(DigestType.DAILY, DIGEST_CONFIGS)
        self.assertIn(DigestType.WEEKLY, DIGEST_CONFIGS)

    def test_daily_config_values(self):
        """Daily config has correct values."""
        config = DIGEST_CONFIGS[DigestType.DAILY]

        self.assertEqual(config.digest_type, DigestType.DAILY)
        self.assertEqual(config.notification_type, "daily")
        self.assertEqual(config.delivery_type, "daily_digest")

    def test_weekly_config_values(self):
        """Weekly config has correct values."""
        config = DIGEST_CONFIGS[DigestType.WEEKLY]

        self.assertEqual(config.digest_type, DigestType.WEEKLY)
        self.assertEqual(config.notification_type, "weekly")
        self.assertEqual(config.delivery_type, "weekly_digest")


class TestCalculateDailyBatchId(unittest.TestCase):
    """Tests for _calculate_daily_batch_id() function."""

    @patch("notifications.process_notification_queue.datetime")
    def test_returns_yesterday_in_chicago_time(self, mock_datetime):
        """Returns yesterday's date in YYYY-MM-DD format (Chicago time)."""
        # Arrange - Mock "today" as 2026-01-26 in Chicago
        chicago_tz = ZoneInfo("America/Chicago")
        mock_now = datetime(2026, 1, 26, 10, 0, 0, tzinfo=chicago_tz)
        mock_datetime.now.return_value = mock_now

        # Act
        result = _calculate_daily_batch_id()

        # Assert
        self.assertEqual(result, "2026-01-25")
        mock_datetime.now.assert_called_once_with(chicago_tz)


class TestCalculateWeeklyBatchId(unittest.TestCase):
    """Tests for _calculate_weekly_batch_id() function."""

    @patch("notifications.process_notification_queue.datetime")
    def test_returns_previous_week_in_iso_format(self, mock_datetime):
        """Returns previous week ID in YYYY-WXX format."""
        # Arrange - Mock "today" as 2026-01-26 (Monday of W05)
        # Previous week is W04
        chicago_tz = ZoneInfo("America/Chicago")
        mock_now = datetime(2026, 1, 26, 10, 0, 0, tzinfo=chicago_tz)
        mock_datetime.now.return_value = mock_now

        # Act
        result = _calculate_weekly_batch_id()

        # Assert
        self.assertEqual(result, "2026-W04")


class TestProcessDigests(unittest.TestCase):
    """Tests for unified process_digests() function."""

    def setUp(self):
        """Suppress print output during tests."""
        self.held_output = io.StringIO()
        sys.stdout = self.held_output

    def tearDown(self):
        """Restore stdout."""
        sys.stdout = sys.__stdout__

    @patch("notifications.process_notification_queue.send_digest")
    @patch("notifications.process_notification_queue.get_supabase_client")
    @patch("notifications.process_notification_queue.get_pending_notifications_by_user")
    def test_processes_daily_digest(self, mock_get_notifs, mock_supabase, mock_send):
        """Daily digest processed with correct configuration."""
        # Arrange
        mock_get_notifs.return_value = {
            "user-1": [{"id": "notif-1", "newsletter_id": "nl-1", "rule_id": "rule-1"}]
        }

        mock_supabase_instance = Mock()
        mock_supabase.return_value = mock_supabase_instance

        # Mock user profile query
        mock_profile_response = Mock()
        mock_profile_response.data = {
            "email": "test@example.com",
            "notification_preferences": {"enabled": True},
        }
        mock_supabase_instance.table.return_value.select.return_value.eq.return_value.single.return_value.execute.return_value = mock_profile_response

        # Mock update/insert operations
        mock_supabase_instance.table.return_value.update.return_value.in_.return_value.execute.return_value = Mock()
        mock_supabase_instance.table.return_value.insert.return_value.execute.return_value = Mock()

        mock_send.return_value = {"success": True, "email_id": "email-123"}

        # Act
        result = process_digests(DigestType.DAILY, "2026-01-25", dry_run=False)

        # Assert
        self.assertEqual(result["sent"], 1)
        mock_send.assert_called_once()

        # Verify send_digest called with DAILY type
        call_args = mock_send.call_args
        self.assertEqual(call_args[0][3], DigestType.DAILY)

    def test_weekly_config_exists(self):
        """Weekly digest configuration exists and has correct values."""
        # Just verify configuration exists and is correct
        # Integration tests handle actual processing
        config = DIGEST_CONFIGS[DigestType.WEEKLY]

        self.assertEqual(config.digest_type, DigestType.WEEKLY)
        self.assertEqual(config.notification_type, "weekly")
        self.assertEqual(config.delivery_type, "weekly_digest")

    @patch("notifications.process_notification_queue.get_pending_notifications_by_user")
    def test_uses_default_batch_id_when_not_provided(self, mock_get_notifs):
        """Calculates batch ID when not provided."""
        # Arrange
        mock_get_notifs.return_value = {}

        # Act
        with patch(
            "notifications.process_notification_queue.datetime"
        ) as mock_datetime:
            from datetime import datetime as real_datetime
            from zoneinfo import ZoneInfo

            chicago_tz = ZoneInfo("America/Chicago")
            mock_datetime.now.return_value = real_datetime(
                2026, 1, 26, 10, 0, 0, tzinfo=chicago_tz
            )
            process_digests(DigestType.DAILY, batch_id=None, dry_run=True)

        # Assert - should have calculated and used batch_id
        mock_get_notifs.assert_called()

    @patch("notifications.process_notification_queue.get_pending_notifications_by_user")
    def test_dry_run_mode_does_not_send_emails(self, mock_get_notifs):
        """Dry run mode counts but doesn't send."""
        # Arrange
        mock_get_notifs.return_value = {
            "user-1": [{"id": "notif-1", "newsletter_id": "nl-1", "rule_id": "rule-1"}]
        }

        # Act
        with patch("notifications.process_notification_queue.get_supabase_client"):
            with patch(
                "notifications.process_notification_queue.send_digest"
            ) as mock_send:
                result = process_digests(DigestType.DAILY, "2026-01-25", dry_run=True)

        # Assert
        self.assertEqual(result["sent"], 1)  # Counted
        mock_send.assert_not_called()  # But not sent

    def test_delivery_types_differ_by_config(self):
        """Each digest type has unique delivery_type value."""
        # Verify that daily and weekly have different delivery types
        daily_config = DIGEST_CONFIGS[DigestType.DAILY]
        weekly_config = DIGEST_CONFIGS[DigestType.WEEKLY]

        self.assertNotEqual(
            daily_config.delivery_type,
            weekly_config.delivery_type,
            "Daily and weekly should have different delivery types",
        )


if __name__ == "__main__":
    unittest.main()
