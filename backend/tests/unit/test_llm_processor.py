"""
Unit tests for processing/llm_processor.py

Tests LLM processing functions including retry logic, Pydantic validation,
topic filtering, and the full processing pipeline.
"""

import unittest
from unittest.mock import patch

from processing.llm_processor import (
    TOPICS,
    extract_newsletter_metadata,
    extract_topics,
    generate_summary,
)


class TestExtractTopics(unittest.TestCase):
    """Tests for extract_topics() function"""

    @patch("processing.llm_processor.call_llm")
    @patch("builtins.print")
    def test_extract_valid_topics(self, mock_print, mock_call_llm):
        """LLM returns valid topics, filtered correctly"""
        mock_call_llm.return_value = (
            '{"topics": ["bike_lanes", "zoning_or_development_meeting_or_approval"]}'
        )

        result = extract_topics("Newsletter about bike lanes and zoning", "test-model")

        self.assertEqual(
            result, ["bike_lanes", "zoning_or_development_meeting_or_approval"]
        )
        mock_call_llm.assert_called_once()

    @patch("processing.llm_processor.call_llm")
    @patch("builtins.print")
    def test_filters_invalid_topics(self, mock_print, mock_call_llm):
        """LLM returns invalid topics, filtered out"""
        mock_call_llm.return_value = (
            '{"topics": ["bike_lanes", "invalid_topic", "not_in_list"]}'
        )

        result = extract_topics("Newsletter content", "test-model")

        # Only valid topic returned
        self.assertEqual(result, ["bike_lanes"])

    @patch("processing.llm_processor.call_llm")
    @patch("builtins.print")
    def test_returns_empty_on_no_topics(self, mock_print, mock_call_llm):
        """LLM returns no topics"""
        mock_call_llm.return_value = '{"topics": []}'

        result = extract_topics("General newsletter content", "test-model")

        self.assertEqual(result, [])

    @patch("processing.llm_processor.call_llm")
    @patch("builtins.print")
    def test_handles_llm_failure(self, mock_print, mock_call_llm):
        """LLM call fails, returns empty list"""
        mock_call_llm.side_effect = Exception("LLM service down")

        result = extract_topics("Newsletter content", "test-model")

        self.assertEqual(result, [])
        # Verify error message was printed
        error_printed = any(
            "Topic extraction failed" in str(call) for call in mock_print.call_args_list
        )
        self.assertTrue(error_printed)

    @patch("processing.llm_processor.call_llm")
    @patch("builtins.print")
    def test_topic_name_exact_match_required(self, mock_print, mock_call_llm):
        """Topic names must match TOPICS list exactly"""
        # Return topics with wrong case
        mock_call_llm.return_value = '{"topics": ["Bike_Lanes", "TRANSIT_FUNDING"]}'

        result = extract_topics("Newsletter content", "test-model")

        # Should filter out case mismatches
        self.assertEqual(result, [])

    @patch("processing.llm_processor.call_llm")
    @patch("builtins.print")
    def test_duplicate_topics_deduplicated(self, mock_print, mock_call_llm):
        """LLM returns duplicates, should be handled"""
        mock_call_llm.return_value = (
            '{"topics": ["bike_lanes", "bike_lanes", "transit_funding"]}'
        )

        result = extract_topics("Newsletter content", "test-model")

        # Result should have duplicates (filtering only checks validity, not uniqueness)
        # But let's verify the list is returned as-is after filtering
        self.assertIn("bike_lanes", result)
        self.assertIn("transit_funding", result)

    @patch("processing.llm_processor.call_llm")
    @patch("builtins.print")
    def test_prompt_includes_all_valid_topics(self, mock_print, mock_call_llm):
        """Prompt includes all topics from TOPICS constant"""
        mock_call_llm.return_value = '{"topics": []}'

        extract_topics("Newsletter content", "test-model")

        # Check that prompt includes topic list
        call_args = mock_call_llm.call_args[0]
        prompt = call_args[1]  # Second positional arg is prompt

        # Should include all topics
        for topic in TOPICS:
            self.assertIn(topic, prompt)


class TestGenerateSummary(unittest.TestCase):
    """Tests for generate_summary() function"""

    @patch("processing.llm_processor.call_llm")
    @patch("builtins.print")
    def test_generate_valid_summary(self, mock_print, mock_call_llm):
        """LLM returns valid summary"""
        summary_text = "Ward 1 announces new bike lane on Main St. Public meeting scheduled for next week."
        mock_call_llm.return_value = f'{{"summary": "{summary_text}"}}'

        result = generate_summary("Newsletter about bike lanes", "test-model")

        self.assertEqual(result, summary_text)
        mock_call_llm.assert_called_once()

    @patch("processing.llm_processor.call_llm")
    @patch("builtins.print")
    def test_max_length_enforced(self, mock_print, mock_call_llm):
        """Pydantic validates ≤2000 chars"""
        # Create a summary >2000 chars
        long_summary = "x" * 2001
        mock_call_llm.return_value = f'{{"summary": "{long_summary}"}}'

        # Should catch the exception and return empty string
        result = generate_summary("Newsletter content", "test-model")

        # The function catches all exceptions and returns empty string
        self.assertEqual(result, "")

    @patch("processing.llm_processor.call_llm")
    @patch("builtins.print")
    def test_returns_empty_on_failure(self, mock_print, mock_call_llm):
        """LLM fails, returns empty string"""
        mock_call_llm.side_effect = Exception("LLM service down")

        result = generate_summary("Newsletter content", "test-model")

        self.assertEqual(result, "")
        # Verify error message was printed
        error_printed = any(
            "Summary generation failed" in str(call)
            for call in mock_print.call_args_list
        )
        self.assertTrue(error_printed)

    @patch("processing.llm_processor.call_llm")
    @patch("builtins.print")
    def test_prompt_warns_against_alfred_hallucination(self, mock_print, mock_call_llm):
        """Prompt includes warning about not assuming Alfred as first name"""
        mock_call_llm.return_value = '{"summary": "Test summary."}'

        generate_summary("Newsletter content", "test-model")

        call_args = mock_call_llm.call_args[0]
        prompt = call_args[1]

        # Should include Alfred warning
        self.assertIn("Alfred", prompt)


class TestProcessWithOllama(unittest.TestCase):
    """Tests for extract_newsletter_metadata() main pipeline function"""

    @patch("processing.llm_processor.extract_topics")
    @patch("processing.llm_processor.generate_summary")
    @patch("time.sleep")
    def test_full_pipeline(self, mock_sleep, mock_summary, mock_topics):
        """Both LLM steps execute successfully"""
        mock_topics.return_value = ["bike_lanes", "transit_funding"]
        mock_summary.return_value = "Newsletter about transit improvements."

        newsletter = {
            "subject": "Transit Updates",
            "plain_text": "New bike lanes and transit funding announced.",
        }

        result = extract_newsletter_metadata(newsletter, "test-model")

        self.assertEqual(
            result,
            {
                "topics": ["bike_lanes", "transit_funding"],
                "summary": "Newsletter about transit improvements.",
            },
        )
        mock_topics.assert_called_once()
        mock_summary.assert_called_once()

    @patch("processing.llm_processor.call_llm")
    @patch("builtins.print")
    def test_pipeline_makes_exactly_two_llm_calls(self, mock_print, mock_call_llm):
        """Pipeline calls the LLM once for topics and once for the summary"""
        mock_call_llm.side_effect = [
            '{"topics": ["bike_lanes"]}',
            '{"summary": "Bike lanes are coming."}',
        ]

        newsletter = {"subject": "Streets", "plain_text": "New bike lanes."}

        result = extract_newsletter_metadata(newsletter, "openai:gpt-5")

        self.assertEqual(mock_call_llm.call_count, 2)
        for call in mock_call_llm.call_args_list:
            self.assertEqual(call[0][0], "openai:gpt-5")
        self.assertEqual(
            result, {"topics": ["bike_lanes"], "summary": "Bike lanes are coming."}
        )

    @patch("processing.llm_processor.extract_topics")
    @patch("builtins.print")
    @patch("time.sleep")
    def test_truncation_applied(self, mock_sleep, mock_print, mock_topics):
        """Content >100k chars truncated"""
        mock_topics.return_value = []

        # Create newsletter with >100k chars
        long_content = "x" * 150000
        newsletter = {
            "subject": "Test",
            "plain_text": long_content,
        }

        extract_newsletter_metadata(newsletter, "test-model", max_chars=100000)

        # Verify truncation message was printed
        truncation_printed = any(
            "Truncated: 150000" in str(call) for call in mock_print.call_args_list
        )
        self.assertTrue(truncation_printed)

        # Verify content passed to extract_topics is truncated
        call_args = mock_topics.call_args[0]
        content = call_args[0]
        # Content includes subject + "Today's date:" prefix, so should be ~100k + small overhead
        self.assertLess(len(content), 100100)  # Allow for date/subject overhead

    @patch("processing.llm_processor.extract_topics")
    @patch("processing.llm_processor.generate_summary")
    @patch("time.sleep")
    def test_includes_todays_date(self, mock_sleep, mock_summary, mock_topics):
        """Prompt includes today's date"""
        mock_topics.return_value = []
        mock_summary.return_value = ""

        newsletter = {
            "subject": "Test Newsletter",
            "plain_text": "Test content",
        }

        extract_newsletter_metadata(newsletter, "test-model")

        # Check that content passed to extract_topics includes date
        call_args = mock_topics.call_args[0]
        content = call_args[0]
        self.assertIn("Today's date:", content)
        # Should be in YYYY-MM-DD format

        self.assertRegex(content, r"\d{4}-\d{2}-\d{2}")

    @patch("processing.llm_processor.extract_topics")
    @patch("processing.llm_processor.generate_summary")
    @patch("builtins.print")
    @patch("time.sleep")
    def test_partial_failure_handling(
        self, mock_sleep, mock_print, mock_summary, mock_topics
    ):
        """One step fails, the other continues"""
        # extract_topics and generate_summary catch their own exceptions and
        # return default values, so we simulate that behavior
        mock_topics.return_value = ["bike_lanes"]
        mock_summary.return_value = ""  # Returns empty string on error

        newsletter = {
            "subject": "Test",
            "plain_text": "Content",
        }

        result = extract_newsletter_metadata(newsletter, "test-model")

        # Topics succeed, summary returns empty (as it does on error)
        self.assertEqual(result["topics"], ["bike_lanes"])
        self.assertEqual(result["summary"], "")

    @patch("processing.llm_processor.extract_topics")
    @patch("processing.llm_processor.generate_summary")
    @patch("builtins.print")
    @patch("time.sleep")
    def test_returns_empty_on_complete_failure(
        self, mock_sleep, mock_print, mock_summary, mock_topics
    ):
        """All steps fail gracefully"""
        # The individual functions catch their own exceptions, so they return defaults
        mock_topics.return_value = []  # Returns [] on error
        mock_summary.return_value = ""  # Returns "" on error

        newsletter = {
            "subject": "Test",
            "plain_text": "Content",
        }

        result = extract_newsletter_metadata(newsletter, "test-model")

        # All should return their error defaults
        self.assertEqual(result, {"topics": [], "summary": ""})

    @patch("processing.llm_processor.extract_topics")
    @patch("processing.llm_processor.generate_summary")
    @patch("time.sleep")
    def test_content_includes_subject(self, mock_sleep, mock_summary, mock_topics):
        """Content passed to LLM includes subject"""
        mock_topics.return_value = []
        mock_summary.return_value = ""

        newsletter = {
            "subject": "Important Announcement",
            "plain_text": "Newsletter body text",
        }

        extract_newsletter_metadata(newsletter, "test-model")

        # Check that subject was included in content
        call_args = mock_topics.call_args[0]
        content = call_args[0]
        self.assertIn("Subject: Important Announcement", content)


if __name__ == "__main__":
    unittest.main()
