"""
Unit tests for notifications/rule_matcher.py

Tests rule matching logic including AND/OR boolean logic and filtering.
Queueing and pending-notification grouping are in test_rule_matcher_queue.py.
"""

import unittest
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from notifications.rule_matcher import (
    _rule_matches_newsletter,
    match_newsletter_to_rules,
)
from tests.fixtures.mock_helpers import create_mock_supabase
from tests.fixtures.quiet_logging import quiet_logger
from tests.fixtures.user_factory import (
    create_test_rule,
    create_test_user,
)


def setUpModule() -> None:
    quiet_logger("notifications.rule_matcher")


class TestRuleMatchesNewsletter(unittest.TestCase):
    """Tests for _rule_matches_newsletter() internal matching logic"""

    def test_topic_match_single(self) -> None:
        """Rule with single topic matches newsletter"""
        rule = create_test_rule(topics=["bike_lanes"])
        newsletter_data = {
            "topics": ["bike_lanes", "zoning_or_development_meeting_or_approval"]
        }

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_topic_match_multiple(self) -> None:
        """Rule with multiple topics (OR logic)"""
        rule = create_test_rule(topics=["bike_lanes", "transit_funding"])
        newsletter_data = {"topics": ["bike_lanes"]}  # Only one matches

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)  # One match is sufficient (OR logic)

    def test_topic_no_match(self) -> None:
        """No topic overlap returns False"""
        rule = create_test_rule(topics=["transit_funding"])
        newsletter_data = {"topics": ["zoning_or_development_meeting_or_approval"]}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertFalse(result)

    def test_topic_filter_empty_matches_all(self) -> None:
        """Rule with empty topics matches all newsletters"""
        rule = create_test_rule(topics=[])
        newsletter_data = {"topics": ["anything"]}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_search_term_match(self) -> None:
        """Keyword found in newsletter text"""
        rule = create_test_rule(search_term="parking")
        newsletter_data = {
            "topics": [],
            "plain_text": "New parking reform legislation announced.",
        }

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_search_term_no_match(self) -> None:
        """Keyword not found returns False"""
        rule = create_test_rule(search_term="parking")
        newsletter_data = {
            "topics": [],
            "plain_text": "Newsletter about zoning changes.",
        }

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertFalse(result)

    def test_search_term_case_insensitive(self) -> None:
        """Search term matching is case-insensitive"""
        rule = create_test_rule(search_term="PARKING")
        newsletter_data = {
            "topics": [],
            "plain_text": "New parking reform legislation announced.",
        }

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_search_term_empty_matches_all(self) -> None:
        """No search term matches all"""
        rule = create_test_rule(search_term=None)
        newsletter_data = {"topics": [], "plain_text": "Any content"}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_ward_filter_match(self) -> None:
        """Newsletter from specified ward matches"""
        rule = create_test_rule(ward_numbers=[1, 2])
        newsletter_data = {"topics": [], "ward_number": 1}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_ward_filter_no_match(self) -> None:
        """Newsletter from wrong ward returns False"""
        rule = create_test_rule(ward_numbers=[1, 2])
        newsletter_data = {"topics": [], "ward_number": 5}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertFalse(result)

    def test_ward_filter_empty_matches_all(self) -> None:
        """No ward filter matches all wards"""
        rule = create_test_rule(ward_numbers=[])
        newsletter_data = {"topics": [], "ward_number": 99}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)

    def test_all_filters_and_logic(self) -> None:
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

    def test_topics_or_within_filter(self) -> None:
        """Multiple topics in rule = OR logic"""
        rule = create_test_rule(topics=["bike_lanes", "transit_funding", "city_budget"])
        newsletter_data = {"topics": ["city_budget"]}  # Only one matches

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)  # Any one topic is sufficient

    def test_missing_plain_text_handled(self) -> None:
        """Newsletter without plain_text doesn't crash"""
        rule = create_test_rule(search_term="parking")
        newsletter_data: dict[str, Any] = {"topics": []}  # No plain_text key

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertFalse(result)  # Search term can't match

    def test_none_ward_number_handled(self) -> None:
        """Newsletter with ward_number=None doesn't crash"""
        rule = create_test_rule(ward_numbers=[1])
        newsletter_data: dict[str, Any] = {"topics": [], "ward_number": None}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertFalse(result)  # None not in [1]

    def test_legacy_min_relevance_score_ignored(self) -> None:
        """Deprecated min_relevance_score on existing rules is ignored (it never filtered)"""
        rule = create_test_rule(topics=["bike_lanes"], min_relevance_score=10)
        newsletter_data = {"topics": ["bike_lanes"]}

        result = _rule_matches_newsletter(rule, newsletter_data)

        self.assertTrue(result)


class TestMatchNewsletterToRules(unittest.TestCase):
    """Tests for match_newsletter_to_rules() public matching function"""

    @patch("notifications.rule_matcher.get_supabase_client")
    def test_match_single_rule(self, mock_get_supabase: MagicMock) -> None:
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
    def test_match_multiple_rules(self, mock_get_supabase: MagicMock) -> None:
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
    def test_no_rules_match(self, mock_get_supabase: MagicMock) -> None:
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
    def test_filters_disabled_users(self, mock_get_supabase: MagicMock) -> None:
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
    def test_filters_inactive_rules(self, mock_get_supabase: MagicMock) -> None:
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
    def test_error_handling_returns_empty(
        self, mock_log: MagicMock, mock_get_supabase: MagicMock
    ) -> None:
        """Database error returns empty list"""
        mock_get_supabase.side_effect = Exception("Database connection failed")

        newsletter_data = {"topics": ["bike_lanes"]}

        result = match_newsletter_to_rules("newsletter_id", newsletter_data)

        self.assertEqual(len(result), 0)
        # Verify error was logged
        mock_log.assert_called_once()

    @patch("notifications.rule_matcher.get_supabase_client")
    @patch("notifications.rule_matcher.log_notification_error")
    def test_error_logged_on_failure(
        self, mock_log: MagicMock, mock_get_supabase: MagicMock
    ) -> None:
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
    def test_no_active_rules_returns_empty(self, mock_get_supabase: MagicMock) -> None:
        """Empty rules list returns empty matches"""
        mock_supabase = create_mock_supabase()
        mock_supabase.execute.return_value = Mock(data=[])  # No rules
        mock_get_supabase.return_value = mock_supabase

        newsletter_data = {"topics": ["bike_lanes"]}

        result = match_newsletter_to_rules("newsletter_id", newsletter_data)

        self.assertEqual(len(result), 0)
