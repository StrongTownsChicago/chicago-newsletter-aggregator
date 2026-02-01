"""
Cost calculation logic for LLM API usage.

Loads pricing data from JSON configuration and calculates costs from token counts.
Supports cost comparisons across multiple models.
"""

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ModelPricing:
    """Pricing information for a specific LLM model."""

    provider: str
    model: str
    input_cost_per_1m: float
    output_cost_per_1m: float
    context_window: int
    encoding: str
    notes: str


class PricingData:
    """Load and query LLM pricing configuration."""

    def __init__(self, pricing_file: str | None = None):
        """
        Initialize pricing data from JSON file.

        Args:
            pricing_file: Path to pricing JSON file. If None, uses default location
                         (backend/config/llm_pricing.json)

        Raises:
            FileNotFoundError: If pricing file doesn't exist
            json.JSONDecodeError: If pricing file is invalid JSON
            ValueError: If pricing data is missing required fields
        """
        if pricing_file is None:
            # Default to backend/config/llm_pricing.json
            backend_dir = Path(__file__).parent.parent
            pricing_file = str(backend_dir / "config" / "llm_pricing.json")

        if not os.path.exists(pricing_file):
            raise FileNotFoundError(
                f"Pricing file not found: {pricing_file}\n"
                f"Please create backend/config/llm_pricing.json with model pricing data."
            )

        with open(pricing_file) as f:
            data = json.load(f)

        self.version = data.get("version", "unknown")
        self.updated = data.get("updated", "unknown")
        self.models: dict[str, ModelPricing] = {}

        # Parse models into ModelPricing objects
        for model_data in data.get("models", []):
            try:
                pricing = ModelPricing(
                    provider=model_data["provider"],
                    model=model_data["model"],
                    input_cost_per_1m=model_data["input_cost_per_1m"],
                    output_cost_per_1m=model_data["output_cost_per_1m"],
                    context_window=model_data["context_window"],
                    encoding=model_data["encoding"],
                    notes=model_data.get("notes", ""),
                )
                self.models[pricing.model] = pricing
            except KeyError as e:
                raise ValueError(f"Missing required field in pricing data: {e}")

    def get_model_pricing(self, model_name: str) -> ModelPricing:
        """
        Get pricing info for a specific model.

        Args:
            model_name: Model identifier (e.g., "gpt-5", "claude-sonnet-4.5")

        Returns:
            ModelPricing object for the model

        Raises:
            KeyError: If model not found in pricing data
        """
        if model_name not in self.models:
            available = ", ".join(sorted(self.models.keys()))
            raise KeyError(
                f"Model '{model_name}' not found in pricing data.\n"
                f"Available models: {available}"
            )

        return self.models[model_name]

    def list_models(self, provider: str | None = None) -> list[str]:
        """
        List available models, optionally filtered by provider.

        Args:
            provider: Optional provider filter (e.g., "openai", "anthropic")

        Returns:
            List of model names
        """
        if provider is None:
            return sorted(self.models.keys())

        return sorted(
            [
                model
                for model, pricing in self.models.items()
                if pricing.provider == provider
            ]
        )

    def list_providers(self) -> list[str]:
        """
        List all available providers.

        Returns:
            List of unique provider names
        """
        providers = {pricing.provider for pricing in self.models.values()}
        return sorted(providers)


def calculate_cost(
    input_tokens: int, output_tokens: int, model_pricing: ModelPricing
) -> dict[str, float]:
    """
    Calculate cost for token counts using model pricing.

    Args:
        input_tokens: Number of input tokens
        output_tokens: Number of output tokens
        model_pricing: ModelPricing object with cost per 1M tokens

    Returns:
        Dict with keys: "input_cost", "output_cost", "total_cost"

    Raises:
        ValueError: If token counts are negative
    """
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts cannot be negative")

    # Calculate costs (pricing is per 1M tokens, so divide by 1,000,000)
    input_cost = (input_tokens / 1_000_000) * model_pricing.input_cost_per_1m
    output_cost = (output_tokens / 1_000_000) * model_pricing.output_cost_per_1m
    total_cost = input_cost + output_cost

    return {
        "input_cost": round(input_cost, 6),
        "output_cost": round(output_cost, 6),
        "total_cost": round(total_cost, 6),
    }
