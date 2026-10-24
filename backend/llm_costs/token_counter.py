"""
Token counting utilities using tiktoken for LLM cost estimation.

Provides accurate token counting for different LLM model families using OpenAI's
tiktoken library. Supports model-specific encodings and schema overhead calculation
for structured outputs.
"""

from typing import Any

import tiktoken

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
    Return the tiktoken encoding name for a model.

    Matches the model name case-insensitively by prefix against MODEL_ENCODING_MAP,
    so variants share an encoding (gpt-5-mini -> o200k_base). Unknown models
    fall back to cl100k_base.
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
    Return the tiktoken encoder for a model, cached per model name.

    Propagates tiktoken's error if the encoding cannot be loaded.
    """
    if model_name not in _encoder_cache:
        encoding_name = get_encoding_for_model(model_name)
        _encoder_cache[model_name] = tiktoken.get_encoding(encoding_name)

    return _encoder_cache[model_name]


def count_tokens(text: str, model_name: str) -> int:
    """
    Count tokens in text with the model's encoding; empty text is 0."""
    if not text:
        return 0

    encoder = get_encoder_for_model(model_name)
    tokens = encoder.encode(text)
    return len(tokens)


def count_schema_tokens(schema: dict[str, Any], model_name: str) -> int:
    """
    Count tokens in a JSON schema serialized with indent=2.

    Models without native structured output (e.g. gpt-oss) get the schema in
    the prompt as JSON; this measures that overhead.
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
    Count input and output tokens for one LLM call.

    Input is the prompt, plus the schema and its instruction line when
    include_schema_in_prompt (gpt-oss models take the schema in the prompt text
    rather than a native format). Returns "input_tokens", "output_tokens" and
    "total_tokens".
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
