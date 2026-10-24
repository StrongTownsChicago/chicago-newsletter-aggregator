"""Tests for the topic migration script (cli.migrate_topics).

Supabase is a FakeSupabase. The tests pin the remapping, the statistics the
script prints, and which newsletters it updates.
"""

import io
import sys
import unittest
from contextlib import redirect_stdout
from typing import Any
from unittest.mock import Mock, patch

from cli import migrate_topics
from tests.fixtures.fake_supabase import FakeSupabase

NEWSLETTERS: list[dict[str, Any]] = [
    {
        "id": "n1",
        "subject": "Budget hearing and bike lanes",
        "topics": ["budget_transparency", "fiscal_sustainability", "bike_lanes"],
    },
    {"id": "n2", "subject": "Unchanged", "topics": ["bike_lanes"]},
    {"id": "n3", "subject": "Retired topic", "topics": ["obsolete_topic"]},
    {"id": "n4", "subject": "No topics", "topics": None},
]


class TestRemapTopics(unittest.TestCase):
    def test_maps_dedupes_and_sorts(self) -> None:
        self.assertEqual(
            migrate_topics.remap_topics(
                ["fiscal_sustainability", "bike_infrastructure", "budget_transparency"]
            ),
            ["bike_lanes", "city_budget"],
        )

    def test_keeps_valid_unmapped_topics_and_drops_unknown_ones(self) -> None:
        self.assertEqual(
            migrate_topics.remap_topics(["transit_funding", "obsolete_topic"]),
            ["transit_funding"],
        )


class MigrationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.db = FakeSupabase({("newsletters", "select"): NEWSLETTERS})
        patcher = patch.object(
            migrate_topics, "get_supabase_client", Mock(return_value=self.db)
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def run_migration(self, dry_run: bool = False) -> str:
        output = io.StringIO()
        with redirect_stdout(output):
            migrate_topics.migrate_topics(dry_run=dry_run)
        return output.getvalue()

    def updates(self) -> list[tuple[str, Any]]:
        return [
            (query.equal_filters["id"], query.payload["topics"])
            for query in self.db.writes("newsletters")
        ]


class TestMigrateTopics(MigrationTestCase):
    def test_updates_only_changed_newsletters(self) -> None:
        output = self.run_migration()

        self.assertEqual(
            self.updates(), [("n1", ["bike_lanes", "city_budget"]), ("n3", [])]
        )
        self.assertIn("✓ Successfully updated 2 newsletters", output)
        self.assertNotIn("Failed to update", output)

    def test_fetches_newsletters_with_topics_newest_first(self) -> None:
        self.run_migration(dry_run=True)

        (query,) = self.db.executed
        self.assertIn(("not_", (), {}), query.calls)
        self.assertIn(("is_", ("topics", None), {}), query.calls)
        self.assertIn(("order", ("created_at",), {"desc": True}), query.calls)

    def test_prints_statistics(self) -> None:
        output = self.run_migration(dry_run=True)

        self.assertIn("Total newsletters:     4", output)
        self.assertIn("Unchanged:             2", output)
        self.assertIn("To be modified:        2", output)
        self.assertIn(
            "Topics to be REMOVED:\n  - obsolete_topic: 1 newsletters", output
        )
        self.assertIn("  - budget_transparency → city_budget: 1 newsletters", output)
        self.assertIn("  - fiscal_sustainability → city_budget: 1 newsletters", output)
        self.assertNotIn("bike_lanes → bike_lanes", output)

    def test_prints_sample_changes(self) -> None:
        output = self.run_migration(dry_run=True)

        self.assertIn(
            "\nNewsletter: Budget hearing and bike lanes...\n"
            "  Old: ['budget_transparency', 'fiscal_sustainability', 'bike_lanes']\n"
            "  New: ['bike_lanes', 'city_budget']\n",
            output,
        )

    def test_dry_run_writes_nothing(self) -> None:
        output = self.run_migration(dry_run=True)

        self.assertEqual(self.db.writes(), [])
        self.assertIn("DRY RUN COMPLETE", output)
        self.assertIn("Migration Complete", output)

    def test_mapping_to_an_invalid_topic_counts_as_removed(self) -> None:
        self.db.responses[("newsletters", "select")] = [
            {"id": "n1", "subject": "Old", "topics": ["legacy_topic"]}
        ]

        with patch.dict(migrate_topics.TOPIC_MAPPING, {"legacy_topic": "gone"}):
            output = self.run_migration(dry_run=True)

        self.assertIn("  - legacy_topic: 1 newsletters", output)
        self.assertNotIn("Topics to be MAPPED", output)

    def test_failed_update_is_reported_and_the_rest_continue(self) -> None:
        calls = iter([RuntimeError("timeout"), [{"id": "n3"}]])

        def answer(_: Any) -> Any:
            outcome = next(calls)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        self.db.responses[("newsletters", "update")] = answer

        output = self.run_migration()

        self.assertEqual(len(self.db.writes()), 2)
        self.assertIn("  ✗ Failed to update newsletter n1: timeout", output)
        self.assertIn("✓ Successfully updated 1 newsletters", output)
        self.assertIn("✗ Failed to update 1 newsletters", output)

    def test_progress_every_ten_updates_and_sample_capped_at_fifty(self) -> None:
        self.db.responses[("newsletters", "select")] = [
            {"id": f"n{index}", "subject": f"S{index}", "topics": ["obsolete"]}
            for index in range(55)
        ]

        output = self.run_migration()

        self.assertIn("  Updated 10/55 newsletters...", output)
        self.assertIn("  Updated 50/55 newsletters...", output)
        self.assertEqual(output.count("\nNewsletter: "), 50)
        self.assertIn("... and 5 more", output)

    def test_nothing_to_migrate(self) -> None:
        self.db.responses[("newsletters", "select")] = []

        output = self.run_migration()

        self.assertIn("No newsletters with topics found.", output)
        self.assertNotIn("Migration Complete", output)

    def test_nothing_changed_writes_nothing(self) -> None:
        self.db.responses[("newsletters", "select")] = [NEWSLETTERS[1]]

        output = self.run_migration()

        self.assertEqual(self.db.writes(), [])
        self.assertNotIn("UPDATING DATABASE", output)
        self.assertNotIn("DRY RUN COMPLETE", output)


class TestMain(unittest.TestCase):
    @patch.object(migrate_topics, "migrate_topics")
    def test_dry_run_flag(self, migrate: Mock) -> None:
        with patch.object(sys, "argv", ["migrate_topics", "--dry-run"]):
            migrate_topics.main()

        migrate.assert_called_once_with(dry_run=True)


if __name__ == "__main__":
    unittest.main()
