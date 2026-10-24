"""Tests for the token cost CLI (cli.calculate_token_costs).

Supabase, pricing data, token analysis and report formatting are mocked. The
tests pin which newsletters and topics are analyzed, which report is written
where, and when the script exits early.
"""

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock, Mock, call, patch

from cli import calculate_token_costs as costs
from tests.fixtures.fake_supabase import FakeSupabase

NEWSLETTERS: list[dict[str, Any]] = [
    {
        "id": "n1",
        "plain_text": "Bike lanes",
        "received_date": "2026-09-28",
        "topics": ["bike_lanes"],
    },
    {
        "id": "n2",
        "plain_text": "Budget and bikes",
        "received_date": "2026-09-29",
        "topics": ["city_budget", "bike_lanes"],
    },
    {"id": "n3", "plain_text": "", "received_date": "2026-10-06", "topics": None},
]


def pricing_data() -> Mock:
    data = Mock()
    data.list_providers.return_value = ["openai"]
    data.list_models.return_value = ["gpt-5"]
    data.get_model_pricing.side_effect = lambda name: SimpleNamespace(
        model=name, input_cost_per_1m=1.25, output_cost_per_1m=10.0
    )
    return data


class TestPureHelpers(unittest.TestCase):
    def test_iso_week_id(self) -> None:
        self.assertEqual(costs.get_iso_week_id("2026-01-30"), "2026-W05")

    def test_groups_by_week_and_skips_undated(self) -> None:
        weeks = costs.group_newsletters_by_week(
            [*NEWSLETTERS, {"id": "n4", "received_date": None}]
        )

        self.assertEqual(
            {week: [nl["id"] for nl in items] for week, items in weeks.items()},
            {"2026-W40": ["n1", "n2"], "2026-W41": ["n3"]},
        )

    def test_collects_unique_topics(self) -> None:
        self.assertEqual(
            costs.get_topics_from_newsletters(NEWSLETTERS),
            {"bike_lanes", "city_budget"},
        )


class TestFetchNewsletters(unittest.TestCase):
    def setUp(self) -> None:
        self.db = FakeSupabase(
            {
                ("newsletters", "select"): [
                    {"id": "n1", "sources": {"name": "Ward 1", "ward_number": 1}},
                    {"id": "n2", "sources": None},
                ]
            }
        )
        patcher = patch.object(costs, "get_supabase_client", return_value=self.db)
        patcher.start()
        self.addCleanup(patcher.stop)

    def fetch(self, **filters: Any) -> list[dict[str, Any]]:
        with redirect_stdout(io.StringIO()):
            return costs.fetch_newsletters(**filters)

    def test_flattens_the_source_join(self) -> None:
        self.assertEqual(
            self.fetch(latest=2),
            [
                {"id": "n1", "source_name": "Ward 1", "ward_number": 1},
                {"id": "n2", "sources": None},
            ],
        )

    def test_filters_by_newsletter_before_source(self) -> None:
        self.fetch(newsletter_id="n1", source_id=4, latest=3)

        (query,) = self.db.executed
        self.assertEqual(query.equal_filters, {"id": "n1"})
        self.assertIn(("order", ("received_date",), {"desc": True}), query.calls)
        self.assertIn(("limit", (3,), {}), query.calls)

    def test_filters_by_source(self) -> None:
        self.fetch(source_id=4)

        (query,) = self.db.executed
        self.assertEqual(query.equal_filters, {"source_id": 4})
        self.assertNotIn("limit", [name for name, _, _ in query.calls])

    def test_no_rows(self) -> None:
        self.db.responses[("newsletters", "select")] = []

        self.assertEqual(self.fetch(latest=1), [])


@patch.object(costs, "generate_comparison_report", return_value="COMPARISON")
@patch.object(costs, "generate_csv_report", return_value="csv,data")
@patch.object(costs, "generate_json_report", return_value={"report": 1})
@patch.object(costs, "generate_combined_text_report", return_value="COMBINED")
@patch.object(costs, "generate_text_report", return_value="TEXT")
class TestMain(unittest.TestCase):
    def setUp(self) -> None:
        self.pricing = pricing_data()
        self.fetch = Mock(return_value=[dict(nl) for nl in NEWSLETTERS])
        self.analyze = Mock(side_effect=lambda nl, model: f"{model}:{nl['id']}")
        self.analyze_weekly = Mock(
            side_effect=lambda **kwargs: f"{kwargs['week_id']}:{kwargs['topic']}"
        )
        for target, value in {
            "PricingData": Mock(return_value=self.pricing),
            "fetch_newsletters": self.fetch,
            "analyze_newsletter_tokens": self.analyze,
            "analyze_weekly_report_tokens": self.analyze_weekly,
        }.items():
            patcher = patch.object(costs, target, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_main(self, *argv: str) -> str:
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["calculate_token_costs", *argv]),
            redirect_stdout(output),
        ):
            costs.main()
        return output.getvalue()

    def exit_code(self, *argv: str) -> tuple[Any, str]:
        output = io.StringIO()
        with (
            patch.object(sys, "argv", ["calculate_token_costs", *argv]),
            redirect_stdout(output),
            self.assertRaises(SystemExit) as raised,
        ):
            costs.main()
        return raised.exception.code, output.getvalue()

    def test_single_model_text_report(self, text: MagicMock, *_: MagicMock) -> None:
        output = self.run_main("--latest", "3", "--model", "gpt-5")

        self.fetch.assert_called_once_with(latest=3, newsletter_id=None, source_id=None)
        self.assertEqual(
            self.analyze.call_args_list,
            [call(NEWSLETTERS[0], "gpt-5"), call(NEWSLETTERS[1], "gpt-5")],
        )
        (analyses, model_pricing) = text.call_args.args
        self.assertEqual(analyses, ["gpt-5:n1", "gpt-5:n2"])
        self.assertEqual(model_pricing.model, "gpt-5")
        self.assertIn("  Warning: Newsletter 3 has no plain_text, skipping", output)
        self.assertIn("  Completed 2 newsletters", output)
        self.assertIn("TEXT", output)

    def test_weekly_analysis_per_week_and_topic(
        self, text: MagicMock, combined: MagicMock, *_: MagicMock
    ) -> None:
        output = self.run_main("--latest", "3", "--include-weekly")

        self.assertEqual(
            [
                (
                    kwargs["week_id"],
                    kwargs["topic"],
                    [nl["id"] for nl in kwargs["newsletters"]],
                )
                for _, kwargs in self.analyze_weekly.call_args_list
            ],
            [
                ("2026-W40", "bike_lanes", ["n1", "n2"]),
                ("2026-W40", "city_budget", ["n2"]),
            ],
        )
        self.assertEqual(self.analyze_weekly.call_args.kwargs["model_name"], "gpt-5")
        text.assert_not_called()
        (analyses, weekly, _pricing) = combined.call_args.args
        self.assertEqual(analyses, ["gpt-5:n1", "gpt-5:n2"])
        self.assertEqual(weekly, ["2026-W40:bike_lanes", "2026-W40:city_budget"])
        self.assertIn("  Found 2 weeks of newsletters", output)
        self.assertIn(
            "Skipping weekly analysis - run process_llm_metadata first", output
        )
        self.assertIn("  Completed 2 weekly reports", output)
        self.assertIn("COMBINED", output)

    def test_weekly_without_any_topics_falls_back_to_the_text_report(
        self, text: MagicMock, combined: MagicMock, *_: MagicMock
    ) -> None:
        self.fetch.return_value = [dict(NEWSLETTERS[0], topics=None)]

        self.run_main("--latest", "1", "--include-weekly")

        combined.assert_not_called()
        text.assert_called_once()

    def test_json_and_csv_files_replace_the_text_report(
        self,
        text: MagicMock,
        _combined: MagicMock,
        json_report: MagicMock,
        *_: MagicMock,
    ) -> None:
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        json_path = Path(directory.name) / "costs.json"
        csv_path = Path(directory.name) / "costs.csv"

        output = self.run_main(
            "--latest",
            "3",
            "--output-json",
            str(json_path),
            "--output-csv",
            str(csv_path),
        )

        text.assert_not_called()
        self.assertEqual(json_report.call_args.args[0], ["gpt-5:n1", "gpt-5:n2"])
        self.assertEqual(json.loads(json_path.read_text()), {"report": 1})
        self.assertEqual(csv_path.read_text(), "csv,data")
        self.assertIn(f"JSON report saved to: {json_path}", output)
        self.assertIn(f"CSV report saved to: {csv_path}", output)

    def test_several_models_print_a_comparison(
        self, text: MagicMock, *mocks: MagicMock
    ) -> None:
        comparison = mocks[-1]

        output = self.run_main("--latest", "3", "--models", "gpt-5, claude")

        text.assert_not_called()
        analyses_by_model, pricing_by_model = comparison.call_args.args
        self.assertEqual(
            analyses_by_model,
            {"gpt-5": ["gpt-5:n1", "gpt-5:n2"], "claude": ["claude:n1", "claude:n2"]},
        )
        self.assertEqual(list(pricing_by_model), ["gpt-5", "claude"])
        self.assertIn("COMPARISON", output)

    def test_list_models(self, *_: MagicMock) -> None:
        code, output = self.exit_code("--list-models")

        self.assertEqual(code, 0)
        self.assertIn("OPENAI:", output)
        self.assertIn(
            "  gpt-5                     $  1.25/1M input, $ 10.00/1M output", output
        )
        self.fetch.assert_not_called()

    def test_requires_a_selection(self, *_: MagicMock) -> None:
        code, output = self.exit_code()

        self.assertEqual(code, 1)
        self.assertIn(
            "Error: Must specify --latest, --newsletter-id, or --source-id", output
        )
        self.fetch.assert_not_called()

    def test_no_newsletters_exits(self, *_: MagicMock) -> None:
        self.fetch.return_value = []

        code, _output = self.exit_code("--latest", "3")

        self.assertEqual(code, 1)
        self.analyze.assert_not_called()

    def test_unknown_model_exits_before_analysis(self, *_: MagicMock) -> None:
        self.pricing.get_model_pricing.side_effect = KeyError("no such model")

        code, output = self.exit_code("--latest", "3", "--model", "nope")

        self.assertEqual(code, 1)
        self.assertIn("Error: 'no such model'", output)
        self.analyze.assert_not_called()

    def test_missing_pricing_file_exits(self, *_: MagicMock) -> None:
        with patch.object(costs, "PricingData", side_effect=FileNotFoundError("gone")):
            code, output = self.exit_code("--latest", "3")

        self.assertEqual(code, 1)
        self.assertIn("Error: gone", output)

    def test_broken_pricing_file_exits(self, *_: MagicMock) -> None:
        with patch.object(costs, "PricingData", side_effect=ValueError("bad json")):
            code, output = self.exit_code("--latest", "3")

        self.assertEqual(code, 1)
        self.assertIn("Error loading pricing data: bad json", output)


if __name__ == "__main__":
    unittest.main()
