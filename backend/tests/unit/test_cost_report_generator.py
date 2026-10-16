"""
Unit tests for cost_report_generator module.

Verifies that newsletter cost reports cover exactly the LLM calls the
processing pipeline makes (topic extraction and summary generation).
"""

import unittest

from utils.cost_calculator import ModelPricing
from utils.cost_report_generator import (
    generate_csv_report,
    generate_json_report,
    generate_text_report,
)
from utils.newsletter_token_analyzer import NewsletterTokenAnalysis, OperationTokens

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


if __name__ == "__main__":
    unittest.main()
