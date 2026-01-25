"""
Unit tests for process_llm_metadata utility.

Tests filtering logic, notification queuing, and dry-run behavior.
"""

import unittest
from unittest.mock import Mock, patch
from utils.process_llm_metadata import fetch_newsletters, reprocess_newsletter


class TestFetchNewsletters(unittest.TestCase):
    """Test newsletter fetching with various filters."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_supabase = Mock()
        self.mock_table = Mock()
        self.mock_supabase.table.return_value = self.mock_table

    def test_missing_metadata_filter_applied(self):
        """Test --missing-metadata flag adds OR filter for null metadata."""
        # Arrange
        args = Mock(
            newsletter_id=None,
            source_id=None,
            missing_metadata=True,
            latest=10,
            skip=0,
            all=False,
        )

        # Mock query chain
        self.mock_table.select.return_value = self.mock_table
        self.mock_table.or_.return_value = self.mock_table
        self.mock_table.order.return_value = self.mock_table
        self.mock_table.range.return_value = self.mock_table
        self.mock_table.execute.return_value.data = []

        # Act
        fetch_newsletters(self.mock_supabase, args)

        # Assert
        self.mock_table.or_.assert_called_once_with(
            "topics.is.null,summary.is.null,relevance_score.is.null"
        )

    def test_missing_metadata_not_applied_when_flag_false(self):
        """Test no filter added when --missing-metadata not set."""
        # Arrange
        args = Mock(
            newsletter_id=None,
            source_id=None,
            missing_metadata=False,
            latest=10,
            skip=0,
            all=False,
        )

        # Mock query chain
        self.mock_table.select.return_value = self.mock_table
        self.mock_table.order.return_value = self.mock_table
        self.mock_table.range.return_value = self.mock_table
        self.mock_table.execute.return_value.data = []

        # Act
        fetch_newsletters(self.mock_supabase, args)

        # Assert
        self.mock_table.or_.assert_not_called()

    def test_combines_missing_metadata_with_source_filter(self):
        """Test --missing-metadata works with --source-id."""
        # Arrange
        args = Mock(
            newsletter_id=None,
            source_id=5,
            missing_metadata=True,
            latest=None,
            skip=0,
            all=True,
        )

        # Mock query chain
        self.mock_table.select.return_value = self.mock_table
        self.mock_table.eq.return_value = self.mock_table
        self.mock_table.or_.return_value = self.mock_table
        self.mock_table.order.return_value = self.mock_table
        self.mock_table.execute.return_value.data = []

        # Act
        fetch_newsletters(self.mock_supabase, args)

        # Assert
        self.mock_table.eq.assert_called_once_with("source_id", 5)
        self.mock_table.or_.assert_called_once()


class TestNotificationQueuing(unittest.TestCase):
    """Test notification queuing during LLM processing."""

    @patch("utils.process_llm_metadata.process_with_ollama")
    @patch("notifications.rule_matcher.match_newsletter_to_rules")
    @patch("notifications.rule_matcher.queue_notifications")
    def test_queues_notifications_when_flag_enabled(
        self, mock_queue, mock_match, mock_llm
    ):
        """Test notifications queued when --queue-notifications set."""
        # Arrange
        mock_supabase = Mock()
        mock_table = Mock()
        mock_supabase.table.return_value = mock_table

        # Mock successful update
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value.data = [{"id": "123"}]

        # Mock LLM processing
        mock_llm.return_value = {
            "topics": ["bike_lanes"],
            "summary": "Test summary",
            "relevance_score": 7,
        }

        # Mock rule matching
        mock_match.return_value = [
            {"user_id": "user1", "rule_id": "rule1", "rule_name": "Test Rule"}
        ]
        mock_queue.return_value = 1

        newsletter = {
            "id": "123",
            "subject": "Test",
            "source_id": 1,
            "received_date": "2026-01-01",
            "plain_text": "Test content",
            "sources": {"ward_number": "10"},
        }

        # Act
        with patch("builtins.print"):  # Suppress output
            result = reprocess_newsletter(
                mock_supabase,
                newsletter,
                "gpt-oss:20b",
                dry_run=False,
                queue_notifications_flag=True,
            )

        # Assert
        self.assertTrue(result)
        mock_match.assert_called_once()
        mock_queue.assert_called_once()

    @patch("utils.process_llm_metadata.process_with_ollama")
    def test_skips_notifications_when_flag_disabled(self, mock_llm):
        """Test notifications not queued when --queue-notifications not set."""
        # Arrange
        mock_supabase = Mock()
        mock_table = Mock()
        mock_supabase.table.return_value = mock_table

        # Mock successful update
        mock_table.update.return_value = mock_table
        mock_table.eq.return_value = mock_table
        mock_table.execute.return_value.data = [{"id": "123"}]

        # Mock LLM processing
        mock_llm.return_value = {
            "topics": ["bike_lanes"],
            "summary": "Test summary",
            "relevance_score": 7,
        }

        newsletter = {
            "id": "123",
            "subject": "Test",
            "source_id": 1,
            "received_date": "2026-01-01",
            "plain_text": "Test content",
        }

        # Act
        with patch("builtins.print"):
            with patch(
                "notifications.rule_matcher.match_newsletter_to_rules"
            ) as mock_match:
                result = reprocess_newsletter(
                    mock_supabase,
                    newsletter,
                    "gpt-oss:20b",
                    dry_run=False,
                    queue_notifications_flag=False,
                )

        # Assert
        self.assertTrue(result)
        # mock_match should not be called. Note: it's lazily imported so we check the patch
        mock_match.assert_not_called()


if __name__ == "__main__":
    unittest.main()
