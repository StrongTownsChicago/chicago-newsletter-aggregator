"""Gmail ingestion (cli.process_emails) against real sources, mappings and rules."""

import io
from contextlib import redirect_stdout
from datetime import datetime
from typing import Any, ClassVar
from unittest.mock import Mock, patch

import cli.process_emails as process_emails
from ingest.email.email_parser import lookup_source_by_email
from shared.dates import CHICAGO_TIMEZONE
from tests.db_integration.fakes import FakeLlm, FakeMailbox, mail_message
from tests.db_integration.local_supabase import (
    TEST_PASSWORD,
    LocalSupabaseTestCase,
    response_rows,
)
from tests.fixtures.newsletter_factory import insert_email_mapping, insert_source
from tests.fixtures.quiet_logging import quiet_logger
from tests.fixtures.user_factory import create_auth_user, insert_rule

WARD_1_SENDER = "alderman@ward1.example.org"
WARD_40_DOMAIN = "40thward.example.org"
UNDERSCORE_SENDER = "first_last@ward2.example.org"

PRIVATE_HTML = (
    "<html><body><p>Snow plow schedule for the ward.</p>"
    '<p><a href="https://example.us1.list-manage.com/unsubscribe?u=1">'
    "Unsubscribe</a></p></body></html>"
)
PRIVATE_TEXT = (
    "Snow plow schedule for the ward.\n\nUnsubscribe\n"
    "Profile: https://example.us1.list-manage.com/profile?u=1\n"
)


def setUpModule() -> None:
    quiet_logger("ingest.email.email_parser")


class SourcesTestCase(LocalSupabaseTestCase):
    """Three sources, mapped by exact address, `%` wildcard and an underscore."""

    sources: ClassVar[dict[str, dict[str, Any]]]

    @classmethod
    def seed_sources(cls) -> None:
        cls.sources = {
            "ward_1": insert_source(cls.db, name="Ward 1 Office", ward_number=1),
            "ward_40": insert_source(cls.db, name="Ward 40 Office", ward_number=40),
            "ward_2": insert_source(cls.db, name="Ward 2 Office", ward_number=2),
        }
        insert_email_mapping(cls.db, WARD_1_SENDER, cls.sources["ward_1"]["id"])
        insert_email_mapping(
            cls.db, f"%@{WARD_40_DOMAIN}", cls.sources["ward_40"]["id"]
        )
        insert_email_mapping(cls.db, UNDERSCORE_SENDER, cls.sources["ward_2"]["id"])


class TestLookupSourceByEmail(SourcesTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        cls.seed_sources()

    def test_matches_real_mappings_with_their_embedded_source(self) -> None:
        for sender, source in (
            (WARD_1_SENDER, "ward_1"),
            (f"news@{WARD_40_DOMAIN}", "ward_40"),
            (f"News@{WARD_40_DOMAIN.upper()}", "ward_40"),
            (UNDERSCORE_SENDER, "ward_2"),
        ):
            with self.subTest(sender=sender):
                self.assertEqual(
                    lookup_source_by_email(sender, self.db), self.sources[source]
                )

    def test_unmatched_senders_find_no_source(self) -> None:
        for sender in (
            "firstxlast@ward2.example.org",  # `_` is literal, not SQL's wildcard
            f"news@{WARD_40_DOMAIN}.evil.example",
            "someone@elsewhere.example.org",
        ):
            with self.subTest(sender=sender):
                self.assertIsNone(lookup_source_by_email(sender, self.db))


class TestProcessEmails(SourcesTestCase):
    def setUp(self) -> None:
        self.reset()
        self.seed_sources()
        self.save_report = Mock()
        for target, value in {
            "GMAIL_ADDRESS": "inbox@example.test",
            "GMAIL_PASSWORD": "app-password",
            "ENABLE_LLM": False,
            "ENABLE_NOTIFICATIONS": False,
            "save_unmapped_report": self.save_report,
        }.items():
            patcher = patch.object(process_emails, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def ingest(self, *messages: Mock) -> FakeMailbox:
        mailbox = FakeMailbox(messages)
        with (
            patch.object(process_emails, "MailBox", mailbox.mailbox_class()),
            redirect_stdout(io.StringIO()),
        ):
            process_emails.process_new_newsletters()
        return mailbox

    def enable(self, setting: str) -> None:
        patcher = patch.object(process_emails, setting, True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_stores_a_sanitized_searchable_newsletter(self) -> None:
        self.ingest(
            mail_message("101", WARD_1_SENDER, html=PRIVATE_HTML, text=PRIVATE_TEXT)
        )

        (row,) = self.rows("newsletters")
        self.assertEqual(row["email_uid"], "101")
        self.assertEqual(row["source_id"], self.sources["ward_1"]["id"])
        self.assertEqual(row["received_date"], "2026-10-01T14:00:00+00:00")
        self.assertNotIn("list-manage", row["raw_html"])
        self.assertNotIn("Unsubscribe", row["plain_text"])
        self.assertNotIn("list-manage", row["plain_text"])
        self.assertIn("Snow plow schedule", row["plain_text"])
        found = response_rows(
            self.db.table("newsletters")
            .select("id")
            .text_search("search_vector", "plows", options={"config": "english"})
            .execute()
        )
        self.assertEqual(found, [{"id": row["id"]}])

    def test_the_same_message_is_stored_once(self) -> None:
        message = mail_message("102", f"news@{WARD_40_DOMAIN}")
        self.ingest(message)

        second_run = self.ingest(message)

        self.assertEqual(len(self.rows("newsletters")), 1)
        self.assertEqual(second_run.flags, [])  # the duplicate stays unread

    def test_an_unmapped_sender_stores_nothing_and_is_reported(self) -> None:
        mailbox = self.ingest(mail_message("103", "someone@elsewhere.example.org"))

        self.assertEqual(self.rows("newsletters"), [])
        self.assertEqual(len(mailbox.flags), 1)
        ((unmapped,),), _ = self.save_report.call_args
        self.assertEqual(unmapped["from"], "someone@elsewhere.example.org")

    def test_llm_topics_and_summary_are_stored(self) -> None:
        self.enable("ENABLE_LLM")
        llm = FakeLlm(topics=["bike_lanes", "not_a_topic"], summary="Plows are out.")

        with patch("processing.llm_processor.call_llm", llm):
            self.ingest(mail_message("104", WARD_1_SENDER))

        (row,) = self.rows("newsletters")
        self.assertEqual(row["topics"], ["bike_lanes"])
        self.assertEqual(row["summary"], "Plows are out.")

    def test_matching_rules_queue_pending_notifications(self) -> None:
        self.enable("ENABLE_NOTIFICATIONS")
        user_id = create_auth_user(self.db, "reader@example.test", TEST_PASSWORD)
        by_ward = insert_rule(self.db, user_id, name="Ward 40", ward_numbers=["40"])
        by_term = insert_rule(self.db, user_id, name="Plows", search_term="snow plow")
        insert_rule(self.db, user_id, name="Ward 1", ward_numbers=["1"])
        insert_rule(self.db, user_id, name="Weekly", delivery_frequency="weekly")

        self.ingest(
            mail_message("105", f"news@{WARD_40_DOMAIN}", text="Snow plow routes.")
        )

        (newsletter,) = self.rows("newsletters")
        queued = self.rows("notification_queue")
        self.assertCountEqual(
            [row["rule_id"] for row in queued], [by_ward["id"], by_term["id"]]
        )
        today = datetime.now(CHICAGO_TIMEZONE).date().isoformat()
        for row in queued:
            self.assertEqual(row["newsletter_id"], newsletter["id"])
            self.assertEqual(row["status"], "pending")
            self.assertEqual(row["notification_type"], "daily")
            self.assertEqual(row["digest_batch_id"], today)
