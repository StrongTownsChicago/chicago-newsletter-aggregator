"""
Unit tests for processing/weekly_report_generator.py

Tests aggregation, error handling, and resilience.
"""

import unittest
import sys
import io
from unittest.mock import patch
from processing.weekly_report_generator import (
    extract_facts_from_newsletters,
    synthesize_weekly_summary,
)
from models.weekly_report import KeyDevelopment


class TestExtractFactsFromNewsletters(unittest.TestCase):
    """Tests for extract_facts_from_newsletters() aggregation."""

    def setUp(self):
        """Suppress print output."""
        self.held_output = io.StringIO()
        sys.stdout = self.held_output

    def tearDown(self):
        """Restore stdout."""
        sys.stdout = sys.__stdout__

    @patch("processing.weekly_report_generator.extract_facts_from_single_newsletter")
    def test_aggregates_facts_from_multiple_newsletters(self, mock_extract):
        """Facts from multiple newsletters aggregated into single list."""
        # Arrange
        dev1 = KeyDevelopment(
            description="Dev from NL1", newsletter_ids=["nl-1"], wards=["10"]
        )
        dev2 = KeyDevelopment(
            description="Dev from NL2", newsletter_ids=["nl-2"], wards=["20"]
        )
        mock_extract.side_effect = [[dev1], [dev2]]

        newsletters = [
            {"id": "nl-1", "subject": "NL1", "plain_text": "C1", "source_name": "S1"},
            {"id": "nl-2", "subject": "NL2", "plain_text": "C2", "source_name": "S2"},
        ]

        # Act
        result = extract_facts_from_newsletters("bike_lanes", newsletters)

        # Assert
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].description, "Dev from NL1")
        self.assertEqual(result[1].description, "Dev from NL2")

    @patch("processing.weekly_report_generator.extract_facts_from_single_newsletter")
    def test_continues_on_individual_failure(self, mock_extract):
        """Processing continues if one newsletter fails (resilience)."""
        # Arrange
        dev1 = KeyDevelopment(description="Success", newsletter_ids=["nl-1"], wards=[])
        mock_extract.side_effect = [[], [dev1], []]  # Only middle succeeds

        newsletters = [
            {"id": "nl-1", "subject": "NL1", "plain_text": "C1", "source_name": "S1"},
            {"id": "nl-2", "subject": "NL2", "plain_text": "C2", "source_name": "S2"},
            {"id": "nl-3", "subject": "NL3", "plain_text": "C3", "source_name": "S3"},
        ]

        # Act
        result = extract_facts_from_newsletters("city_budget", newsletters)

        # Assert
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].description, "Success")
        # All 3 were attempted despite failures
        self.assertEqual(mock_extract.call_count, 3)


class TestSynthesizeWeeklySummary(unittest.TestCase):
    """Tests for synthesize_weekly_summary() function."""

    def setUp(self):
        """Suppress print output."""
        self.held_output = io.StringIO()
        sys.stdout = self.held_output

    def tearDown(self):
        """Restore stdout."""
        sys.stdout = sys.__stdout__

    @patch("processing.weekly_report_generator.call_llm")
    def test_synthesizes_facts_into_summary(self, mock_llm):
        """Multiple facts synthesized into narrative using LLM."""
        # Arrange
        mock_llm.return_value = (
            '{"summary": "This week saw significant bike lane developments."}'
        )

        facts = [
            KeyDevelopment(
                description="Ward 10 approved bike lanes",
                newsletter_ids=["nl-1"],
                wards=["10"],
            ),
            KeyDevelopment(
                description="Ward 20 announced bike lane study",
                newsletter_ids=["nl-2"],
                wards=["20"],
            ),
        ]

        # Act
        result = synthesize_weekly_summary("bike_lanes", facts, "2026-W05")

        # Assert
        self.assertIn("significant bike lane", result)
        mock_llm.assert_called_once()

    @patch("processing.weekly_report_generator.call_llm")
    def test_handles_synthesis_failure_gracefully(self, mock_llm):
        """Returns empty string on LLM failure instead of crashing."""
        # Arrange
        mock_llm.side_effect = Exception("LLM timeout")

        facts = [
            KeyDevelopment(description="Test", newsletter_ids=["nl-1"], wards=["10"])
        ]

        # Act
        result = synthesize_weekly_summary("bike_lanes", facts, "2026-W05")

        # Assert
        self.assertEqual(result, "")  # Graceful degradation


if __name__ == "__main__":
    unittest.main()
