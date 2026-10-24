"""Characterization tests for weekly report generation (cli.process_weekly_reports).

Supabase, the report generator and the error log are mocked. The tests pin
which topics get a report, what is stored, and how each outcome is counted.
"""

import io
import sys
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from typing import Any
from unittest.mock import MagicMock, Mock, patch
from zoneinfo import ZoneInfo

from cli import process_weekly_reports as weekly
from models.types import NewsletterID
from models.weekly_report import KeyDevelopment, WeeklyTopicReport
from tests.fixtures.fake_supabase import ExecutedQuery, FakeSupabase

WEEK = "2026-W40"
NEWSLETTER = NewsletterID("nl-1")


def make_report(topic: str, developments: bool = True) -> WeeklyTopicReport:
    return WeeklyTopicReport(
        id=f"generated-{topic}",
        created_at=datetime(2026, 10, 5, tzinfo=ZoneInfo("America/Chicago")),
        topic=topic,
        week_id=WEEK,
        report_summary=f"{topic} summary",
        newsletter_ids=[NEWSLETTER],
        key_developments=(
            [
                KeyDevelopment(
                    description="Council vote", newsletter_ids=[NEWSLETTER], wards=["1"]
                )
            ]
            if developments
            else []
        ),
    )


class WeeklyReportsTestCase(unittest.TestCase):
    """Runs process_weekly_reports against a fake database and generator."""

    def setUp(self) -> None:
        self.reported_topics: set[str] = set()
        self.db = FakeSupabase(
            {
                ("notification_rules", "select"): [
                    {"topics": ["transit_funding", "bike_lanes"]},
                    {"topics": ["bike_lanes"]},
                    {"topics": None},
                ],
                ("weekly_topic_reports", "select"): self.answer_report_exists,
                ("weekly_topic_reports", "upsert"): [{"id": "report-1"}],
            }
        )
        self.generate = Mock(side_effect=lambda topic, *_: make_report(topic))
        self.log_error = Mock(return_value="errors/weekly.json")
        for target, value in {
            "get_supabase_client": Mock(return_value=self.db),
            "generate_weekly_topic_report": self.generate,
            "log_notification_error": self.log_error,
            "ENABLE_LLM": True,
        }.items():
            patcher = patch.object(weekly, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.output = io.StringIO()

    def answer_report_exists(self, query: ExecutedQuery) -> list[dict[str, Any]]:
        topic = query.equal_filters["topic"]
        return [{"id": "old"}] if topic in self.reported_topics else []

    def run_reports(self, **options: Any) -> dict[str, int]:
        with redirect_stdout(self.output):
            return weekly.process_weekly_reports(
                **{"week_id": WEEK, "model": "test-model", **options}
            )

    def stored_topics(self) -> list[str]:
        return [query.payload["topic"] for query in self.db.writes()]


class TestProcessWeeklyReports(WeeklyReportsTestCase):
    def test_generates_and_stores_one_report_per_active_topic(self) -> None:
        stats = self.run_reports()

        self.assertEqual(stats, {"generated": 2, "skipped": 0, "failed": 0})
        self.assertEqual(
            [args[0] for args, _ in self.generate.call_args_list],
            ["bike_lanes", "transit_funding"],
        )
        self.generate.assert_any_call("bike_lanes", WEEK, "test-model")
        self.assertEqual(self.stored_topics(), ["bike_lanes", "transit_funding"])

    def test_stored_row_and_upsert_conflict_target(self) -> None:
        self.run_reports()

        upsert = self.db.writes()[0]
        self.assertEqual(upsert.table, "weekly_topic_reports")
        self.assertEqual(upsert.calls[0][2], {"on_conflict": "topic,week_id"})
        self.assertEqual(
            upsert.payload,
            {
                "topic": "bike_lanes",
                "week_id": WEEK,
                "report_summary": "bike_lanes summary",
                "newsletter_ids": ["nl-1"],
                "key_developments": [
                    {
                        "description": "Council vote",
                        "newsletter_ids": ["nl-1"],
                        "wards": ["1"],
                    }
                ],
            },
        )

    def test_report_without_developments_stores_null(self) -> None:
        self.generate.side_effect = lambda topic, *_: make_report(topic, False)

        self.run_reports()

        self.assertIsNone(self.db.writes()[0].payload["key_developments"])

    def test_existing_report_is_skipped_unless_forced(self) -> None:
        self.reported_topics.add("bike_lanes")

        stats = self.run_reports()

        self.assertEqual(stats, {"generated": 1, "skipped": 1, "failed": 0})
        self.assertEqual(self.stored_topics(), ["transit_funding"])
        self.assertIn(
            "Report already exists for bike_lanes / 2026-W40", self.output.getvalue()
        )

    def test_force_regenerates_existing_reports(self) -> None:
        self.reported_topics.add("bike_lanes")

        stats = self.run_reports(force=True)

        self.assertEqual(stats, {"generated": 2, "skipped": 0, "failed": 0})
        self.assertNotIn(
            "weekly_topic_reports",
            [query.table for query in self.db.executed if query.operation == "select"],
        )

    def test_topic_without_content_is_skipped(self) -> None:
        self.generate.side_effect = lambda topic, *_: (
            None if topic == "bike_lanes" else make_report(topic)
        )

        stats = self.run_reports()

        self.assertEqual(stats, {"generated": 1, "skipped": 1, "failed": 0})

    def test_dry_run_generates_without_storing(self) -> None:
        stats = self.run_reports(dry_run=True)

        self.assertEqual(stats, {"generated": 2, "skipped": 0, "failed": 0})
        self.assertEqual(self.db.writes(), [])
        self.assertIn("Mode: DRY RUN", self.output.getvalue())

    def test_store_failure_counts_as_failed(self) -> None:
        self.db.responses[("weekly_topic_reports", "upsert")] = RuntimeError("down")

        stats = self.run_reports()

        self.assertEqual(stats, {"generated": 0, "skipped": 0, "failed": 2})
        self.assertIn("  ✗ Failed to store report: down", self.output.getvalue())

    def test_empty_upsert_response_counts_as_failed(self) -> None:
        self.db.responses[("weekly_topic_reports", "upsert")] = []

        stats = self.run_reports()

        self.assertEqual(stats["failed"], 2)

    def test_generation_error_is_logged_and_the_run_continues(self) -> None:
        self.generate.side_effect = lambda topic, *_: (
            make_report(topic) if topic == "transit_funding" else 1 / 0
        )

        stats = self.run_reports()

        self.assertEqual(stats, {"generated": 1, "skipped": 0, "failed": 1})
        self.log_error.assert_called_once_with(
            error_type="weekly_report_generation",
            error_message="division by zero",
            context={"week_id": WEEK, "topic": "bike_lanes"},
        )
        self.assertIn("  ⚠ Error logged to: errors/weekly.json", self.output.getvalue())

    def test_disabled_llm_generates_nothing(self) -> None:
        with patch.object(weekly, "ENABLE_LLM", False):
            stats = self.run_reports()

        self.assertEqual(stats, {"generated": 0, "skipped": 0, "failed": 0})
        self.assertEqual(self.db.executed, [])
        self.generate.assert_not_called()

    def test_no_active_topics_generates_nothing(self) -> None:
        self.db.responses[("notification_rules", "select")] = []

        stats = self.run_reports()

        self.assertEqual(stats, {"generated": 0, "skipped": 0, "failed": 0})
        self.generate.assert_not_called()

    def test_failed_topic_query_generates_nothing(self) -> None:
        self.db.responses[("notification_rules", "select")] = RuntimeError("down")

        stats = self.run_reports()

        self.assertEqual(stats, {"generated": 0, "skipped": 0, "failed": 0})
        self.assertIn("⚠ Error querying active topics: down", self.output.getvalue())

    def test_failed_existence_check_treats_the_report_as_missing(self) -> None:
        self.db.responses[("weekly_topic_reports", "select")] = RuntimeError("down")

        stats = self.run_reports()

        self.assertEqual(stats["generated"], 2)

    def test_active_topics_come_from_active_weekly_rules(self) -> None:
        self.run_reports()

        rules_query = self.db.executed[0]
        self.assertEqual(rules_query.table, "notification_rules")
        self.assertEqual(
            rules_query.equal_filters,
            {"is_active": True, "delivery_frequency": "weekly"},
        )


class TestWeekSelection(WeeklyReportsTestCase):
    @patch.object(weekly, "get_previous_week_id", return_value="2026-W39")
    def test_defaults_to_the_previous_week(self, _previous: MagicMock) -> None:
        self.run_reports(week_id=None)

        self.assertEqual(self.generate.call_args.args[1], "2026-W39")

    @patch.object(weekly, "get_iso_week_id", return_value="2026-W41")
    def test_current_week_option(self, _current: MagicMock) -> None:
        self.run_reports(week_id=None, current_week=True)

        self.assertEqual(self.generate.call_args.args[1], "2026-W41")

    def test_iso_week_id_pads_the_week(self) -> None:
        chicago = ZoneInfo("America/Chicago")
        self.assertEqual(
            weekly.get_iso_week_id(datetime(2026, 1, 30, tzinfo=chicago)), "2026-W05"
        )
        self.assertEqual(
            weekly.get_iso_week_id(datetime(2027, 1, 1, tzinfo=chicago)), "2026-W53"
        )


class TestMain(unittest.TestCase):
    def run_main(self, stats: dict[str, int], *argv: str) -> MagicMock:
        with (
            patch.object(sys, "argv", ["process_weekly_reports", *argv]),
            patch.object(weekly, "process_weekly_reports", return_value=stats) as run,
        ):
            weekly.main()
        return run

    def test_passes_options_through(self) -> None:
        run = self.run_main(
            {"generated": 1, "skipped": 0, "failed": 0},
            "--week-id",
            WEEK,
            "--dry-run",
            "--force",
            "--model",
            "openai:gpt-5",
        )

        run.assert_called_once_with(
            week_id=WEEK,
            dry_run=True,
            force=True,
            current_week=False,
            model="openai:gpt-5",
        )

    def test_exits_nonzero_when_a_report_failed(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            self.run_main({"generated": 0, "skipped": 0, "failed": 1})
        self.assertEqual(raised.exception.code, 1)


if __name__ == "__main__":
    unittest.main()
