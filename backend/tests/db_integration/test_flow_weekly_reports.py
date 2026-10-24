"""Weekly report generation (cli.process_weekly_reports) with the LLM faked."""

import io
from contextlib import redirect_stdout
from typing import Any
from unittest.mock import patch

import cli.process_weekly_reports as reports_cli
from tests.db_integration.fakes import FakeLlm
from tests.db_integration.local_supabase import TEST_PASSWORD, LocalSupabaseTestCase
from tests.fixtures.newsletter_factory import insert_newsletter, insert_source
from tests.fixtures.user_factory import create_auth_user, insert_rule

#: Monday 2 to Sunday 8 March 2026, in Chicago; DST starts on the Sunday.
WEEK_ID = "2026-W10"


class TestProcessWeeklyReports(LocalSupabaseTestCase):
    """Bike lane newsletters around the week's edges; one weekly subscriber."""

    def setUp(self) -> None:
        self.reset()
        source_id = insert_source(self.db, name="Ward 15 Office", ward_number=15)["id"]
        self.ids = {
            name: insert_newsletter(
                self.db,
                source_id,
                subject=name,
                topics=topics,
                received_date=received,
            )["id"]
            for name, topics, received in (
                # 8pm Sunday 1 March in Chicago: the week before, though Monday in UTC.
                ("sunday_before", ["bike_lanes"], "2026-03-02T02:00:00+00:00"),
                ("monday_morning", ["bike_lanes"], "2026-03-02T15:00:00+00:00"),
                ("sunday_evening", ["bike_lanes"], "2026-03-08T23:00:00+00:00"),
                # 10pm Sunday 8 March in Chicago, already Monday in UTC.
                ("sunday_late", ["bike_lanes"], "2026-03-09T03:00:00+00:00"),
                ("monday_after", ["bike_lanes"], "2026-03-09T15:00:00+00:00"),
                ("budget", ["city_budget"], "2026-03-04T15:00:00+00:00"),
            )
        }
        user_id = create_auth_user(self.db, "weekly@example.test", TEST_PASSWORD)
        weekly: dict[str, Any] = {"delivery_frequency": "weekly"}
        insert_rule(self.db, user_id, topics=["bike_lanes"], **weekly)
        insert_rule(self.db, user_id, topics=["tax_policy"], is_active=False, **weekly)
        insert_rule(self.db, user_id, topics=["city_budget"])  # daily
        self.enterContext(patch.object(reports_cli, "ENABLE_LLM", True))

    def generate(self, summary: str, **options: Any) -> dict[str, int]:
        llm = FakeLlm(weekly_summary=summary)
        with (
            patch("processing.weekly_report_generator.call_llm", llm),
            redirect_stdout(io.StringIO()),
        ):
            return reports_cli.process_weekly_reports(week_id=WEEK_ID, **options)

    def test_reports_on_weekly_topics_from_the_chicago_week(self) -> None:
        stats = self.generate("First pass.")

        self.assertEqual(stats, {"generated": 1, "skipped": 0, "failed": 0})
        (report,) = self.rows("weekly_topic_reports")
        self.assertEqual((report["topic"], report["week_id"]), ("bike_lanes", WEEK_ID))
        self.assertEqual(report["report_summary"], "First pass.")
        self.assertCountEqual(
            report["newsletter_ids"],
            [
                self.ids[name]
                for name in ("monday_morning", "sunday_evening", "sunday_late")
            ],
        )
        self.assertEqual(len(report["key_developments"]), 3)

    def test_rerunning_skips_or_updates_in_place(self) -> None:
        self.generate("First pass.")
        (first,) = self.rows("weekly_topic_reports")

        skipped = self.generate("Second pass.")
        forced = self.generate("Second pass.", force=True)

        self.assertEqual(skipped["skipped"], 1)
        self.assertEqual(forced["generated"], 1)
        (report,) = self.rows("weekly_topic_reports")
        self.assertEqual(report["id"], first["id"])
        self.assertEqual(report["report_summary"], "Second pass.")

    def test_dry_run_stores_nothing(self) -> None:
        stats = self.generate("Dry.", dry_run=True)

        self.assertEqual(stats["generated"], 1)
        self.assertEqual(self.rows("weekly_topic_reports"), [])
