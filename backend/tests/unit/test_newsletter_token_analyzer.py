"""
Unit tests for newsletter_token_analyzer module.

Tests token analysis for newsletter processing and weekly report workflows.
"""

import unittest
from utils.newsletter_token_analyzer import (
    analyze_newsletter_tokens,
    analyze_weekly_report_tokens,
)


class TestNewsletterTokenAnalyzer(unittest.TestCase):
    """Test newsletter token analysis functionality."""

    def test_analyze_newsletter_tokens_basic(self):
        """Test basic newsletter analysis."""
        newsletter = {
            "id": "test-123",
            "subject": "Weekly Update from Alderman",
            "plain_text": "This week we approved new bike lanes on Main Street. Community meeting Tuesday at 6pm.",
        }

        analysis = analyze_newsletter_tokens(newsletter, "gpt-5")

        # Should have 3 operations
        self.assertEqual(analysis.topic_extraction.operation, "topic_extraction")
        self.assertEqual(analysis.summary_generation.operation, "summary_generation")
        self.assertEqual(analysis.relevance_scoring.operation, "relevance_scoring")

        # All operations should have token counts
        self.assertGreater(analysis.topic_extraction.input_tokens, 0)
        self.assertGreater(analysis.topic_extraction.output_tokens, 0)
        self.assertGreater(analysis.summary_generation.input_tokens, 0)
        self.assertGreater(analysis.summary_generation.output_tokens, 0)
        self.assertGreater(analysis.relevance_scoring.input_tokens, 0)
        self.assertGreater(analysis.relevance_scoring.output_tokens, 0)

        # Total should equal sum
        expected_total = (
            analysis.topic_extraction.total_tokens
            + analysis.summary_generation.total_tokens
            + analysis.relevance_scoring.total_tokens
        )
        self.assertEqual(analysis.total_tokens, expected_total)

    def test_analyze_newsletter_tokens_truncation(self):
        """Test content truncation handling."""
        # Create newsletter with >100k chars
        long_text = "a" * 150000

        newsletter = {
            "subject": "Test",
            "plain_text": long_text,
        }

        # Should not raise error, should truncate
        analysis = analyze_newsletter_tokens(newsletter, "gpt-5", max_chars=100000)
        self.assertIsNotNone(analysis)

    def test_analyze_newsletter_tokens_empty_content(self):
        """Test newsletter with no plain_text."""
        newsletter = {
            "subject": "Empty Newsletter",
            "plain_text": "",
        }

        analysis = analyze_newsletter_tokens(newsletter, "gpt-5")

        # Should still return analysis with minimal tokens
        self.assertIsNotNone(analysis)
        self.assertGreater(analysis.total_tokens, 0)

    def test_analyze_newsletter_tokens_schema_overhead(self):
        """Test schema overhead for gpt-oss models."""
        newsletter = {
            "subject": "Test",
            "plain_text": "Short newsletter.",
        }

        # gpt-oss should have schema in prompt
        analysis_gpt_oss = analyze_newsletter_tokens(newsletter, "gpt-oss:20b")

        # gpt-4o should not have schema in prompt
        analysis_gpt4o = analyze_newsletter_tokens(newsletter, "gpt-4o")

        # gpt-oss should have higher input tokens (due to schema overhead)
        self.assertGreater(
            analysis_gpt_oss.total_input_tokens, analysis_gpt4o.total_input_tokens
        )

    def test_analyze_weekly_report_tokens_basic(self):
        """Test basic weekly report analysis."""
        newsletters = [
            {
                "id": "nl-1",
                "subject": "Update 1",
                "plain_text": "Bike lanes approved.",
                "source_name": "Alderman Smith",
                "ward_number": "42",
            },
            {
                "id": "nl-2",
                "subject": "Update 2",
                "plain_text": "Traffic calming measures announced.",
                "source_name": "Alderman Jones",
                "ward_number": "43",
            },
        ]

        analysis = analyze_weekly_report_tokens(
            topic="bike_lanes",
            newsletters=newsletters,
            week_id="2026-W05",
            model_name="gpt-5",
        )

        # Phase 1: Should have one operation per newsletter
        self.assertEqual(len(analysis.phase1_operations), 2)

        # Phase 2: Should have one synthesis operation
        self.assertEqual(analysis.phase2_operation.operation, "phase2_synthesis")

        # All operations should have token counts
        for op in analysis.phase1_operations:
            self.assertGreater(op.input_tokens, 0)
            self.assertGreater(op.output_tokens, 0)

        self.assertGreater(analysis.phase2_operation.input_tokens, 0)
        self.assertGreater(analysis.phase2_operation.output_tokens, 0)

        # Newsletter count should match
        self.assertEqual(analysis.newsletter_count, 2)

    def test_analyze_weekly_report_tokens_totals(self):
        """Test weekly report token totals calculation."""
        newsletters = [
            {
                "id": "nl-1",
                "subject": "Update",
                "plain_text": "Content.",
                "source_name": "Alderman",
                "ward_number": "1",
            },
        ]

        analysis = analyze_weekly_report_tokens(
            topic="bike_lanes",
            newsletters=newsletters,
            week_id="2026-W05",
            model_name="gpt-5",
        )

        # Calculate expected totals
        phase1_input = sum(op.input_tokens for op in analysis.phase1_operations)
        phase1_output = sum(op.output_tokens for op in analysis.phase1_operations)

        expected_total_input = phase1_input + analysis.phase2_operation.input_tokens
        expected_total_output = phase1_output + analysis.phase2_operation.output_tokens

        self.assertEqual(analysis.total_input_tokens, expected_total_input)
        self.assertEqual(analysis.total_output_tokens, expected_total_output)
        self.assertEqual(
            analysis.total_tokens, expected_total_input + expected_total_output
        )


if __name__ == "__main__":
    unittest.main()
