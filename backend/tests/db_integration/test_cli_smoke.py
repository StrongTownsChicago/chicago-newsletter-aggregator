"""One-off and developer CLIs: their queries run against the real schema."""

import io
import tempfile
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

import cli.calculate_token_costs as token_costs
import cli.download_samples as download_samples
import cli.migrate_topics as migrate_topics
import cli.preview_weekly_digest as preview_weekly_digest
import cli.try_rule_matcher as try_rule_matcher
import cli.try_weekly_summary as try_weekly_summary
from tests.db_integration.local_supabase import TEST_PASSWORD, LocalSupabaseTestCase
from tests.fixtures.newsletter_factory import (
    insert_newsletter,
    insert_row,
    insert_source,
)
from tests.fixtures.user_factory import create_auth_user, insert_rule


class TestOneOffClis(LocalSupabaseTestCase):
    """A source, two newsletters (one with old topic ids) and a weekly report."""

    def setUp(self) -> None:
        self.reset()
        source_id = insert_source(self.db, name="Ward 17 Office", ward_number=17)["id"]
        self.newsletter_ids = [
            insert_newsletter(
                self.db,
                source_id,
                subject=f"Ward 17 Issue {number}",
                topics=topics,
                received_date=f"2026-10-0{number + 1}T12:00:00+00:00",
            )["id"]
            for number, topics in enumerate(
                (["bike_infrastructure", "budget_transparency"], ["bike_lanes"])
            )
        ]
        insert_row(
            self.db,
            "weekly_topic_reports",
            {
                "topic": "bike_lanes",
                "week_id": "2026-W40",
                "report_summary": "Bikes.",
                "newsletter_ids": self.newsletter_ids,
                "key_developments": [
                    {
                        "description": "Lanes on Elm.",
                        "newsletter_ids": [],
                        "wards": ["17"],
                    }
                ],
            },
        )
        self.enterContext(redirect_stdout(io.StringIO()))

    def test_migrate_topics_rewrites_old_topic_ids(self) -> None:
        migrate_topics.migrate_topics(dry_run=True)
        self.assertEqual(
            self.rows("newsletters", "topics", id=self.newsletter_ids[0])[0]["topics"],
            ["bike_infrastructure", "budget_transparency"],
        )

        migrate_topics.migrate_topics()

        (row,) = self.rows("newsletters", "topics", id=self.newsletter_ids[0])
        self.assertCountEqual(row["topics"], ["bike_lanes", "city_budget"])

    def test_download_samples_saves_each_sources_latest_newsletter(self) -> None:
        directory = Path(self.enterContext(tempfile.TemporaryDirectory()))

        with patch.object(download_samples, "OUTPUT_DIR", directory):
            download_samples.download_samples()

        self.assertEqual(
            sorted(path.name for path in directory.iterdir()),
            ["1_Ward_17_Office_2026-10-02.html", "1_Ward_17_Office_2026-10-02.txt"],
        )

    def test_token_costs_fetch_newsletters_with_their_source(self) -> None:
        (newsletter,) = token_costs.fetch_newsletters(latest=1)

        self.assertEqual(newsletter["id"], self.newsletter_ids[1])
        self.assertEqual(newsletter["source_name"], "Ward 17 Office")
        self.assertEqual(newsletter["ward_number"], "17")

    def test_weekly_previews_read_the_stored_report(self) -> None:
        report = preview_weekly_digest.fetch_weekly_report("bike_lanes", "2026-W40")
        assert report is not None
        (prepared,) = preview_weekly_digest.prepare_report_for_preview(report)
        self.assertEqual(
            sorted(n["subject"] for n in prepared["referenced_newsletters"]),
            ["Ward 17 Issue 0", "Ward 17 Issue 1"],
        )
        self.assertIsNone(
            preview_weekly_digest.fetch_weekly_report("tax_policy", "2026-W40")
        )

        found = try_weekly_summary.fetch_report_facts("bike_lanes", "2026-W40")
        assert found is not None
        facts, _topic_display = found
        self.assertEqual([fact.wards for fact in facts], [["17"]])

    def test_try_rule_matcher_queues_matches(self) -> None:
        user_id = create_auth_user(self.db, "tryout@example.test", TEST_PASSWORD)
        insert_rule(self.db, user_id, topics=["bike_lanes"], ward_numbers=["17"])

        try_rule_matcher.test_matching(should_queue=True)

        self.assertEqual(
            {row["newsletter_id"] for row in self.rows("notification_queue")},
            {self.newsletter_ids[1]},
        )
