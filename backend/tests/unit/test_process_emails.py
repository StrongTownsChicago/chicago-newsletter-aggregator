"""Characterization tests for Gmail ingestion (cli.process_emails).

IMAP, Supabase, the parser, the LLM and rule matching are all mocked. The tests
pin what gets stored, which emails are marked read, and what is counted.
"""

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from imap_tools import MailMessageFlags  # type: ignore[attr-defined]

import cli.process_emails as process_emails
from config.privacy_patterns import PRIVACY_PATTERNS_DICT
from tests.fixtures.fake_supabase import ExecutedQuery, FakeSupabase
from tests.fixtures.mock_helpers import create_mock_mail_message


def parsed_newsletter(uid: str, source_id: int | None = 7) -> dict[str, Any]:
    return {
        "email_uid": uid,
        "subject": f"Subject {uid}",
        "plain_text": f"Body of {uid}",
        "source_id": source_id,
        "ward_number": 12 if source_id is not None else None,
        "topics": [],
    }


class ProcessEmailsTestCase(unittest.TestCase):
    """Runs process_new_newsletters against a fake mailbox and database."""

    def setUp(self) -> None:
        self.existing_uids: set[str] = set()
        self.parsed: dict[str, dict[str, Any]] = {}
        self.db = FakeSupabase(
            {
                ("newsletters", "select"): self.answer_existing,
                ("newsletters", "insert"): lambda query: [
                    {"id": f"nl-{query.payload['email_uid']}"}
                ],
            }
        )
        self.mailbox = MagicMock()
        mailbox_factory = MagicMock()
        mailbox_factory.return_value.login.return_value.__enter__.return_value = (
            self.mailbox
        )
        self.mailbox_factory = mailbox_factory

        self.parse = Mock(side_effect=lambda msg, *_: dict(self.parsed[msg.uid]))
        self.save_report = Mock()
        self.print_summary = Mock()
        for target, value in {
            "get_supabase_client": Mock(return_value=self.db),
            "MailBox": mailbox_factory,
            "GMAIL_ADDRESS": "inbox@example.com",
            "GMAIL_PASSWORD": "app-password",
            "ENABLE_LLM": False,
            "ENABLE_NOTIFICATIONS": False,
            "parse_newsletter": self.parse,
            "save_unmapped_report": self.save_report,
            "print_summary": self.print_summary,
        }.items():
            patcher = patch.object(process_emails, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.output = io.StringIO()

    def answer_existing(self, query: ExecutedQuery) -> list[dict[str, Any]]:
        uid = query.equal_filters["email_uid"]
        return [{"id": "existing"}] if uid in self.existing_uids else []

    def run_with(self, *messages: Mock) -> str:
        self.mailbox.fetch.return_value = list(messages)
        with redirect_stdout(self.output):
            process_emails.process_new_newsletters()
        return self.output.getvalue()

    def message(self, uid: str, source_id: int | None = 7) -> Mock:
        self.parsed[uid] = parsed_newsletter(uid, source_id)
        return create_mock_mail_message(
            uid=uid,
            subject=f"Subject {uid}",
            from_=f"{uid}@example.org",
            date=datetime(2026, 10, 1, 9, 30),
        )

    def inserted_rows(self) -> list[dict[str, Any]]:
        return [query.payload for query in self.db.writes("newsletters")]

    def flagged_uids(self) -> list[str]:
        return [args[0] for args, _ in self.mailbox.flag.call_args_list]


class TestConnection(ProcessEmailsTestCase):
    def test_missing_credentials_raise_before_connecting(self) -> None:
        with (
            patch.object(process_emails, "GMAIL_PASSWORD", None),
            redirect_stdout(self.output),
            self.assertRaisesRegex(ValueError, "GMAIL_ADDRESS and GMAIL_APP_PASSWORD"),
        ):
            process_emails.process_new_newsletters()
        self.mailbox_factory.assert_not_called()

    def test_logs_in_to_gmail_and_fetches_unread_only(self) -> None:
        self.run_with()

        self.mailbox_factory.assert_called_once_with("imap.gmail.com")
        self.mailbox_factory.return_value.login.assert_called_once_with(
            "inbox@example.com", "app-password"
        )
        (criteria,), _ = self.mailbox.fetch.call_args
        self.assertEqual(str(criteria), "(UNSEEN)")
        self.print_summary.assert_called_once_with(0, 0, 0)
        self.save_report.assert_not_called()


class TestStoring(ProcessEmailsTestCase):
    def test_mapped_email_is_stored_without_ward_and_marked_read(self) -> None:
        output = self.run_with(self.message("u1"))

        self.parse.assert_called_once()
        _, client, patterns = self.parse.call_args.args
        self.assertIs(client, self.db)
        self.assertIs(patterns, PRIVACY_PATTERNS_DICT)
        expected = parsed_newsletter("u1")
        del expected["ward_number"]
        self.assertEqual(self.inserted_rows(), [expected])
        self.mailbox.flag.assert_called_once_with("u1", MailMessageFlags.SEEN, True)
        self.print_summary.assert_called_once_with(1, 0, 0)
        self.assertIn("Processing: Subject u1", output)
        self.assertIn("✓ Stored in database", output)

    def test_marks_read_only_after_the_insert(self) -> None:
        writes_when_flagged: list[int] = []
        self.mailbox.flag.side_effect = lambda *_: writes_when_flagged.append(
            len(self.db.writes())
        )

        self.run_with(self.message("u1"))

        self.assertEqual(writes_when_flagged, [1])

    def test_duplicate_is_skipped_and_left_unread(self) -> None:
        self.existing_uids.add("dup")

        output = self.run_with(self.message("dup"), self.message("new"))

        self.assertEqual(self.parse.call_count, 1)
        self.assertEqual([row["email_uid"] for row in self.inserted_rows()], ["new"])
        self.assertEqual(self.flagged_uids(), ["new"])
        self.print_summary.assert_called_once_with(1, 1, 0)
        self.assertIn("⊘ Duplicate: Subject dup...", output)

    def test_unmapped_email_is_reported_and_marked_read_but_not_stored(self) -> None:
        output = self.run_with(self.message("lost", source_id=None))

        self.assertEqual(self.inserted_rows(), [])
        self.assertEqual(self.flagged_uids(), ["lost"])
        self.save_report.assert_called_once_with(
            [
                {
                    "from": "lost@example.org",
                    "subject": "Subject lost",
                    "date": "2026-10-01T09:30:00",
                }
            ]
        )
        self.print_summary.assert_called_once_with(0, 0, 1)
        self.assertIn("✗ Unmapped: Subject lost... (from: lost@example.org)", output)

    def test_unmapped_email_without_date_reports_unknown(self) -> None:
        message = self.message("lost", source_id=None)
        message.date = None

        self.run_with(message)

        (unmapped,) = self.save_report.call_args.args
        self.assertEqual(unmapped[0]["date"], "Unknown")

    def test_failing_email_is_left_unread_and_the_run_continues(self) -> None:
        broken = self.message("broken")

        def parse(msg: Mock, *_: Any) -> dict[str, Any]:
            if msg.uid == "broken":
                raise RuntimeError("bad MIME")
            return dict(self.parsed[msg.uid])

        self.parse.side_effect = parse

        output = self.run_with(broken, self.message("ok"))

        self.assertEqual(self.flagged_uids(), ["ok"])
        self.assertEqual([row["email_uid"] for row in self.inserted_rows()], ["ok"])
        self.print_summary.assert_called_once_with(1, 0, 0)
        self.assertIn("✗ Error processing broken: bad MIME", output)

    def test_failed_insert_is_not_counted_or_marked_read(self) -> None:
        self.db.responses[("newsletters", "insert")] = RuntimeError("db down")

        output = self.run_with(self.message("u1"))

        self.mailbox.flag.assert_not_called()
        self.print_summary.assert_called_once_with(0, 0, 0)
        self.assertIn("✗ Error processing u1: db down", output)


class TestLlmStep(ProcessEmailsTestCase):
    def setUp(self) -> None:
        super().setUp()
        patcher = patch.object(process_emails, "ENABLE_LLM", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    @patch.dict(os.environ, {"LLM_MODEL": "openai:gpt-5"})
    @patch("processing.llm_processor.extract_newsletter_metadata")
    def test_llm_metadata_is_merged_into_the_stored_row(
        self, extract: MagicMock
    ) -> None:
        extract.return_value = {"topics": ["bike_lanes"], "summary": "Short."}

        output = self.run_with(self.message("u1"))

        newsletter, model = extract.call_args.args
        self.assertEqual(newsletter["email_uid"], "u1")
        self.assertEqual(model, "openai:gpt-5")
        (row,) = self.inserted_rows()
        self.assertEqual(row["topics"], ["bike_lanes"])
        self.assertEqual(row["summary"], "Short.")
        self.assertIn("  LLM processing complete", output)

    @patch("processing.llm_processor.extract_newsletter_metadata")
    def test_llm_failure_still_stores_the_newsletter(self, extract: MagicMock) -> None:
        extract.side_effect = RuntimeError("model offline")

        output = self.run_with(self.message("u1"))

        (row,) = self.inserted_rows()
        self.assertNotIn("summary", row)
        self.print_summary.assert_called_once_with(1, 0, 0)
        self.assertIn("  Warning: LLM processing failed: model offline", output)


@patch("notifications.rule_matcher.queue_notifications")
@patch("notifications.rule_matcher.match_newsletter_to_rules")
class TestNotifications(ProcessEmailsTestCase):
    def setUp(self) -> None:
        super().setUp()
        patcher = patch.object(process_emails, "ENABLE_NOTIFICATIONS", True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_matches_with_ward_and_queues(
        self, match: MagicMock, queue: MagicMock
    ) -> None:
        match.return_value = [{"rule_id": "r1"}]
        queue.return_value = 1

        output = self.run_with(self.message("u1"))

        match.assert_called_once_with(
            "nl-u1",
            {
                "topics": [],
                "plain_text": "Body of u1",
                "source_id": 7,
                "ward_number": 12,
            },
        )
        queue.assert_called_once_with("nl-u1", [{"rule_id": "r1"}])
        self.assertIn("  ✓ Queued 1 notification(s)", output)

    def test_no_match_queues_nothing(self, match: MagicMock, queue: MagicMock) -> None:
        match.return_value = []

        self.run_with(self.message("u1"))

        queue.assert_not_called()

    def test_empty_insert_response_skips_matching(
        self, match: MagicMock, queue: MagicMock
    ) -> None:
        self.db.responses[("newsletters", "insert")] = []

        self.run_with(self.message("u1"))

        match.assert_not_called()
        queue.assert_not_called()
        self.print_summary.assert_called_once_with(1, 0, 0)

    def test_queuing_failure_still_marks_read_and_counts(
        self, match: MagicMock, queue: MagicMock
    ) -> None:
        match.side_effect = RuntimeError("rules table missing")

        output = self.run_with(self.message("u1"))

        queue.assert_not_called()
        self.assertEqual(self.flagged_uids(), ["u1"])
        self.print_summary.assert_called_once_with(1, 0, 0)
        self.assertIn("Notification queuing failed: rules table missing", output)


class TestSaveUnmappedReport(unittest.TestCase):
    def test_writes_one_entry_per_email(self) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        previous = Path.cwd()
        os.chdir(directory.name)
        self.addCleanup(os.chdir, previous)

        with redirect_stdout(io.StringIO()):
            process_emails.save_unmapped_report(
                [{"from": "a@example.org", "subject": "Hello", "date": "Unknown"}]
            )

        (report,) = Path(directory.name).glob("unmapped_emails_*.txt")
        text = report.read_text(encoding="utf-8")
        self.assertIn("1. From: a@example.org\n   Subject: Hello\n", text)
        self.assertIn("   Date: Unknown\n", text)

    def test_writes_nothing_for_an_empty_list(self) -> None:
        with patch.object(Path, "open") as open_file:
            process_emails.save_unmapped_report([])
        open_file.assert_not_called()


if __name__ == "__main__":
    unittest.main()
