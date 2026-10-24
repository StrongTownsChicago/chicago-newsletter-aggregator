"""LLM metadata backfill (cli.process_llm_metadata): which rows each filter updates."""

import io
import os
from contextlib import redirect_stdout
from typing import Any
from unittest.mock import patch

import cli.process_llm_metadata as llm_cli
from tests.db_integration.fakes import FakeLlm
from tests.db_integration.local_supabase import TEST_PASSWORD, LocalSupabaseTestCase
from tests.fixtures.newsletter_factory import insert_newsletter, insert_source
from tests.fixtures.user_factory import create_auth_user, insert_rule

LLM_SUMMARY = "Summary from the LLM."


class TestProcessLlmMetadata(LocalSupabaseTestCase):
    """Four newsletters, newest first: two complete, two missing metadata."""

    def setUp(self) -> None:
        self.reset()
        ward_1 = insert_source(self.db, name="Ward 1 Office", ward_number=1)["id"]
        ward_2 = insert_source(self.db, name="Ward 2 Office", ward_number=2)["id"]
        self.ward_2 = ward_2
        complete = {"topics": ["city_budget"], "summary": "Stored summary."}
        self.ids = {
            name: insert_newsletter(
                self.db,
                source_id,
                subject=name,
                received_date=f"2026-10-0{day}T12:00:00+00:00",
                plain_text=f"{name} text about the snow plow schedule.",
                **fields,
            )["id"]
            for name, source_id, day, fields in (
                ("newest", ward_1, 4, complete),
                ("no_summary", ward_1, 3, {"topics": ["city_budget"], "summary": None}),
                ("no_metadata", ward_2, 2, {"topics": None, "summary": None}),
                ("oldest", ward_2, 1, complete),
            )
        }
        self.llm = FakeLlm(topics=["bike_lanes"], summary=LLM_SUMMARY)

    def run_cli(self, *args: str) -> None:
        with (
            patch("sys.argv", ["process_llm_metadata", *args]),
            patch.dict(os.environ, {"ENABLE_LLM": "true"}),
            patch("processing.llm_processor.call_llm", self.llm),
            redirect_stdout(io.StringIO()),
        ):
            llm_cli.main()

    def updated(self) -> set[str]:
        return {
            row["subject"]
            for row in self.rows("newsletters", "subject, summary, topics")
            if row["summary"] == LLM_SUMMARY and row["topics"] == ["bike_lanes"]
        }

    def test_each_filter_updates_only_the_rows_it_selects(self) -> None:
        cases: list[tuple[list[str], set[str]]] = [
            (["--missing-metadata"], {"no_summary", "no_metadata"}),
            (["--source-id", "{ward_2}"], {"no_metadata", "oldest"}),
            (["--latest", "2"], {"newest", "no_summary"}),
            (["--latest", "1", "--skip", "2"], {"no_metadata"}),
            (["--newsletter-id", "{oldest}"], {"oldest"}),
            (["--all"], set(self.ids)),
        ]
        for args, expected in cases:
            with self.subTest(args=args):
                self.setUp()  # fresh rows, and ids, for each case
                self.run_cli(
                    *(arg.format(**self.ids, ward_2=self.ward_2) for arg in args)
                )
                self.assertEqual(self.updated(), expected)

    def test_dry_run_writes_nothing_and_calls_no_llm(self) -> None:
        before = self.rows("newsletters")

        self.run_cli("--all", "--dry-run")

        self.assertEqual(self.rows("newsletters"), before)
        self.assertEqual(self.llm.prompts, [])

    def test_queue_notifications_queues_matches_for_updated_rows(self) -> None:
        user_id = create_auth_user(self.db, "bikes@example.test", TEST_PASSWORD)
        rule: dict[str, Any] = insert_rule(
            self.db, user_id, topics=["bike_lanes"], ward_numbers=["2"]
        )

        self.run_cli("--missing-metadata", "--queue-notifications")

        (queued,) = self.rows("notification_queue")
        self.assertEqual(queued["newsletter_id"], self.ids["no_metadata"])
        self.assertEqual(queued["rule_id"], rule["id"])
