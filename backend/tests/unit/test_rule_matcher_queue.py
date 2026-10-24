"""Unit tests for queueing and fetching pending notifications in notifications/rule_matcher.py."""

import unittest
from unittest.mock import MagicMock, Mock, patch

from notifications.rule_matcher import (
    get_pending_notifications_by_user,
    queue_notifications,
)
from tests.fixtures.mock_helpers import create_mock_supabase
from tests.fixtures.quiet_logging import quiet_logger
from tests.fixtures.user_factory import (
    create_test_notification,
)


def setUpModule() -> None:
    quiet_logger("notifications.rule_matcher")


class TestQueueNotifications(unittest.TestCase):
    """Tests for queue_notifications() function"""

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.rule_matcher.datetime")
    def test_queue_single_notification(
        self,
        mock_datetime: MagicMock,
        mock_get_supabase: MagicMock,
    ) -> None:
        """Basic insertion of one notification"""
        # Mock datetime.now() to return a specific date
        mock_now = Mock()
        mock_now.date.return_value.isoformat.return_value = "2026-01-24"
        mock_datetime.now.return_value = mock_now

        mock_supabase = create_mock_supabase()
        mock_get_supabase.return_value = mock_supabase

        matched_rules = [
            {"user_id": "user1", "rule_id": "rule1", "rule_name": "Test Rule"}
        ]

        result = queue_notifications("newsletter_id", matched_rules)

        self.assertEqual(result, 1)  # 1 notification queued
        # Verify insert was called
        self.assertEqual(mock_supabase.insert.call_count, 1)

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.rule_matcher.datetime")
    def test_queue_multiple_notifications(
        self,
        mock_datetime: MagicMock,
        mock_get_supabase: MagicMock,
    ) -> None:
        """Batch insert of multiple notifications"""
        # Mock datetime.now() to return a specific date
        mock_now = Mock()
        mock_now.date.return_value.isoformat.return_value = "2026-01-24"
        mock_datetime.now.return_value = mock_now

        mock_supabase = create_mock_supabase()
        mock_get_supabase.return_value = mock_supabase

        matched_rules = [
            {"user_id": "user1", "rule_id": "rule1", "rule_name": "Rule 1"},
            {"user_id": "user2", "rule_id": "rule2", "rule_name": "Rule 2"},
            {"user_id": "user3", "rule_id": "rule3", "rule_name": "Rule 3"},
        ]

        result = queue_notifications("newsletter_id", matched_rules)

        self.assertEqual(result, 3)  # 3 notifications queued
        # Each inserted individually
        self.assertEqual(mock_supabase.insert.call_count, 3)

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.rule_matcher.datetime")
    def test_generates_batch_id(
        self,
        mock_datetime: MagicMock,
        mock_get_supabase: MagicMock,
    ) -> None:
        """Uses today's date (YYYY-MM-DD) as batch_id"""
        # Mock datetime.now() to return a specific date in Chicago timezone
        mock_now = Mock()
        mock_now.date.return_value.isoformat.return_value = "2026-01-24"
        mock_datetime.now.return_value = mock_now

        mock_supabase = create_mock_supabase()
        mock_get_supabase.return_value = mock_supabase

        matched_rules = [{"user_id": "user1", "rule_id": "rule1", "rule_name": "Test"}]

        queue_notifications("newsletter_id", matched_rules)

        # Check that insert was called with digest_batch_id="2026-01-24"
        call_args = mock_supabase.insert.call_args[0]
        notification = call_args[0]
        self.assertEqual(notification["digest_batch_id"], "2026-01-24")

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.rule_matcher.datetime")
    def test_duplicate_handling(
        self,
        mock_datetime: MagicMock,
        mock_get_supabase: MagicMock,
    ) -> None:
        """Unique constraint on (user_id, newsletter_id, rule_id) handled gracefully"""
        # Mock datetime.now() to return a specific date
        mock_now = Mock()
        mock_now.date.return_value.isoformat.return_value = "2026-01-24"
        mock_datetime.now.return_value = mock_now

        # First insert succeeds, second fails with duplicate error
        mock_supabase = Mock()
        mock_supabase.table.return_value = mock_supabase
        mock_supabase.insert.return_value = mock_supabase

        # First call succeeds, second raises duplicate error
        mock_supabase.execute.side_effect = [
            Mock(),  # Success
            Exception("duplicate key value violates unique constraint"),
        ]
        mock_get_supabase.return_value = mock_supabase

        matched_rules = [
            {"user_id": "user1", "rule_id": "rule1", "rule_name": "Rule 1"},
            {
                "user_id": "user1",
                "rule_id": "rule1",
                "rule_name": "Rule 1",
            },  # Duplicate
        ]

        result = queue_notifications("newsletter_id", matched_rules)

        # Only 1 queued (duplicate ignored)
        self.assertEqual(result, 1)

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.rule_matcher.log_notification_error")
    @patch("builtins.print")
    def test_either_duplicate_wording_is_not_logged_as_a_failure(
        self,
        mock_print: MagicMock,
        mock_log: MagicMock,
        mock_get_supabase: MagicMock,
    ) -> None:
        """An error naming only "duplicate" or only "unique" is still a duplicate"""
        for message in ("duplicate key value", "violates unique constraint"):
            with self.subTest(message=message):
                mock_supabase = create_mock_supabase()
                mock_supabase.execute.side_effect = Exception(message)
                mock_get_supabase.return_value = mock_supabase

                queue_notifications(
                    "newsletter_id",
                    [{"user_id": "user1", "rule_id": "rule1", "rule_name": "Rule 1"}],
                )

                mock_log.assert_not_called()

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.rule_matcher.log_notification_error")
    @patch("notifications.rule_matcher.datetime")
    def test_partial_failure_continues(
        self,
        mock_datetime: MagicMock,
        mock_log: MagicMock,
        mock_get_supabase: MagicMock,
    ) -> None:
        """Some insertions fail, others succeed"""
        # Mock datetime.now() to return a specific date
        mock_now = Mock()
        mock_now.date.return_value.isoformat.return_value = "2026-01-24"
        mock_datetime.now.return_value = mock_now

        mock_supabase = Mock()
        mock_supabase.table.return_value = mock_supabase
        mock_supabase.insert.return_value = mock_supabase

        # First succeeds, second fails, third succeeds
        mock_supabase.execute.side_effect = [
            Mock(),  # Success
            Exception("Database error"),  # Failure
            Mock(),  # Success
        ]
        mock_get_supabase.return_value = mock_supabase

        matched_rules = [
            {"user_id": "user1", "rule_id": "rule1", "rule_name": "Rule 1"},
            {"user_id": "user2", "rule_id": "rule2", "rule_name": "Rule 2"},
            {"user_id": "user3", "rule_id": "rule3", "rule_name": "Rule 3"},
        ]

        result = queue_notifications("newsletter_id", matched_rules)

        # 2 succeeded
        self.assertEqual(result, 2)
        # Error logged for non-duplicate failure
        self.assertEqual(mock_log.call_count, 1)

    def test_empty_rules_returns_zero(self) -> None:
        """No rules to queue returns 0"""
        result = queue_notifications("newsletter_id", [])

        self.assertEqual(result, 0)

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.rule_matcher.log_notification_error")
    def test_error_logged_on_failure(
        self, mock_log: MagicMock, mock_get_supabase: MagicMock
    ) -> None:
        """Failures logged to file"""
        mock_get_supabase.side_effect = Exception("Database connection failed")

        matched_rules = [{"user_id": "user1", "rule_id": "rule1", "rule_name": "Test"}]

        result = queue_notifications("newsletter_id", matched_rules)

        self.assertEqual(result, 0)
        # Verify error was logged
        mock_log.assert_called_once()


class TestGetPendingNotificationsByUser(unittest.TestCase):
    """Tests for get_pending_notifications_by_user() function"""

    @patch("notifications.rule_matcher.get_supabase_client")
    def test_groups_by_user(self, mock_get_supabase: MagicMock) -> None:
        """Notifications grouped correctly by user_id"""
        notification1 = create_test_notification(user_id="user1", newsletter_id="n1")
        notification2 = create_test_notification(user_id="user1", newsletter_id="n2")
        notification3 = create_test_notification(user_id="user2", newsletter_id="n3")

        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(
            data=[notification1, notification2, notification3]
        )
        mock_get_supabase.return_value = mock_supabase

        result = get_pending_notifications_by_user()

        self.assertEqual(len(result), 2)  # 2 users
        self.assertEqual(len(result["user1"]), 2)  # user1 has 2 notifications
        self.assertEqual(len(result["user2"]), 1)  # user2 has 1 notification

    @patch("notifications.rule_matcher.get_supabase_client")
    def test_filters_by_batch_id(self, mock_get_supabase: MagicMock) -> None:
        """Only specified date returned"""
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(data=[])
        mock_get_supabase.return_value = mock_supabase

        get_pending_notifications_by_user(digest_batch_id="2026-01-24")

        # Verify query was filtered by batch_id
        # eq() should be called with digest_batch_id
        self.assertEqual(mock_supabase.eq.call_count, 2)
        mock_supabase.eq.assert_any_call("status", "pending")
        mock_supabase.eq.assert_any_call("digest_batch_id", "2026-01-24")

    @patch("notifications.rule_matcher.get_supabase_client")
    def test_filters_pending_status(self, mock_get_supabase: MagicMock) -> None:
        """Only status='pending' notifications returned"""
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(data=[])
        mock_get_supabase.return_value = mock_supabase

        get_pending_notifications_by_user()

        # Verify query filtered by status='pending'
        mock_supabase.eq.assert_any_call("status", "pending")

    @patch("notifications.rule_matcher.get_supabase_client")
    def test_orders_by_created_at(self, mock_get_supabase: MagicMock) -> None:
        """Chronological order by created_at"""
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(data=[])
        mock_get_supabase.return_value = mock_supabase

        get_pending_notifications_by_user()

        # Verify order() was called with created_at, desc=False
        mock_supabase.order.assert_called_once_with("created_at", desc=False)

    @patch("notifications.rule_matcher.get_supabase_client")
    def test_joins_newsletter_and_rule_data(self, mock_get_supabase: MagicMock) -> None:
        """Nested data structure with joins"""
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(data=[])
        mock_get_supabase.return_value = mock_supabase

        get_pending_notifications_by_user()

        # Verify select() includes newsletter and rule joins
        select_call = mock_supabase.select.call_args[0][0]
        self.assertIn("newsletter:newsletters", select_call)
        self.assertIn("rule:notification_rules", select_call)

    @patch("notifications.rule_matcher.get_supabase_client")
    def test_empty_queue_returns_empty_dict(self, mock_get_supabase: MagicMock) -> None:
        """No pending notifications returns empty dict"""
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(data=[])
        mock_get_supabase.return_value = mock_supabase

        result = get_pending_notifications_by_user()

        self.assertEqual(result, {})

    @patch("notifications.rule_matcher.get_supabase_client")
    def test_batch_id_none_gets_all(self, mock_get_supabase: MagicMock) -> None:
        """No filter when batch_id=None"""
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(data=[])
        mock_get_supabase.return_value = mock_supabase

        get_pending_notifications_by_user(digest_batch_id=None)

        # eq() should only be called once (for status='pending')
        # NOT called for digest_batch_id when None
        eq_calls = mock_supabase.eq.call_args_list
        # Should only have one call for status
        self.assertEqual(len(eq_calls), 1)
        self.assertEqual(eq_calls[0][0], ("status", "pending"))


if __name__ == "__main__":
    unittest.main()
