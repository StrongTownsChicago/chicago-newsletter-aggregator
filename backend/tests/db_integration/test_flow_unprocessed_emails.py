"""Mailbox audits (find_unprocessed_emails, replay_unprocessed_emails) on real rows."""

import io
import os
from contextlib import redirect_stderr, redirect_stdout
from typing import ClassVar
from unittest.mock import patch

from imap_tools import MailMessageFlags  # type: ignore[attr-defined]

import cli.find_unprocessed_emails as find_cli
import cli.replay_unprocessed_emails as replay_cli
from tests.db_integration.fakes import FakeMailbox, mail_message
from tests.db_integration.local_supabase import LocalSupabaseTestCase
from tests.fixtures.newsletter_factory import (
    insert_email_mapping,
    insert_newsletter,
    insert_source,
)

MAPPED_SENDER = "news@ward7.example.org"


class TestUnprocessedEmails(LocalSupabaseTestCase):
    """Two stored emails; the mailbox also holds a mapped and an unmapped one."""

    source_id: ClassVar[int]

    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.source_id = insert_source(cls.db, name="Ward 7 Office", ward_number=7)["id"]
        insert_email_mapping(cls.db, MAPPED_SENDER, cls.source_id)
        for uid in ("201", "202"):
            insert_newsletter(cls.db, cls.source_id, email_uid=uid)
        insert_newsletter(cls.db, cls.source_id, email_uid=None)  # a scraped row

    def setUp(self) -> None:
        self.mailbox = FakeMailbox(
            [
                mail_message("201", MAPPED_SENDER),
                mail_message("203", MAPPED_SENDER),
                mail_message("204", "someone@elsewhere.example.org"),
            ]
        )

    def run_cli(self, main: object, *args: str) -> str:
        output = io.StringIO()
        with (
            patch("sys.argv", ["cli", *args]),
            patch.dict(
                os.environ,
                {"GMAIL_ADDRESS": "inbox@example.test", "GMAIL_APP_PASSWORD": "pw"},
            ),
            patch.object(find_cli, "MailBox", self.mailbox.mailbox_class()),
            patch.object(replay_cli, "MailBox", self.mailbox.mailbox_class()),
            redirect_stdout(output),
            redirect_stderr(io.StringIO()),
        ):
            main()  # type: ignore[operator]
        return output.getvalue()

    def test_stored_uids_are_read_across_pages(self) -> None:
        for page_size in (1, 2, find_cli.SUPABASE_PAGE_SIZE):
            with self.subTest(page_size=page_size):
                self.assertEqual(
                    find_cli.fetch_stored_email_uids(self.db, page_size),
                    {"201", "202"},
                )

    def test_find_lists_only_emails_without_a_row(self) -> None:
        output = self.run_cli(find_cli.main)

        self.assertEqual(
            [line.split("\t")[1] for line in output.splitlines()], ["203", "204"]
        )

    def test_replay_marks_unread_only_unprocessed_emails_from_mapped_senders(
        self,
    ) -> None:
        self.run_cli(replay_cli.main)
        self.assertEqual(self.mailbox.flags, [])  # dry run

        self.run_cli(replay_cli.main, "--apply")
        self.assertEqual(self.mailbox.flags, [(["203"], MailMessageFlags.SEEN, False)])
