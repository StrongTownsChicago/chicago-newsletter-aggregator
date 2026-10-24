"""Weekly queueing (cli.weekly_notification_queue) and sending, with Resend faked."""

import io
from contextlib import redirect_stdout
from typing import Any
from unittest.mock import patch

import cli.process_notification_queue as queue_cli
import cli.weekly_notification_queue as weekly_queue
from tests.db_integration.fakes import FakeResend
from tests.db_integration.local_supabase import TEST_PASSWORD, LocalSupabaseTestCase
from tests.fixtures.newsletter_factory import (
    insert_newsletter,
    insert_row,
    insert_source,
)
from tests.fixtures.user_factory import create_auth_user, insert_rule

WEEK_ID = "2026-W10"


class TestWeeklyDigest(LocalSupabaseTestCase):
    """Two reports; weekly, muted-weekly and daily subscribers."""

    def setUp(self) -> None:
        self.reset()
        source_id = insert_source(self.db, name="Ward 16 Office", ward_number=16)["id"]
        newsletter_id = insert_newsletter(
            self.db, source_id, subject="Ward 16: New bike lanes on Elm"
        )["id"]
        self.reports = {
            topic: insert_row(
                self.db,
                "weekly_topic_reports",
                {
                    "topic": topic,
                    "week_id": WEEK_ID,
                    "report_summary": f"{topic} summary for the week.",
                    "newsletter_ids": [newsletter_id],
                },
            )["id"]
            for topic in ("bike_lanes", "city_budget")
        }
        self.users = {
            name: create_auth_user(self.db, f"{name}@example.test", TEST_PASSWORD)
            for name in ("alice", "bob", "carol")
        }
        weekly: dict[str, Any] = {"delivery_frequency": "weekly"}
        self.alice_rule = insert_rule(
            self.db,
            self.users["alice"],
            topics=["bike_lanes", "transit_funding"],
            **weekly,
        )["id"]
        insert_rule(self.db, self.users["bob"], topics=["city_budget"], **weekly)
        self.db.table("user_profiles").update(
            {"notification_preferences": {"enabled": False}}
        ).eq("id", self.users["bob"]).execute()
        insert_rule(
            self.db, self.users["carol"], topics=["bike_lanes"], ward_numbers=["16"]
        )
        self.resend = FakeResend()
        for patcher in (
            patch("resend.Emails.send", self.resend),
            patch("cli.process_notification_queue.time.sleep"),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def queue(self) -> dict[str, int]:
        with redirect_stdout(io.StringIO()):
            return weekly_queue.queue_weekly_notifications(WEEK_ID)

    def test_queues_report_notifications_for_enabled_weekly_subscribers(self) -> None:
        stats = self.queue()

        self.assertEqual(stats, {"queued": 1, "skipped": 1, "users": 1})
        (row,) = self.rows("notification_queue")
        self.assertEqual(row["user_id"], self.users["alice"])
        self.assertEqual(row["rule_id"], self.alice_rule)
        self.assertEqual(row["report_id"], self.reports["bike_lanes"])
        self.assertIsNone(row["newsletter_id"])
        self.assertEqual(
            (row["notification_type"], row["digest_batch_id"], row["status"]),
            ("weekly", WEEK_ID, "pending"),
        )

    def test_queueing_again_adds_nothing(self) -> None:
        self.queue()

        stats = self.queue()

        self.assertEqual(stats["queued"], 0)
        self.assertEqual(len(self.rows("notification_queue")), 1)

    def test_sends_the_weekly_digest_and_records_it(self) -> None:
        self.queue()

        with redirect_stdout(io.StringIO()):
            stats = queue_cli.process_weekly_digests(batch_id=WEEK_ID)

        self.assertEqual(stats, {"sent": 1, "failed": 0, "skipped": 0})
        (email,) = self.resend.sent
        self.assertEqual(email["to"], "alice@example.test")
        self.assertIn("bike_lanes summary for the week.", email["html"])
        self.assertIn("Ward 16: New bike lanes on Elm", email["html"])
        (row,) = self.rows("notification_queue")
        self.assertEqual(row["status"], "sent")
        (history,) = self.rows("notification_history")
        self.assertEqual(history["delivery_type"], "weekly_digest")
        self.assertEqual(history["newsletter_ids"], [self.reports["bike_lanes"]])
        self.assertEqual(history["digest_batch_id"], WEEK_ID)
