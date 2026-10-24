"""Tests for generate_weekly_topic_report(): validation, week range, query and report assembly."""

import io
import unittest
from contextlib import redirect_stdout
from typing import Any
from unittest.mock import MagicMock, patch

from models.types import NewsletterID
from models.weekly_report import KeyDevelopment
from processing.weekly_report_generator import generate_weekly_topic_report
from tests.fixtures.mock_helpers import create_mock_supabase

TOPIC = "missing_middle_housing"
WEEK_ID = "2026-W42"
WEEK_RANGE = [{"week_start": "2026-10-12", "week_end": "2026-10-18"}]
NEWSLETTER_ROWS: list[dict[str, Any]] = [
    {
        "id": "nl-1",
        "subject": "Ward update",
        "plain_text": "Six-flats approved",
        "received_date": "2026-10-13",
        "source": {"name": "Ald. One", "ward_number": 1},
    },
    {
        "id": "nl-2",
        "subject": "City news",
        "plain_text": None,
        "received_date": "2026-10-14",
        "source": None,
    },
]
FACTS = [
    KeyDevelopment(
        description="Six-flat approved", newsletter_ids=[NewsletterID("nl-1")]
    )
]


def supabase_with(
    week_range: list[dict[str, str]], rows: list[dict[str, object]]
) -> MagicMock:
    supabase = create_mock_supabase(rows)
    supabase.gte.return_value = supabase
    supabase.lte.return_value = supabase
    supabase.rpc.return_value.execute.return_value.data = week_range
    return supabase


@patch("processing.weekly_report_generator.synthesize_weekly_summary")
@patch("processing.weekly_report_generator.extract_facts_from_newsletters")
@patch("processing.weekly_report_generator.get_supabase_client")
class TestGenerateWeeklyTopicReport(unittest.TestCase):
    def setUp(self) -> None:
        self.enterContext(redirect_stdout(io.StringIO()))

    def test_builds_report_from_the_weeks_newsletters(
        self, get_client: MagicMock, extract: MagicMock, synthesize: MagicMock
    ) -> None:
        get_client.return_value = supabase_with(WEEK_RANGE, NEWSLETTER_ROWS)
        extract.return_value = FACTS
        synthesize.return_value = "A summary."

        report = generate_weekly_topic_report(TOPIC, WEEK_ID, model="test-model")

        assert report is not None
        self.assertEqual(report.report_summary, "A summary.")
        self.assertEqual(report.newsletter_ids, ["nl-1", "nl-2"])
        self.assertEqual(report.key_developments, FACTS)
        newsletters = extract.call_args.args[1]
        self.assertEqual(
            newsletters[0],
            {
                "id": "nl-1",
                "subject": "Ward update",
                "plain_text": "Six-flats approved",
                "received_date": "2026-10-13",
                "source_name": "Ald. One",
                "ward_number": "1",
            },
        )
        self.assertEqual(newsletters[1]["source_name"], "Unknown")
        self.assertIsNone(newsletters[1]["ward_number"])
        self.assertEqual(newsletters[1]["plain_text"], "")
        synthesize.assert_called_once_with(TOPIC, FACTS, WEEK_ID, "test-model")

    def test_rejects_unknown_topic_and_malformed_week_without_querying(
        self, get_client: MagicMock, extract: MagicMock, synthesize: MagicMock
    ) -> None:
        for topic, week_id in [
            ("not_a_topic", WEEK_ID),
            (TOPIC, "2026-42"),
            (TOPIC, "x-Wy"),
        ]:
            with self.subTest(topic=topic, week_id=week_id):
                self.assertIsNone(generate_weekly_topic_report(topic, week_id))
        get_client.assert_not_called()

    def test_returns_none_when_the_week_range_is_unavailable(
        self, get_client: MagicMock, extract: MagicMock, synthesize: MagicMock
    ) -> None:
        failing = supabase_with([], [])
        failing.rpc.side_effect = RuntimeError("rpc down")
        for supabase in (supabase_with([], NEWSLETTER_ROWS), failing):
            with self.subTest(supabase=supabase):
                get_client.return_value = supabase
                self.assertIsNone(generate_weekly_topic_report(TOPIC, WEEK_ID))
        extract.assert_not_called()

    def test_returns_none_without_newsletters_facts_or_summary(
        self, get_client: MagicMock, extract: MagicMock, synthesize: MagicMock
    ) -> None:
        cases = [
            ([], FACTS, "A summary."),
            (NEWSLETTER_ROWS, [], "A summary."),
            (NEWSLETTER_ROWS, FACTS, ""),
        ]
        for rows, facts, summary in cases:
            with self.subTest(rows=len(rows), facts=len(facts), summary=summary):
                get_client.return_value = supabase_with(WEEK_RANGE, rows)
                extract.return_value = facts
                synthesize.return_value = summary
                self.assertIsNone(generate_weekly_topic_report(TOPIC, WEEK_ID))

    def test_returns_none_when_the_pipeline_raises(
        self, get_client: MagicMock, extract: MagicMock, synthesize: MagicMock
    ) -> None:
        get_client.return_value = supabase_with(WEEK_RANGE, NEWSLETTER_ROWS)
        extract.side_effect = RuntimeError("LLM down")
        self.assertIsNone(generate_weekly_topic_report(TOPIC, WEEK_ID))


if __name__ == "__main__":
    unittest.main()
