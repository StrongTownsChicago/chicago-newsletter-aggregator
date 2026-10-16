"""
Unit tests for cost_calculator module.

Tests pricing data loading, cost calculation accuracy, and model lookup logic.
"""

import json
import tempfile
import unittest
from pathlib import Path

from utils.cost_calculator import (
    PricingData,
    calculate_cost,
)


class TestCostCalculator(unittest.TestCase):
    """Test cost calculation functionality."""

    def setUp(self) -> None:
        """Create temporary pricing file for tests."""
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.temp_dir = Path(temp_dir.name)
        self.pricing_file = str(self.temp_dir / "test_pricing.json")

        # Create valid test pricing data
        test_pricing = {
            "version": "test-1.0",
            "updated": "2026-01-31",
            "models": [
                {
                    "provider": "openai",
                    "model": "gpt-5",
                    "input_cost_per_1m": 1.25,
                    "output_cost_per_1m": 10.00,
                    "context_window": 128000,
                    "encoding": "o200k_base",
                    "notes": "Test model",
                },
                {
                    "provider": "anthropic",
                    "model": "claude-sonnet-4.5",
                    "input_cost_per_1m": 3.00,
                    "output_cost_per_1m": 15.00,
                    "context_window": 200000,
                    "encoding": "cl100k_base",
                    "notes": "Test Claude model",
                },
            ],
        }

        Path(self.pricing_file).write_text(json.dumps(test_pricing))

    def test_load_pricing_data_valid(self) -> None:
        """Test loading valid pricing file."""
        pricing = PricingData(self.pricing_file)
        self.assertEqual(pricing.version, "test-1.0")
        self.assertEqual(len(pricing.models), 2)

    def test_load_pricing_data_invalid_json(self) -> None:
        """Test invalid JSON handling."""
        invalid_file = self.temp_dir / "invalid.json"
        invalid_file.write_text("{invalid json")

        with self.assertRaises(json.JSONDecodeError):
            PricingData(str(invalid_file))

    def test_load_pricing_data_missing_file(self) -> None:
        """Test missing pricing file."""
        with self.assertRaises(FileNotFoundError) as cm:
            PricingData("/nonexistent/path/pricing.json")

        self.assertIn("not found", str(cm.exception))

    def test_get_model_pricing_exists(self) -> None:
        """Test retrieving pricing for known model."""
        pricing_data = PricingData(self.pricing_file)
        model_pricing = pricing_data.get_model_pricing("gpt-5")

        self.assertEqual(model_pricing.provider, "openai")
        self.assertEqual(model_pricing.input_cost_per_1m, 1.25)
        self.assertEqual(model_pricing.output_cost_per_1m, 10.00)

    def test_get_model_pricing_not_found(self) -> None:
        """Test unknown model handling."""
        pricing_data = PricingData(self.pricing_file)

        with self.assertRaises(KeyError) as cm:
            pricing_data.get_model_pricing("unknown-model")

        self.assertIn("not found", str(cm.exception))
        self.assertIn("Available models", str(cm.exception))

    def test_calculate_cost_basic(self) -> None:
        """Test simple cost calculation."""
        pricing_data = PricingData(self.pricing_file)
        model_pricing = pricing_data.get_model_pricing("gpt-5")

        # 1M input + 500K output tokens
        result = calculate_cost(1_000_000, 500_000, model_pricing)

        # Input: 1M * $1.25 = $1.25
        # Output: 0.5M * $10.00 = $5.00
        # Total: $6.25
        self.assertAlmostEqual(result["input_cost"], 1.25, places=2)
        self.assertAlmostEqual(result["output_cost"], 5.00, places=2)
        self.assertAlmostEqual(result["total_cost"], 6.25, places=2)

    def test_calculate_cost_zero_tokens(self) -> None:
        """Test zero token handling."""
        pricing_data = PricingData(self.pricing_file)
        model_pricing = pricing_data.get_model_pricing("gpt-5")

        result = calculate_cost(0, 0, model_pricing)

        self.assertEqual(result["input_cost"], 0.0)
        self.assertEqual(result["output_cost"], 0.0)
        self.assertEqual(result["total_cost"], 0.0)

    def test_calculate_cost_precision(self) -> None:
        """Test floating point precision handling."""
        pricing_data = PricingData(self.pricing_file)
        model_pricing = pricing_data.get_model_pricing("gpt-5")

        # Small token counts
        result = calculate_cost(123, 456, model_pricing)

        # Should have reasonable precision (6 decimal places)
        self.assertIsInstance(result["input_cost"], float)
        self.assertIsInstance(result["output_cost"], float)
        self.assertIsInstance(result["total_cost"], float)

        # Total should equal sum
        self.assertAlmostEqual(
            result["total_cost"],
            result["input_cost"] + result["output_cost"],
            places=6,
        )

    def test_calculate_cost_negative_tokens(self) -> None:
        """Test invalid negative tokens."""
        pricing_data = PricingData(self.pricing_file)
        model_pricing = pricing_data.get_model_pricing("gpt-5")

        with self.assertRaises(ValueError) as cm:
            calculate_cost(-100, 500, model_pricing)

        self.assertIn("cannot be negative", str(cm.exception))

    def test_list_models_all(self) -> None:
        """Test listing all available models."""
        pricing_data = PricingData(self.pricing_file)
        models = pricing_data.list_models()

        self.assertEqual(len(models), 2)
        self.assertIn("gpt-5", models)
        self.assertIn("claude-sonnet-4.5", models)

    def test_list_models_by_provider(self) -> None:
        """Test filtering models by provider."""
        pricing_data = PricingData(self.pricing_file)

        openai_models = pricing_data.list_models(provider="openai")
        self.assertEqual(len(openai_models), 1)
        self.assertIn("gpt-5", openai_models)

        anthropic_models = pricing_data.list_models(provider="anthropic")
        self.assertEqual(len(anthropic_models), 1)
        self.assertIn("claude-sonnet-4.5", anthropic_models)

    def test_list_providers(self) -> None:
        """Test listing all providers."""
        pricing_data = PricingData(self.pricing_file)
        providers = pricing_data.list_providers()

        self.assertEqual(len(providers), 2)
        self.assertIn("openai", providers)
        self.assertIn("anthropic", providers)

    def test_load_pricing_data_missing_fields(self) -> None:
        """Test pricing data with missing required fields."""
        invalid_data = {
            "version": "test",
            "models": [
                {
                    "provider": "openai",
                    "model": "gpt-5",
                    # Missing input_cost_per_1m, output_cost_per_1m, etc.
                }
            ],
        }

        invalid_file = self.temp_dir / "invalid_schema.json"
        invalid_file.write_text(json.dumps(invalid_data))

        with self.assertRaises(ValueError) as cm:
            PricingData(str(invalid_file))

        self.assertIn("Missing required field", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
