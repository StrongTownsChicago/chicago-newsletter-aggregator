"""Characterization tests for weekly notification queuing (cli.weekly_notification_queue).

Supabase is a FakeSupabase. The tests pin which rule topics are queued or
skipped, the queued row, and how users are counted.
"""

import io
import sys
import unittest
from contextlib import redirect_stdout
from typing import Any
from unittest.mock import MagicMock, Mock, patch

from cli import weekly_notification_queue as weekly_queue
from tests.fixtures.fake_supabase import FakeSupabase

WEEK = "2026-W40"


class WeeklyQueueTestCase(unittest.TestCase):
    """Runs queue_weekly_notifications against a fake database."""

    def setUp(self) -> None:
        self.db = FakeSupabase(
            {
                ("notification_rules", "select"): [
                    {"id": "r1", "user_id": "user-one", "topics": ["bike_lanes"]},
                    {
                        "id": "r2",
                        "user_id": "user-one",
                        "topics": ["transit_funding", "city_budget"],
                    },
                    {"id": "r3", "user_id": "user-two", "topics": ["city_budget"]},
                ],
                ("user_profiles", "select"): [
                    {"id": "user-one", "notification_preferences": {"enabled": True}},
                    {"id": "user-two", "notification_preferences": {}},
                ],
                ("weekly_topic_reports", "select"): [
                    {"id": "rep-bike", "topic": "bike_lanes", "week_id": WEEK},
                    {"id": "rep-transit", "topic": "transit_funding", "week_id": WEEK},
                ],
            }
        )
        patcher = patch.object(
            weekly_queue, "get_supabase_client", Mock(return_value=self.db)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.output = io.StringIO()

    def run_queue(self) -> dict[str, int]:
        with redirect_stdout(self.output):
            return weekly_queue.queue_weekly_notifications(WEEK)

    def queued(self) -> list[dict[str, Any]]:
        return [query.payload for query in self.db.writes("notification_queue")]


class TestQueueWeeklyNotifications(WeeklyQueueTestCase):
    def test_queues_each_rule_topic_with_a_report(self) -> None:
        stats = self.run_queue()

        self.assertEqual(stats, {"queued": 2, "skipped": 2, "users": 1})
        self.assertEqual(
            self.queued(),
            [
                {
                    "user_id": "user-one",
                    "report_id": "rep-bike",
                    "rule_id": "r1",
                    "status": "pending",
                    "digest_batch_id": WEEK,
                    "notification_type": "weekly",
                },
                {
                    "user_id": "user-one",
                    "report_id": "rep-transit",
                    "rule_id": "r2",
                    "status": "pending",
                    "digest_batch_id": WEEK,
                    "notification_type": "weekly",
                },
            ],
        )
        self.assertIn(
            "  ✓ Queued 2 notifications for user user-one...", self.output.getvalue()
        )

    def test_reports_are_fetched_for_the_week(self) -> None:
        self.run_queue()

        (reports_query,) = [
            query for query in self.db.executed if query.table == "weekly_topic_reports"
        ]
        self.assertEqual(reports_query.equal_filters, {"week_id": WEEK})

    def test_failed_insert_counts_as_skipped(self) -> None:
        self.db.responses[("notification_queue", "insert")] = RuntimeError("duplicate")

        stats = self.run_queue()

        self.assertEqual(stats, {"queued": 0, "skipped": 4, "users": 0})

    def test_rule_with_non_list_topics_is_ignored(self) -> None:
        self.db.responses[("notification_rules", "select")] = [
            {"id": "r1", "user_id": "user-one", "topics": None},
            {"id": "r2", "user_id": "user-one", "topics": ["bike_lanes"]},
        ]

        stats = self.run_queue()

        self.assertEqual(stats, {"queued": 1, "skipped": 0, "users": 1})

    def test_users_with_notifications_disabled_are_left_out(self) -> None:
        self.db.responses[("user_profiles", "select")] = [
            {"id": "user-one", "notification_preferences": {"enabled": False}},
            {"id": "user-two", "notification_preferences": {"enabled": True}},
        ]

        stats = self.run_queue()

        self.assertEqual(stats, {"queued": 0, "skipped": 1, "users": 0})
        self.assertEqual(self.queued(), [])

    def test_users_without_a_profile_are_left_out(self) -> None:
        self.db.responses[("user_profiles", "select")] = []

        stats = self.run_queue()

        self.assertEqual(stats, {"queued": 0, "skipped": 0, "users": 0})
        self.assertIn("No users with active weekly rules found", self.output.getvalue())

    def test_no_weekly_rules_queues_nothing(self) -> None:
        self.db.responses[("notification_rules", "select")] = []

        stats = self.run_queue()

        self.assertEqual(stats, {"queued": 0, "skipped": 0, "users": 0})
        self.assertEqual(
            [query.table for query in self.db.executed], ["notification_rules"]
        )

    def test_failed_rules_query_queues_nothing(self) -> None:
        self.db.responses[("notification_rules", "select")] = RuntimeError("down")

        stats = self.run_queue()

        self.assertEqual(stats, {"queued": 0, "skipped": 0, "users": 0})
        self.assertIn("⚠ Error querying weekly rules: down", self.output.getvalue())

    def test_failed_reports_query_queues_nothing(self) -> None:
        self.db.responses[("weekly_topic_reports", "select")] = RuntimeError("down")

        stats = self.run_queue()

        self.assertEqual(stats, {"queued": 0, "skipped": 0, "users": 0})
        self.assertEqual(self.queued(), [])
        self.assertIn("✗ Error fetching reports: down", self.output.getvalue())


class TestMain(unittest.TestCase):
    def run_main(self, queued: int, *argv: str) -> MagicMock:
        stats = {"queued": queued, "skipped": 0, "users": 0}
        with (
            patch.object(sys, "argv", ["weekly_notification_queue", *argv]),
            patch.object(
                weekly_queue, "queue_weekly_notifications", return_value=stats
            ) as run,
        ):
            weekly_queue.main()
        return run

    def test_uses_the_given_week(self) -> None:
        run = self.run_main(1, "--week-id", WEEK)

        run.assert_called_once_with(WEEK)

    def test_defaults_to_an_iso_week_id(self) -> None:
        run = self.run_main(1)

        (week_id,) = run.call_args.args
        self.assertRegex(week_id, r"^\d{4}-W\d{2}$")

    def test_exits_nonzero_when_nothing_was_queued(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            self.run_main(0, "--week-id", WEEK)
        self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
