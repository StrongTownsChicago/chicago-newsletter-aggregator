"""
Unit tests for notifications/rule_matcher.py

Tests rule matching logic including AND/OR boolean logic, filtering,
duplicate handling, and grouping.
"""

import unittest
from unittest.mock import Mock, patch

from notifications.rule_matcher import (
    _rule_matches_newsletter,
    match_newsletter_to_rules,
    queue_notifications,
    get_pending_notifications_by_user,
)
from tests.fixtures.user_factory import (
    create_test_user,
    create_test_rule,
    create_test_notification,
)
from tests.fixtures.mock_helpers import create_mock_supabase


class TestRuleMatchesNewsletter(unittest.TestCase):
    """Tests for _rule_matches_newsletter() internal matching logic"""

    def test_topic_match_single(self):
        """Rule with single topic matches newsletter"""
        rule = create_test_rule(topics=["bike_lanes"])
        newsletter_data = {
            "topics": ["bike_lanes", "zoning_or_development_meeting_or_approval"]
        }

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_topic_match_multiple(self):
        """Rule with multiple topics (OR logic)"""
        rule = create_test_rule(topics=["bike_lanes", "transit_funding"])
        newsletter_data = {"topics": ["bike_lanes"]}  # Only one matches

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)  # One match is sufficient (OR logic)

    def test_topic_no_match(self):
        """No topic overlap returns False"""
        rule = create_test_rule(topics=["transit_funding"])
        newsletter_data = {"topics": ["zoning_or_development_meeting_or_approval"]}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertFalse(result)

    def test_topic_filter_empty_matches_all(self):
        """Rule with empty topics matches all newsletters"""
        rule = create_test_rule(topics=[])
        newsletter_data = {"topics": ["anything"]}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_search_term_match(self):
        """Keyword found in newsletter text"""
        rule = create_test_rule(search_term="parking")
        newsletter_data = {
            "topics": [],
            "plain_text": "New parking reform legislation announced.",
        }

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_search_term_no_match(self):
        """Keyword not found returns False"""
        rule = create_test_rule(search_term="parking")
        newsletter_data = {
            "topics": [],
            "plain_text": "Newsletter about zoning changes.",
        }

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertFalse(result)

    def test_search_term_case_insensitive(self):
        """Search term matching is case-insensitive"""
        rule = create_test_rule(search_term="PARKING")
        newsletter_data = {
            "topics": [],
            "plain_text": "New parking reform legislation announced.",
        }

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_search_term_empty_matches_all(self):
        """No search term matches all"""
        rule = create_test_rule(search_term=None)
        newsletter_data = {"topics": [], "plain_text": "Any content"}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_ward_filter_match(self):
        """Newsletter from specified ward matches"""
        rule = create_test_rule(ward_numbers=[1, 2])
        newsletter_data = {"topics": [], "ward_number": 1}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_ward_filter_no_match(self):
        """Newsletter from wrong ward returns False"""
        rule = create_test_rule(ward_numbers=[1, 2])
        newsletter_data = {"topics": [], "ward_number": 5}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertFalse(result)

    def test_ward_filter_empty_matches_all(self):
        """No ward filter matches all wards"""
        rule = create_test_rule(ward_numbers=[])
        newsletter_data = {"topics": [], "ward_number": 99}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_all_filters_and_logic(self):
        """Topics AND search term AND ward (all must pass)"""
        rule = create_test_rule(
            topics=["bike_lanes"], search_term="cycling", ward_numbers=[1]
        )

        # All filters match
        newsletter_data = {
            "topics": ["bike_lanes"],
            "plain_text": "New cycling infrastructure approved.",
            "ward_number": 1,
        }

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

        # One filter fails (wrong ward)
        newsletter_data["ward_number"] = 2

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertFalse(result)

    def test_topics_or_within_filter(self):
        """Multiple topics in rule = OR logic"""
        rule = create_test_rule(topics=["bike_lanes", "transit_funding", "city_budget"])
        newsletter_data = {"topics": ["city_budget"]}  # Only one matches

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)  # Any one topic is sufficient

    def test_missing_plain_text_handled(self):
        """Newsletter without plain_text doesn't crash"""
        rule = create_test_rule(search_term="parking")
        newsletter_data = {"topics": []}  # No plain_text key

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertFalse(result)  # Search term can't match

    def test_none_ward_number_handled(self):
        """Newsletter with ward_number=None doesn't crash"""
        rule = create_test_rule(ward_numbers=[1])
        newsletter_data = {"topics": [], "ward_number": None}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertFalse(result)  # None not in [1]


class TestMatchNewsletterToRules(unittest.TestCase):
    """Tests for match_newsletter_to_rules() public matching function"""

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("builtins.print")
    def test_match_single_rule(self, mock_print, mock_get_supabase):
        """One rule matches newsletter"""
        user = create_test_user(user_id="user1", notifications_enabled=True)
        rule = create_test_rule(user_id="user1", topics=["bike_lanes"], is_active=True)

        mock_supabase = create_mock_supabase()
        # First call returns rules, second returns users
        mock_supabase.execute.side_effect = [
            Mock(data=[rule]),  # Rules query
            Mock(data=[user]),  # Users query
        ]
        mock_get_supabase.return_value = mock_supabase

        newsletter_data = {"topics": ["bike_lanes"], "plain_text": "Bike lane news"}

        result = match_newsletter_to_rules("newsletter_id", newsletter_data)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["user_id"], "user1")
        self.assertEqual(result[0]["rule_id"], rule["id"])

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("builtins.print")
    def test_match_multiple_rules(self, mock_print, mock_get_supabase):
        """Multiple rules match same newsletter"""
        user1 = create_test_user(user_id="user1", notifications_enabled=True)
        user2 = create_test_user(user_id="user2", notifications_enabled=True)

        rule1 = create_test_rule(
            rule_id="rule1", user_id="user1", topics=["bike_lanes"]
        )
        rule2 = create_test_rule(
            rule_id="rule2", user_id="user2", topics=["bike_lanes"]
        )

        mock_supabase = create_mock_supabase()
        mock_supabase.execute.side_effect = [
            Mock(data=[rule1, rule2]),  # Rules query
            Mock(data=[user1, user2]),  # Users query
        ]
        mock_get_supabase.return_value = mock_supabase

        newsletter_data = {"topics": ["bike_lanes"]}

        result = match_newsletter_to_rules("newsletter_id", newsletter_data)

        self.assertEqual(len(result), 2)
        self.assertIn("user1", [match["user_id"] for match in result])
        self.assertIn("user2", [match["user_id"] for match in result])

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("builtins.print")
    def test_no_rules_match(self, mock_print, mock_get_supabase):
        """No rules match newsletter"""
        user = create_test_user(user_id="user1", notifications_enabled=True)
        rule = create_test_rule(
            user_id="user1", topics=["transit_funding"]
        )  # Different topic

        mock_supabase = create_mock_supabase()
        mock_supabase.execute.side_effect = [
            Mock(data=[rule]),
            Mock(data=[user]),
        ]
        mock_get_supabase.return_value = mock_supabase

        newsletter_data = {"topics": ["bike_lanes"]}  # Different topic

        result = match_newsletter_to_rules("newsletter_id", newsletter_data)

        self.assertEqual(len(result), 0)

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("builtins.print")
    def test_filters_disabled_users(self, mock_print, mock_get_supabase):
        """Users with notifications_enabled=false excluded"""
        user = create_test_user(
            user_id="user1", notifications_enabled=False
        )  # Disabled!
        rule = create_test_rule(user_id="user1", topics=["bike_lanes"])

        mock_supabase = create_mock_supabase()
        mock_supabase.execute.side_effect = [
            Mock(data=[rule]),
            Mock(data=[user]),
        ]
        mock_get_supabase.return_value = mock_supabase

        newsletter_data = {"topics": ["bike_lanes"]}

        result = match_newsletter_to_rules("newsletter_id", newsletter_data)

        self.assertEqual(len(result), 0)  # User filtered out

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("builtins.print")
    def test_filters_inactive_rules(self, mock_print, mock_get_supabase):
        """Only is_active=true rules considered"""
        # Rule with is_active=False should not be returned by query
        # (the query filters .eq("is_active", True))
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(data=[])  # No active rules
        mock_get_supabase.return_value = mock_supabase

        newsletter_data = {"topics": ["bike_lanes"]}

        result = match_newsletter_to_rules("newsletter_id", newsletter_data)

        self.assertEqual(len(result), 0)

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.rule_matcher.log_notification_error")
    @patch("builtins.print")
    def test_error_handling_returns_empty(
        self, mock_print, mock_log, mock_get_supabase
    ):
        """Database error returns empty list"""
        mock_get_supabase.side_effect = Exception("Database connection failed")

        newsletter_data = {"topics": ["bike_lanes"]}

        result = match_newsletter_to_rules("newsletter_id", newsletter_data)

        self.assertEqual(len(result), 0)
        # Verify error was logged
        mock_log.assert_called_once()

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.rule_matcher.log_notification_error")
    @patch("builtins.print")
    def test_error_logged_on_failure(self, mock_print, mock_log, mock_get_supabase):
        """Errors logged to file"""
        mock_get_supabase.side_effect = Exception("Test error")

        newsletter_data = {"topics": ["bike_lanes"], "source_id": "source123"}

        match_newsletter_to_rules("newsletter_id", newsletter_data)

        # Verify error logger was called with correct context
        self.assertEqual(mock_log.call_count, 1)
        call_kwargs = mock_log.call_args[1]
        self.assertEqual(call_kwargs["error_type"], "matching")
        self.assertIn("newsletter_id", call_kwargs["context"])

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("builtins.print")
    def test_no_active_rules_returns_empty(self, mock_print, mock_get_supabase):
        """Empty rules list returns empty matches"""
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(data=[])  # No rules
        mock_get_supabase.return_value = mock_supabase

        newsletter_data = {"topics": ["bike_lanes"]}

        result = match_newsletter_to_rules("newsletter_id", newsletter_data)

        self.assertEqual(len(result), 0)


class TestQueueNotifications(unittest.TestCase):
    """Tests for queue_notifications() function"""

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.rule_matcher.datetime")
    @patch("builtins.print")
    def test_queue_single_notification(
        self, mock_print, mock_datetime, mock_get_supabase
    ):
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
    @patch("builtins.print")
    def test_queue_multiple_notifications(
        self, mock_print, mock_datetime, mock_get_supabase
    ):
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
    @patch("builtins.print")
    def test_generates_batch_id(self, mock_print, mock_datetime, mock_get_supabase):
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
    @patch("builtins.print")
    def test_duplicate_handling(self, mock_print, mock_datetime, mock_get_supabase):
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
    @patch("notifications.rule_matcher.datetime")
    @patch("builtins.print")
    def test_partial_failure_continues(
        self, mock_print, mock_datetime, mock_log, mock_get_supabase
    ):
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

    def test_empty_rules_returns_zero(self):
        """No rules to queue returns 0"""
        result = queue_notifications("newsletter_id", [])

        self.assertEqual(result, 0)

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.rule_matcher.log_notification_error")
    @patch("builtins.print")
    def test_error_logged_on_failure(self, mock_print, mock_log, mock_get_supabase):
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
    def test_groups_by_user(self, mock_get_supabase):
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
    def test_filters_by_batch_id(self, mock_get_supabase):
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
    def test_filters_pending_status(self, mock_get_supabase):
        """Only status='pending' notifications returned"""
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(data=[])
        mock_get_supabase.return_value = mock_supabase

        get_pending_notifications_by_user()

        # Verify query filtered by status='pending'
        mock_supabase.eq.assert_any_call("status", "pending")

    @patch("notifications.rule_matcher.get_supabase_client")
    def test_orders_by_created_at(self, mock_get_supabase):
        """Chronological order by created_at"""
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(data=[])
        mock_get_supabase.return_value = mock_supabase

        get_pending_notifications_by_user()

        # Verify order() was called with created_at, desc=False
        mock_supabase.order.assert_called_once_with("created_at", desc=False)

    @patch("notifications.rule_matcher.get_supabase_client")
    def test_joins_newsletter_and_rule_data(self, mock_get_supabase):
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
    def test_empty_queue_returns_empty_dict(self, mock_get_supabase):
        """No pending notifications returns empty dict"""
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(data=[])
        mock_get_supabase.return_value = mock_supabase

        result = get_pending_notifications_by_user()

        self.assertEqual(result, {})

    @patch("notifications.rule_matcher.get_supabase_client")
    def test_batch_id_none_gets_all(self, mock_get_supabase):
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
