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
    extract_facts_from_single_newsletter,
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


class TestExtractFactsFromSingleNewsletter(unittest.TestCase):
    """Tests for extract_facts_from_single_newsletter() LLM extraction + mapping."""

    def setUp(self):
        """Suppress print output."""
        self.held_output = io.StringIO()
        sys.stdout = self.held_output

    def tearDown(self):
        """Restore stdout."""
        sys.stdout = sys.__stdout__

    @patch("processing.weekly_report_generator.call_llm")
    def test_attaches_newsletter_id_and_ward_deterministically(self, mock_llm):
        """The LLM returns only a description; id and ward come from the source."""
        # The LLM response provides only description — newsletter_ids and wards
        # are known deterministically from the source newsletter.
        mock_llm.return_value = '{"developments": ["Approved protected bike lanes"]}'
        newsletter = {
            "id": "nl-42",
            "subject": "Safety update",
            "plain_text": "content",
            "source_name": "Alderman 5",
            "ward_number": "5",
        }

        result = extract_facts_from_single_newsletter(
            "street_safety_or_traffic_calming", newsletter
        )

        self.assertEqual(len(result), 1)
        dev = result[0]
        self.assertIsInstance(dev, KeyDevelopment)
        self.assertEqual(dev.description, "Approved protected bike lanes")
        self.assertEqual(dev.wards, ["5"])  # from source ward_number, not the LLM
        self.assertEqual(dev.newsletter_ids, ["nl-42"])

    @patch("processing.weekly_report_generator.call_llm")
    def test_citywide_source_yields_no_wards(self, mock_llm):
        """A source without a ward number (citywide official) yields empty wards."""
        mock_llm.return_value = '{"developments": ["Citywide budget announcement"]}'
        newsletter = {
            "id": "nl-7",
            "subject": "Budget",
            "plain_text": "content",
            "source_name": "City Treasurer",
            # no ward_number
        }

        result = extract_facts_from_single_newsletter("city_budget", newsletter)

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0].wards, [])

    @patch("processing.weekly_report_generator.call_llm")
    def test_returns_empty_list_on_llm_failure(self, mock_llm):
        """A failed LLM call yields an empty list rather than raising."""
        mock_llm.side_effect = Exception("LLM timeout")
        newsletter = {
            "id": "nl-1",
            "subject": "S",
            "plain_text": "C",
            "source_name": "Src",
        }

        result = extract_facts_from_single_newsletter("city_budget", newsletter)

        self.assertEqual(result, [])


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
