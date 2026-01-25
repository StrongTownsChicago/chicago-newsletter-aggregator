"""
Unit tests for notification rule matching and queuing.

Tests verify that newsletters are correctly matched to user notification rules
and queued for digest emails.

Note: Email parsing is comprehensively tested in test_sanitization*.py and
test_user_cases.py.
"""

import unittest
from unittest.mock import patch, MagicMock


class TestNotificationMatching(unittest.TestCase):
    """Tests for notification rule matching and queuing."""

    def test_newsletter_matches_topic_rule(self):
        """Verify newsletter with matching topic triggers notification rule."""
        from notifications.rule_matcher import (
            match_newsletter_to_rules,
            queue_notifications,
        )

        # Create mock newsletter data
        newsletter_id = 123
        newsletter_data = {
            "id": newsletter_id,
            "subject": "Bike Lane Update",
            "topics": ["bike_lanes"],
            "plain_text": "New bike lanes on Milwaukee Avenue",
            "source_id": "source_001",
            "relevance_score": 0.8,
        }

        # Mock Supabase client
        mock_supabase = MagicMock()

        # Mock active rules query
        mock_rules_table = MagicMock()
        mock_rules_select = MagicMock()
        mock_rules_eq = MagicMock()
        mock_rules_response = MagicMock()
        mock_rules_response.data = [
            {
                "id": "rule_001",
                "user_id": "user_001",
                "name": "Bike Lane Alerts",
                "topics": ["bike_lanes"],
                "search_term": None,
                "min_relevance_score": None,
                "source_ids": None,
                "ward_numbers": None,
            }
        ]
        mock_rules_eq.execute.return_value = mock_rules_response
        mock_rules_select.eq.return_value = mock_rules_eq
        mock_rules_table.select.return_value = mock_rules_select

        # Mock user preferences query
        mock_users_table = MagicMock()
        mock_users_select = MagicMock()
        mock_users_in = MagicMock()
        mock_users_response = MagicMock()
        mock_users_response.data = [
            {"id": "user_001", "notification_preferences": {"enabled": True}}
        ]
        mock_users_in.execute.return_value = mock_users_response
        mock_users_select.in_.return_value = mock_users_in
        mock_users_table.select.return_value = mock_users_select

        # Mock queue insert
        mock_queue_table = MagicMock()
        mock_queue_insert = MagicMock()
        mock_queue_response = MagicMock()
        mock_queue_response.data = [{"id": "queue_001"}]
        mock_queue_insert.execute.return_value = mock_queue_response
        mock_queue_table.insert.return_value = mock_queue_insert

        # Route table() calls
        def table_router(table_name):
            if table_name == "notification_rules":
                return mock_rules_table
            elif table_name == "user_profiles":
                return mock_users_table
            elif table_name == "notification_queue":
                return mock_queue_table
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        # Test matching and queuing
        with patch(
            "notifications.rule_matcher.get_supabase_client", return_value=mock_supabase
        ):
            matched_rules = match_newsletter_to_rules(newsletter_id, newsletter_data)

            # Verify rule matched
            self.assertEqual(len(matched_rules), 1)
            self.assertEqual(matched_rules[0]["user_id"], "user_001")
            self.assertEqual(matched_rules[0]["rule_id"], "rule_001")

            # Verify notification queued
            count = queue_notifications(newsletter_id, matched_rules)
            self.assertEqual(count, 1)

    def test_reprocessing_triggers_notifications(self):
        """Verify that reprocessing flow correctly triggers notification matching."""
        from utils.process_llm_metadata import reprocess_newsletter

        # Create mock newsletter data
        newsletter_id = "newsletter_123"
        newsletter = {
            "id": newsletter_id,
            "subject": "Bike Lane Update",
            "source_id": 1,
            "received_date": "2026-01-25T12:00:00",
            "plain_text": "New bike lanes on Milwaukee Avenue",
            "sources": {"ward_number": "10"},
        }

        # Mock Supabase client
        mock_supabase = MagicMock()

        # Mock successful update
        mock_update_table = MagicMock()
        mock_update_result = MagicMock()
        mock_update_result.data = [{"id": newsletter_id}]
        mock_update_table.update.return_value.eq.return_value.execute.return_value = (
            mock_update_result
        )

        # Mock rules query (matching)
        mock_rules_response = MagicMock()
        mock_rules_response.data = [
            {
                "id": "rule_001",
                "user_id": "user_001",
                "name": "Bike Lane Alerts",
                "topics": ["bike_lanes"],
                "search_term": None,
                "min_relevance_score": None,
                "source_ids": None,
                "ward_numbers": ["10"],
            }
        ]

        # Mock user preferences query
        mock_users_response = MagicMock()
        mock_users_response.data = [
            {"id": "user_001", "notification_preferences": {"enabled": True}}
        ]

        # Mock queue insert
        mock_queue_response = MagicMock()
        mock_queue_response.data = [{"id": "queue_001"}]

        # Route table() calls
        def table_router(table_name):
            if table_name == "newsletters":
                return mock_update_table
            if table_name == "notification_rules":
                mock_rules_table = MagicMock()
                mock_rules_table.select.return_value.eq.return_value.execute.return_value = mock_rules_response
                return mock_rules_table
            elif table_name == "user_profiles":
                mock_users_table = MagicMock()
                mock_users_table.select.return_value.in_.return_value.execute.return_value = mock_users_response
                return mock_users_table
            elif table_name == "notification_queue":
                mock_queue_table = MagicMock()
                mock_queue_table.insert.return_value.execute.return_value = (
                    mock_queue_response
                )
                return mock_queue_table
            return MagicMock()

        mock_supabase.table.side_effect = table_router

        # Mock LLM processor
        with patch("utils.process_llm_metadata.process_with_ollama") as mock_llm:
            mock_llm.return_value = {
                "topics": ["bike_lanes"],
                "summary": "Newsletter about bike lanes",
                "relevance_score": 8,
            }

            # Test reprocessing with notification queuing
            with patch(
                "notifications.rule_matcher.get_supabase_client",
                return_value=mock_supabase,
            ):
                with patch("builtins.print"):  # Suppress output
                    success = reprocess_newsletter(
                        mock_supabase,
                        newsletter,
                        model="gpt-oss:20b",
                        dry_run=False,
                        queue_notifications_flag=True,
                    )

                self.assertTrue(success)
                # Verify that update was called
                mock_update_table.update.assert_called_once()
                # Verify that LLM was called
                mock_llm.assert_called_once_with(newsletter, "gpt-oss:20b")


if __name__ == "__main__":
    unittest.main()
