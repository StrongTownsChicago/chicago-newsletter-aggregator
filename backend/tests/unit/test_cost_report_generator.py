"""
Unit tests for cost_report_generator module.

Verifies that newsletter cost reports cover exactly the LLM calls the
processing pipeline makes (topic extraction and summary generation).
"""

import unittest

from llm_costs.cost_calculator import ModelPricing
from llm_costs.cost_report_generator import (
    TokenTotals,
    format_cost_row,
    generate_combined_text_report,
    generate_csv_report,
    generate_json_report,
    generate_text_report,
    sum_operation_tokens,
)
from llm_costs.newsletter_token_analyzer import (
    NewsletterTokenAnalysis,
    OperationTokens,
    WeeklyReportTokenAnalysis,
)

TOPIC_INPUT_TOKENS = 1000
TOPIC_OUTPUT_TOKENS = 100
SUMMARY_INPUT_TOKENS = 1200
SUMMARY_OUTPUT_TOKENS = 150


def build_analysis() -> NewsletterTokenAnalysis:
    """Build a newsletter analysis with fixed token counts per operation."""
    topic_op = OperationTokens(
        operation="topic_extraction",
        input_tokens=TOPIC_INPUT_TOKENS,
        output_tokens=TOPIC_OUTPUT_TOKENS,
        total_tokens=TOPIC_INPUT_TOKENS + TOPIC_OUTPUT_TOKENS,
    )
    summary_op = OperationTokens(
        operation="summary_generation",
        input_tokens=SUMMARY_INPUT_TOKENS,
        output_tokens=SUMMARY_OUTPUT_TOKENS,
        total_tokens=SUMMARY_INPUT_TOKENS + SUMMARY_OUTPUT_TOKENS,
    )
    total_input = TOPIC_INPUT_TOKENS + SUMMARY_INPUT_TOKENS
    total_output = TOPIC_OUTPUT_TOKENS + SUMMARY_OUTPUT_TOKENS
    return NewsletterTokenAnalysis(
        newsletter_id="test-1",
        topic_extraction=topic_op,
        summary_generation=summary_op,
        total_input_tokens=total_input,
        total_output_tokens=total_output,
        total_tokens=total_input + total_output,
    )


def operation(name: str, input_tokens: int, output_tokens: int) -> OperationTokens:
    return OperationTokens(
        operation=name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=input_tokens + output_tokens,
    )


def build_weekly_analysis(
    week_id: str, phase1: list[tuple[int, int]], phase2: tuple[int, int]
) -> WeeklyReportTokenAnalysis:
    """A weekly report analysis; only the operations feed the combined report."""
    return WeeklyReportTokenAnalysis(
        topic="bike_lanes",
        week_id=week_id,
        newsletter_count=len(phase1),
        phase1_operations=[operation("extract", *tokens) for tokens in phase1],
        phase2_operation=operation("synthesize", *phase2),
        total_input_tokens=0,
        total_output_tokens=0,
        total_tokens=0,
    )


WEEKLY_ANALYSES = [
    build_weekly_analysis("2026-W40", [(500, 50), (300, 30)], (900, 200)),
    build_weekly_analysis("2026-W41", [(200, 20)], (400, 100)),
]


PRICING = ModelPricing(
    provider="test",
    model="test-model",
    input_cost_per_1m=1.0,
    output_cost_per_1m=2.0,
    context_window=128000,
    encoding="o200k_base",
    notes="",
)


class TestCostReportGenerator(unittest.TestCase):
    """Reports include only topic extraction and summary generation."""

    def test_json_report_has_two_operations_and_matching_totals(self) -> None:
        report = generate_json_report([build_analysis()], PRICING)

        self.assertEqual(
            set(report["operations"]), {"topic_extraction", "summary_generation"}
        )
        self.assertEqual(
            report["totals"]["total_input_tokens"],
            TOPIC_INPUT_TOKENS + SUMMARY_INPUT_TOKENS,
        )
        self.assertEqual(
            report["totals"]["total_output_tokens"],
            TOPIC_OUTPUT_TOKENS + SUMMARY_OUTPUT_TOKENS,
        )

    def test_csv_report_has_one_row_per_operation(self) -> None:
        rows = generate_csv_report([build_analysis()], PRICING).strip().split("\n")

        operations = [row.split(",")[0] for row in rows[1:]]
        self.assertEqual(operations, ["topic_extraction", "summary_generation"])

    def test_text_report_describes_two_calls(self) -> None:
        report = generate_text_report([build_analysis()], PRICING)

        self.assertIn("2 calls per newsletter", report)
        self.assertNotIn("Scoring", report)


class TestTokenTotals(unittest.TestCase):
    def test_sums_operations(self) -> None:
        self.assertEqual(
            sum_operation_tokens([operation("a", 10, 1), operation("b", 5, 2)]),
            TokenTotals(input_tokens=15, output_tokens=3),
        )

    def test_no_operations_sum_to_zero(self) -> None:
        self.assertEqual(sum_operation_tokens([]), TokenTotals())

    def test_cost_row_prices_the_summed_tokens(self) -> None:
        self.assertEqual(
            format_cost_row("TOTAL", TokenTotals(1_000_000, 500_000), PRICING),
            "TOTAL                   1,000,000      500,000 $   2.0000",
        )


class TestCombinedTextReport(unittest.TestCase):
    """Newsletter and weekly costs: one row per phase, totals priced from summed tokens."""

    def test_empty_input(self) -> None:
        self.assertEqual(
            generate_combined_text_report([], WEEKLY_ANALYSES, PRICING),
            "No newsletters analyzed.",
        )

    def test_newsletters_only(self) -> None:
        lines = generate_combined_text_report(
            [build_analysis()], [], PRICING
        ).splitlines()

        for expected in [
            "Newsletters Analyzed: 1",
            "Weekly Reports Generated: 0",
            "Model: test-model (test)",
            "Pricing: $1.00/1M input, $2.00/1M output",
            "Topic Extraction            1,000          100 $   0.0012",
            "Summary Generation          1,200          150 $   0.0015",
            "SUBTOTAL                    2,200          250 $   0.0027",
            "TOTAL                       2,200          250 $   0.0027",
            "Per newsletter (processing only): $0.0027",
            "Total for 1 newsletters: $0.0027",
            "100 newsletters/month (processing only): $0.27",
            "1,000 newsletters/month (processing only): $2.70",
        ]:
            self.assertIn(expected, lines)
        self.assertFalse(any(line.startswith("WEEKLY") for line in lines))

    def test_with_weekly_reports(self) -> None:
        lines = generate_combined_text_report(
            [build_analysis()], WEEKLY_ANALYSES, PRICING
        ).splitlines()

        for expected in [
            "Weekly Reports Generated: 2",
            "WEEKLY REPORT SYNTHESIS (2 topic reports)",
            "Phase 1: Extract            1,000          100 $   0.0012",
            "Phase 2: Synthesize         1,300          300 $   0.0019",
            "SUBTOTAL                    2,300          400 $   0.0031",
            "TOTAL                       4,500          650 $   0.0058",
            "Per weekly report: $0.0015",
            "Total for 1 newsletters + 2 reports: $0.0058",
            "~4 weekly reports/month: $0.01",
            "100 newsletters + weekly reports: $0.28",
            "1,000 newsletters + weekly reports: $2.71",
        ]:
            self.assertIn(expected, lines)


if __name__ == "__main__":
    unittest.main()
