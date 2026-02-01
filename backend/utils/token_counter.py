"""
Token counting utilities using tiktoken for LLM cost estimation.

Provides accurate token counting for different LLM model families using OpenAI's
tiktoken library. Supports model-specific encodings and schema overhead calculation
for structured outputs.
"""

import tiktoken
from typing import Any


# Cache encoders to avoid reloading
_encoder_cache: dict[str, tiktoken.Encoding] = {}


# Mapping of model names/patterns to tiktoken encodings
MODEL_ENCODING_MAP = {
    # OpenAI models
    "gpt-5": "o200k_base",
    "gpt-4.1": "o200k_base",
    "gpt-4o": "o200k_base",
    "gpt-4": "cl100k_base",
    "gpt-3.5": "cl100k_base",
    # Non-OpenAI models (approximations)
    "claude": "cl100k_base",
    "gemini": "cl100k_base",
    "grok": "cl100k_base",
    "deepseek": "cl100k_base",
    "llama": "cl100k_base",
}


def get_encoding_for_model(model_name: str) -> str:
    """
    Get the tiktoken encoding name for a model.

    Maps model names to appropriate tiktoken encodings. Uses pattern matching
    to handle model variants (e.g., gpt-5-mini -> o200k_base).

    Args:
        model_name: Model identifier (e.g., "gpt-5", "claude-sonnet-4.5")

    Returns:
        Encoding name (e.g., "o200k_base", "cl100k_base")

    Raises:
        ValueError: If model name doesn't match any known pattern
    """
    model_lower = model_name.lower()

    # Try exact prefix matches first
    for pattern, encoding in MODEL_ENCODING_MAP.items():
        if model_lower.startswith(pattern):
            return encoding

    # Default fallback
    return "cl100k_base"


def get_encoder_for_model(model_name: str) -> tiktoken.Encoding:
    """
    Get tiktoken encoder for a model (with caching).

    Returns a cached encoder if available, otherwise creates and caches a new one.

    Args:
        model_name: Model identifier

    Returns:
        tiktoken.Encoding instance for the model

    Raises:
        Exception: If encoding cannot be loaded
    """
    if model_name not in _encoder_cache:
        encoding_name = get_encoding_for_model(model_name)
        _encoder_cache[model_name] = tiktoken.get_encoding(encoding_name)

    return _encoder_cache[model_name]


def count_tokens(text: str, model_name: str) -> int:
    """
    Count tokens in text using model-specific encoding.

    Args:
        text: Text to count tokens for
        model_name: Model identifier to determine encoding

    Returns:
        Token count as integer

    Raises:
        Exception: If encoding fails
    """
    if not text:
        return 0

    encoder = get_encoder_for_model(model_name)
    tokens = encoder.encode(text)
    return len(tokens)


def count_schema_tokens(schema: dict[str, Any], model_name: str) -> int:
    """
    Count tokens in a JSON schema.

    Schemas are added to prompts as JSON for models that don't support native
    structured output (e.g., gpt-oss). This counts the overhead.

    Args:
        schema: Pydantic model JSON schema dict
        model_name: Model identifier

    Returns:
        Token count for schema JSON representation
    """
    import json

    schema_json = json.dumps(schema, indent=2)
    return count_tokens(schema_json, model_name)


def estimate_llm_call_tokens(
    prompt: str,
    response: str,
    schema: dict[str, Any] | None,
    model_name: str,
    include_schema_in_prompt: bool = False,
) -> dict[str, int]:
    """
    Calculate input and output tokens for an LLM call.

    Counts tokens for prompt (including schema if manually added) and response.
    Matches the actual LLM processing behavior where some models require schema
    in the prompt text.

    Args:
        prompt: Input prompt text
        response: LLM response text
        schema: Optional Pydantic schema dict
        model_name: Model identifier
        include_schema_in_prompt: Whether schema is added to prompt manually
                                  (True for gpt-oss models, False for native format)

    Returns:
        Dict with keys: "input_tokens", "output_tokens", "total_tokens"
    """

    # Count prompt tokens
    input_tokens = count_tokens(prompt, model_name)

    # Add schema overhead if included in prompt
    if schema and include_schema_in_prompt:
        schema_overhead = count_schema_tokens(schema, model_name)
        # Add overhead for the instruction text: "\n\nRespond with valid JSON matching this schema:\n"
        instruction_text = "\n\nRespond with valid JSON matching this schema:\n"
        instruction_tokens = count_tokens(instruction_text, model_name)
        input_tokens += schema_overhead + instruction_tokens

    # Count response tokens
    output_tokens = count_tokens(response, model_name)

    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
