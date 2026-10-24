"""
Unit tests for process_llm_metadata utility.

Tests filtering logic, notification queuing, and dry-run behavior.
"""

import io
import os
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from typing import Any
from unittest.mock import MagicMock, Mock, call, patch

from cli import process_llm_metadata
from cli.process_llm_metadata import fetch_newsletters, reprocess_newsletter


class TestFetchNewsletters(unittest.TestCase):
    """Test newsletter fetching with various filters."""

    def setUp(self) -> None:
        """Set up test fixtures."""
        self.mock_supabase = Mock()
        self.mock_table = Mock()
        self.mock_supabase.table.return_value = self.mock_table

    def test_missing_metadata_filter_applied(self) -> None:
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
        self.mock_table.or_.assert_called_once_with("topics.is.null,summary.is.null")

    def test_missing_metadata_not_applied_when_flag_false(self) -> None:
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

    def test_combines_missing_metadata_with_source_filter(self) -> None:
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
        self.mock_table.range.return_value = self.mock_table
        self.mock_table.execute.return_value.data = []

        # Act
        fetch_newsletters(self.mock_supabase, args)

        # Assert
        self.mock_table.eq.assert_called_once_with("source_id", 5)
        self.mock_table.or_.assert_called_once()


class TestNotificationQueuing(unittest.TestCase):
    """Test notification queuing during LLM processing."""

    @patch("cli.process_llm_metadata.extract_newsletter_metadata")
    @patch("notifications.rule_matcher.match_newsletter_to_rules")
    @patch("notifications.rule_matcher.queue_notifications")
    def test_queues_notifications_when_flag_enabled(
        self, mock_queue: MagicMock, mock_match: MagicMock, mock_llm: MagicMock
    ) -> None:
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
        mock_table.update.assert_called_once_with(
            {"topics": ["bike_lanes"], "summary": "Test summary"}
        )
        mock_match.assert_called_once()
        mock_queue.assert_called_once()

    @patch("cli.process_llm_metadata.extract_newsletter_metadata")
    def test_skips_notifications_when_flag_disabled(self, mock_llm: MagicMock) -> None:
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
        }

        newsletter = {
            "id": "123",
            "subject": "Test",
            "source_id": 1,
            "received_date": "2026-01-01",
            "plain_text": "Test content",
        }

        # Act
        with (
            patch("builtins.print"),
            patch("notifications.rule_matcher.match_newsletter_to_rules") as mock_match,
        ):
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


class TestMain(unittest.TestCase):
    """main(): argument checks, the LLM switch, confirmation, counting."""

    def setUp(self) -> None:
        self.client = Mock(name="supabase")
        self.newsletters: list[dict[str, Any]] = [{"id": "a"}, {"id": "b"}]
        self.fetch = Mock(side_effect=lambda *_: self.newsletters)
        self.reprocess = Mock(return_value=True)
        self.get_client = Mock(return_value=self.client)
        self.fetch_text = Mock(
            side_effect=lambda _client, newsletter_id: f"{newsletter_id} text"
        )
        for target, value in {
            "get_supabase_client": self.get_client,
            "fetch_newsletters": self.fetch,
            "fetch_plain_text": self.fetch_text,
            "reprocess_newsletter": self.reprocess,
        }.items():
            patcher = patch.object(process_llm_metadata, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        env = patch.dict(os.environ, {"ENABLE_LLM": "true"})
        env.start()
        self.addCleanup(env.stop)

    def run_main(self, *argv: str) -> str:
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["process_llm_metadata", *argv]),
            redirect_stdout(output),
            redirect_stderr(io.StringIO()),
        ):
            process_llm_metadata.main()
        return output.getvalue()

    def test_requires_a_filter(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            self.run_main()
        self.assertEqual(raised.exception.code, 2)
        self.get_client.assert_not_called()

    def test_rejects_all_with_latest(self) -> None:
        with self.assertRaises(SystemExit):
            self.run_main("--all", "--latest", "5")
        self.get_client.assert_not_called()

    def test_disabled_llm_stops_before_connecting(self) -> None:
        with patch.dict(os.environ, {"ENABLE_LLM": "false"}):
            output = self.run_main("--latest", "5")

        self.assertIn("ENABLE_LLM is not set to 'true'", output)
        self.get_client.assert_not_called()

    def test_dry_run_works_with_llm_disabled(self) -> None:
        with patch.dict(os.environ, {"ENABLE_LLM": "false"}):
            output = self.run_main("--latest", "5", "--dry-run")

        self.assertEqual(self.reprocess.call_count, 2)
        self.assertIn("=== DRY RUN MODE ===", output)
        self.assertIn("Would process: 2 newsletter(s)", output)

    def test_passes_options_to_each_newsletter(self) -> None:
        self.run_main(
            "--latest", "5", "--model", "openai:gpt-5", "--queue-notifications"
        )

        (args,) = self.fetch.call_args.args[1:]
        self.assertIs(self.fetch.call_args.args[0], self.client)
        self.assertEqual(args.latest, 5)
        self.assertEqual(
            self.reprocess.call_args_list,
            [
                call(
                    self.client,
                    {"id": "a", "plain_text": "a text"},
                    "openai:gpt-5",
                    False,
                    True,
                ),
                call(
                    self.client,
                    {"id": "b", "plain_text": "b text"},
                    "openai:gpt-5",
                    False,
                    True,
                ),
            ],
        )

    def test_counts_successes_failures_and_errors(self) -> None:
        self.newsletters = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        self.reprocess.side_effect = [True, False, RuntimeError("boom")]

        output = self.run_main("--source-id", "3")

        self.assertIn("  ✗ Unexpected error: boom", output)
        self.assertIn("Processed: 1 successful, 2 failed", output)

    def test_interrupt_stops_the_run_and_still_summarizes(self) -> None:
        self.newsletters = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
        self.reprocess.side_effect = [True, KeyboardInterrupt, True]

        output = self.run_main("--all")

        self.assertEqual(self.reprocess.call_count, 2)
        self.assertIn("Interrupted by user", output)
        self.assertIn("Processed: 1 successful, 0 failed", output)

    def test_no_matches_processes_nothing(self) -> None:
        self.newsletters = []

        output = self.run_main("--missing-metadata")

        self.assertIn("No newsletters found matching criteria", output)
        self.reprocess.assert_not_called()

    @patch("builtins.input", return_value="n")
    def test_large_run_can_be_cancelled(self, prompt: MagicMock) -> None:
        self.newsletters = [{"id": str(index)} for index in range(101)]

        output = self.run_main("--all")

        prompt.assert_called_once()
        self.assertIn("Cancelled", output)
        self.reprocess.assert_not_called()
        self.fetch_text.assert_not_called()

    @patch("builtins.input", return_value="Y")
    def test_large_run_continues_when_confirmed(self, _prompt: MagicMock) -> None:
        self.newsletters = [{"id": str(index)} for index in range(101)]

        self.run_main("--all")

        self.assertEqual(self.reprocess.call_count, 101)

    @patch("builtins.input")
    def test_large_dry_run_does_not_ask(self, prompt: MagicMock) -> None:
        self.newsletters = [{"id": str(index)} for index in range(101)]

        self.run_main("--all", "--dry-run")

        prompt.assert_not_called()
        self.fetch_text.assert_not_called()

    def test_each_newsletter_gets_its_text_as_it_is_processed(self) -> None:
        self.run_main("--latest", "2")

        processed = [entry.args[1] for entry in self.reprocess.call_args_list]
        self.assertEqual(
            processed,
            [{"id": "a", "plain_text": "a text"}, {"id": "b", "plain_text": "b text"}],
        )

    def test_latest_must_be_positive(self) -> None:
        for latest in ("0", "-3"):
            with self.subTest(latest=latest), self.assertRaises(SystemExit):
                self.run_main("--latest", latest, "--source-id", "5")
        self.fetch.assert_not_called()


class TestFetchPlainText(unittest.TestCase):
    def test_reads_one_newsletters_text(self) -> None:
        client = MagicMock()
        query = client.table.return_value.select.return_value.eq.return_value
        query.execute.return_value.data = [{"plain_text": "body"}]

        self.assertEqual(process_llm_metadata.fetch_plain_text(client, "a"), "body")
        client.table.return_value.select.assert_called_once_with("plain_text")

    def test_a_deleted_newsletter_has_no_text(self) -> None:
        client = MagicMock()
        query = client.table.return_value.select.return_value.eq.return_value
        query.execute.return_value.data = []

        self.assertIsNone(process_llm_metadata.fetch_plain_text(client, "a"))


if __name__ == "__main__":
    unittest.main()
