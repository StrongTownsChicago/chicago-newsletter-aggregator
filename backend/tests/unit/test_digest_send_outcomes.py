"""What process_digests() writes to the queue and history for each send outcome."""

import io
import unittest
from contextlib import redirect_stdout
from typing import Any
from unittest.mock import MagicMock, patch

from cli.process_notification_queue import process_digests
from notifications.digest_config import DigestType
from tests.fixtures.mock_helpers import create_mock_supabase

BATCH_ID = "2026-10-22"
NOTIFICATIONS = [
    {"id": "q-1", "newsletter_id": "nl-1", "rule_id": "rule-1"},
    {"id": "q-2", "newsletter_id": "nl-1", "rule_id": "rule-1"},
]
HISTORY_BASE = {
    "user_id": "user-1",
    "newsletter_ids": ["nl-1"],
    "rule_ids": ["rule-1"],
    "digest_batch_id": BATCH_ID,
    "delivery_type": "daily_digest",
}


@patch("cli.process_notification_queue.time.sleep")
@patch("cli.process_notification_queue.log_notification_error", return_value="log.json")
@patch("cli.process_notification_queue.send_digest")
@patch("cli.process_notification_queue.get_supabase_client")
@patch(
    "cli.process_notification_queue.get_pending_notifications_by_user",
    return_value={"user-1": NOTIFICATIONS},
)
class TestDigestSendOutcomes(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(redirect_stdout(io.StringIO()))
        self.supabase = create_mock_supabase()
        # The user_profiles lookup ends in .single(), so its data is one row.
        self.supabase.execute.return_value.data = {
            "email": "reader@example.com",
            "notification_preferences": {"enabled": True},
        }

    def run_digest(
        self, get_client: MagicMock, send: MagicMock, result: dict[str, Any]
    ) -> dict[str, int]:
        get_client.return_value = self.supabase
        send.return_value = result
        return process_digests(DigestType.DAILY, BATCH_ID)

    def test_sent_marks_queue_sent_and_records_success(
        self,
        _pending: MagicMock,
        get_client: MagicMock,
        send: MagicMock,
        log: MagicMock,
        _sleep: MagicMock,
    ) -> None:
        stats = self.run_digest(get_client, send, {"success": True, "email_id": "em-1"})

        self.assertEqual(stats, {"sent": 1, "failed": 0, "skipped": 0})
        self.supabase.update.assert_called_once_with(
            {"status": "sent", "sent_at": "now()"}
        )
        self.supabase.in_.assert_called_once_with("id", ["q-1", "q-2"])
        self.supabase.insert.assert_called_once_with(
            {**HISTORY_BASE, "success": True, "resend_email_id": "em-1"}
        )
        log.assert_not_called()

    def test_empty_digest_marks_queue_failed_and_records_skip(
        self,
        _pending: MagicMock,
        get_client: MagicMock,
        send: MagicMock,
        log: MagicMock,
        _sleep: MagicMock,
    ) -> None:
        stats = self.run_digest(
            get_client, send, {"success": False, "error": "Empty digest content"}
        )

        self.assertEqual(stats, {"sent": 0, "failed": 0, "skipped": 1})
        self.supabase.update.assert_called_once_with(
            {"status": "failed", "error_message": "Empty digest content"}
        )
        self.supabase.insert.assert_called_once_with(
            {**HISTORY_BASE, "success": False, "error_message": "Empty digest content"}
        )
        log.assert_not_called()

    def test_failure_logs_marks_queue_failed_and_records_error(
        self,
        _pending: MagicMock,
        get_client: MagicMock,
        send: MagicMock,
        log: MagicMock,
        _sleep: MagicMock,
    ) -> None:
        stats = self.run_digest(
            get_client, send, {"success": False, "error": "Resend down"}
        )

        self.assertEqual(stats, {"sent": 0, "failed": 1, "skipped": 0})
        self.supabase.update.assert_called_once_with(
            {"status": "failed", "error_message": "Resend down"}
        )
        self.supabase.insert.assert_called_once_with(
            {**HISTORY_BASE, "success": False, "error_message": "Resend down"}
        )
        self.assertEqual(log.call_args.kwargs["context"]["content_ids"], ["nl-1"])

    def test_skipped_users_are_not_rate_limited(
        self,
        _pending: MagicMock,
        get_client: MagicMock,
        send: MagicMock,
        log: MagicMock,
        sleep: MagicMock,
    ) -> None:
        self.supabase.execute.return_value.data = None
        stats = self.run_digest(get_client, send, {"success": True})

        self.assertEqual(stats, {"sent": 0, "failed": 0, "skipped": 1})
        send.assert_not_called()
        sleep.assert_not_called()

    def test_dry_run_leaves_a_disabled_users_queue_alone(
        self,
        _pending: MagicMock,
        get_client: MagicMock,
        send: MagicMock,
        _log: MagicMock,
        _sleep: MagicMock,
    ) -> None:
        self.supabase.execute.return_value.data = {
            "email": "reader@example.com",
            "notification_preferences": {"enabled": False},
        }
        get_client.return_value = self.supabase

        for dry_run, writes in ((True, 0), (False, 1)):
            with self.subTest(dry_run=dry_run):
                self.supabase.update.reset_mock()
                stats = process_digests(DigestType.DAILY, BATCH_ID, dry_run=dry_run)

                self.assertEqual(stats["skipped"], 1)
                self.assertEqual(self.supabase.update.call_count, writes)
        send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
