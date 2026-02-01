"""
Unit tests for token_counter module.

Tests token counting accuracy, encoder selection, and schema overhead calculation.
"""

import unittest
from utils.token_counter import (
    count_tokens,
    count_schema_tokens,
    estimate_llm_call_tokens,
    get_encoding_for_model,
    get_encoder_for_model,
)


class TestTokenCounter(unittest.TestCase):
    """Test token counting functionality."""

    def test_count_tokens_basic(self):
        """Test basic token counting with known text."""
        text = "hello world"
        # For GPT-5 (o200k_base), this should be ~2 tokens
        count = count_tokens(text, "gpt-5")
        self.assertGreater(count, 0)
        self.assertLess(count, 10)  # Sanity check

    def test_count_tokens_empty_string(self):
        """Test empty string handling."""
        count = count_tokens("", "gpt-5")
        self.assertEqual(count, 0)

    def test_count_tokens_unicode(self):
        """Test Unicode and special characters."""
        text = "Hello 世界 🌍"
        count = count_tokens(text, "gpt-5")
        # Unicode chars typically use multiple tokens
        self.assertGreater(count, 3)

    def test_count_tokens_very_long_text(self):
        """Test performance with large text."""
        import time

        text = "a" * 100000  # 100k characters
        start = time.time()
        count = count_tokens(text, "gpt-5")
        elapsed = time.time() - start

        # Should complete reasonably quickly (under 5 seconds)
        self.assertLess(elapsed, 5.0)
        # Should return reasonable count
        self.assertGreater(count, 10000)

    def test_get_encoding_for_model_gpt5(self):
        """Test model name to encoding mapping for GPT-5."""
        encoding = get_encoding_for_model("gpt-5")
        self.assertEqual(encoding, "o200k_base")

    def test_get_encoding_for_model_gpt5_mini(self):
        """Test GPT-5 variant encoding."""
        encoding = get_encoding_for_model("gpt-5-mini")
        self.assertEqual(encoding, "o200k_base")

    def test_get_encoding_for_model_claude(self):
        """Test non-OpenAI model encoding."""
        encoding = get_encoding_for_model("claude-sonnet-4.5")
        self.assertEqual(encoding, "cl100k_base")

    def test_get_encoding_for_model_fallback(self):
        """Test unknown model falls back to cl100k_base."""
        encoding = get_encoding_for_model("unknown-model-xyz")
        self.assertEqual(encoding, "cl100k_base")

    def test_get_encoder_for_model_caching(self):
        """Test encoder caching works."""
        encoder1 = get_encoder_for_model("gpt-5")
        encoder2 = get_encoder_for_model("gpt-5")
        # Should return same cached instance
        self.assertIs(encoder1, encoder2)

    def test_estimate_llm_call_tokens_no_schema(self):
        """Test token estimation without schema."""
        prompt = "Summarize this text"
        response = "This is a summary"

        result = estimate_llm_call_tokens(prompt, response, None, "gpt-5")

        self.assertIn("input_tokens", result)
        self.assertIn("output_tokens", result)
        self.assertIn("total_tokens", result)
        self.assertGreater(result["input_tokens"], 0)
        self.assertGreater(result["output_tokens"], 0)
        self.assertEqual(
            result["total_tokens"], result["input_tokens"] + result["output_tokens"]
        )

    def test_estimate_llm_call_tokens_with_schema(self):
        """Test token estimation with schema overhead."""
        prompt = "Extract topics from this text"
        response = '{"topics": ["bike_lanes"]}'
        schema = {
            "type": "object",
            "properties": {"topics": {"type": "array", "items": {"type": "string"}}},
        }

        # Without schema in prompt (use same model for both)
        result_no_schema = estimate_llm_call_tokens(
            prompt, response, schema, "gpt-5", include_schema_in_prompt=False
        )

        # With schema in prompt
        result_with_schema = estimate_llm_call_tokens(
            prompt, response, schema, "gpt-5", include_schema_in_prompt=True
        )

        # Schema version should have more input tokens
        self.assertGreater(
            result_with_schema["input_tokens"], result_no_schema["input_tokens"]
        )
        # Output tokens should be the same (same model, same response)
        self.assertEqual(
            result_with_schema["output_tokens"], result_no_schema["output_tokens"]
        )

    def test_count_schema_tokens(self):
        """Test schema token counting."""
        schema = {
            "type": "object",
            "properties": {
                "summary": {"type": "string", "maxLength": 2000},
                "score": {"type": "integer", "minimum": 0, "maximum": 10},
            },
            "required": ["summary", "score"],
        }

        count = count_schema_tokens(schema, "gpt-5")
        # Schema should be several tokens
        self.assertGreater(count, 10)


if __name__ == "__main__":
    unittest.main()
