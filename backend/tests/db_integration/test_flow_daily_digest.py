"""Daily digest sending (cli.process_notification_queue) with Resend faked."""

import io
from contextlib import redirect_stdout
from typing import Any
from unittest.mock import patch

import cli.process_notification_queue as queue_cli
from tests.db_integration.fakes import FakeResend
from tests.db_integration.local_supabase import TEST_PASSWORD, LocalSupabaseTestCase
from tests.fixtures.newsletter_factory import (
    insert_newsletter,
    insert_row,
    insert_source,
)
from tests.fixtures.user_factory import (
    create_auth_user,
    insert_notification,
    insert_rule,
)

BATCH = "2026-10-01"


class TestDailyDigests(LocalSupabaseTestCase):
    """Readers whose digests send, fail, are turned off, or come out empty."""

    def setUp(self) -> None:
        self.reset()
        source_id = insert_source(self.db, name="Ward 14 Office", ward_number=14)["id"]
        self.newsletters = [
            insert_newsletter(
                self.db,
                source_id,
                subject=f"Ward 14 Issue {number}",
                received_date=f"2026-10-01T1{number}:00:00+00:00",
            )["id"]
            for number in range(3)
        ]
        report_id = insert_row(
            self.db,
            "weekly_topic_reports",
            {
                "topic": "city_budget",
                "week_id": "2026-W40",
                "report_summary": "Budget week.",
                "newsletter_ids": [],
            },
        )["id"]
        self.users: dict[str, str] = {}
        self.rules: dict[str, str] = {}
        for name in ("alice", "bob", "carol", "dave"):
            self.users[name] = create_auth_user(
                self.db, f"{name}@example.test", TEST_PASSWORD
            )
            self.rules[name] = insert_rule(self.db, self.users[name], name=name)["id"]
        self.db.table("user_profiles").update(
            {"notification_preferences": {"enabled": False}}
        ).eq("id", self.users["carol"]).execute()

        self.queue("alice", newsletter_id=self.newsletters[0])
        self.queue("alice", newsletter_id=self.newsletters[1])
        self.earlier = self.queue(
            "alice", newsletter_id=self.newsletters[2], digest_batch_id="2026-09-30"
        )
        self.queue("bob", newsletter_id=self.newsletters[0])
        self.queue("carol", newsletter_id=self.newsletters[0])
        # A daily row with no newsletter to show: its digest is empty.
        self.queue("dave", newsletter_id=None, report_id=report_id)

        self.resend = FakeResend(fail_for={"bob@example.test"})
        for patcher in (
            patch("resend.Emails.send", self.resend),
            patch("cli.process_notification_queue.time.sleep"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def queue(self, user: str, **fields: Any) -> dict[str, Any]:
        fields.setdefault("digest_batch_id", BATCH)
        return insert_notification(
            self.db, user_id=self.users[user], rule_id=self.rules[user], **fields
        )

    def send(self, dry_run: bool = False) -> dict[str, int]:
        with redirect_stdout(io.StringIO()):
            return queue_cli.process_daily_digests(batch_id=BATCH, dry_run=dry_run)

    def queue_by_user(self) -> dict[str, list[dict[str, Any]]]:
        names = {user_id: name for name, user_id in self.users.items()}
        grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in self.users}
        for row in self.rows("notification_queue"):
            if row["id"] != self.earlier["id"]:
                grouped[names[row["user_id"]]].append(row)
        return grouped

    def test_sends_records_and_marks_each_users_digest(self) -> None:
        stats = self.send()

        self.assertEqual(stats, {"sent": 1, "failed": 1, "skipped": 2})
        self.assertEqual(self.resend.recipients(), ["alice@example.test"])
        self.assertIn("Ward 14 Issue 0", self.resend.sent[0]["html"])
        queued = self.queue_by_user()
        for name, status, error in (
            ("alice", "sent", None),
            ("bob", "failed", "Resend rejected bob@example.test"),
            ("carol", "failed", "User notifications disabled"),
            ("dave", "failed", "Empty digest content"),
        ):
            with self.subTest(user=name):
                self.assertEqual({row["status"] for row in queued[name]}, {status})
                self.assertEqual(
                    {row["error_message"] for row in queued[name]}, {error}
                )
        self.assertTrue(all(row["sent_at"] for row in queued["alice"]))
        (earlier,) = self.rows("notification_queue", id=self.earlier["id"])
        self.assertEqual(earlier["status"], "pending")

    def test_history_records_each_attempt(self) -> None:
        self.send()

        history = {row["user_id"]: row for row in self.rows("notification_history")}
        self.assertEqual(
            set(history), {self.users["alice"], self.users["bob"], self.users["dave"]}
        )
        alice = history[self.users["alice"]]
        self.assertTrue(alice["success"])
        self.assertEqual(alice["resend_email_id"], "email-1")
        self.assertCountEqual(alice["newsletter_ids"], self.newsletters[:2])
        self.assertEqual(alice["rule_ids"], [self.rules["alice"]])
        self.assertEqual(alice["digest_batch_id"], BATCH)
        self.assertEqual(alice["delivery_type"], "daily_digest")
        self.assertFalse(history[self.users["bob"]]["success"])

    def test_dry_run_sends_and_writes_nothing(self) -> None:
        before = (self.rows("notification_queue"), self.rows("notification_history"))

        self.send(dry_run=True)

        self.assertEqual(self.resend.sent, [])
        self.assertEqual(
            (self.rows("notification_queue"), self.rows("notification_history")),
            before,
        )

    def test_a_user_without_a_profile_is_skipped_and_others_still_get_theirs(
        self,
    ) -> None:
        self.db.table("user_profiles").delete().eq("id", self.users["bob"]).execute()

        stats = self.send()

        self.assertEqual(self.resend.recipients(), ["alice@example.test"])
        self.assertEqual(stats["sent"], 1)
        self.assertEqual(
            {row["status"] for row in self.queue_by_user()["bob"]}, {"pending"}
        )
