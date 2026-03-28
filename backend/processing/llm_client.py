"""
Multi-provider LLM client.

Dispatches LLM calls to the appropriate provider (Ollama or OpenAI) based on
a provider prefix in the model string. Format: "provider:model_name"
(e.g., "openai:gpt-5", "ollama:gpt-oss:20b"). Bare model names without a
prefix default to Ollama for backward compatibility.
"""

import json
import re
import time
from typing import Any

from ollama import Client
from openai import OpenAI

# LLM processing limits
MAX_LLM_RETRIES = 6

SUPPORTED_PROVIDERS = ("ollama", "openai")
DEFAULT_PROVIDER = "ollama"

# OpenAI reasoning models do not support temperature, top_p, or other sampling params.
# These models use reasoning_effort instead. Pattern matches o1, o3, o4, gpt-5 families.
_OPENAI_REASONING_MODEL_RE = re.compile(r"^(o\d|gpt-5)")

# Lazy-initialized clients (None until first use)
_ollama_client: Client | None = None
_openai_client: OpenAI | None = None


def _get_ollama_client() -> Client:
    """Return the cached Ollama client, creating it on first call."""
    global _ollama_client
    if _ollama_client is None:
        _ollama_client = Client(timeout=360.0)
    return _ollama_client


def _get_openai_client() -> OpenAI:
    """Return the cached OpenAI client, creating it on first call."""
    global _openai_client
    if _openai_client is None:
        _openai_client = OpenAI(timeout=120.0)
    return _openai_client


def parse_model_string(model_string: str) -> tuple[str, str]:
    """
    Parse a model string into (provider, model_name).

    Accepts an optional provider prefix separated by a colon. Bare model names
    (without a recognized provider prefix) default to Ollama for backward
    compatibility. Ollama model names may contain colons (e.g., "gpt-oss:20b")
    and are handled correctly.

    Args:
        model_string: Model identifier, optionally prefixed with provider
                      (e.g., "openai:gpt-5", "ollama:gpt-oss:20b", "gpt-oss:20b")

    Returns:
        Tuple of (provider, model_name)

    Raises:
        ValueError: If the provider prefix is present but not in SUPPORTED_PROVIDERS
    """
    if ":" in model_string:
        first_segment = model_string.split(":")[0]
        if first_segment in SUPPORTED_PROVIDERS:
            provider = first_segment
            model_name = model_string[len(provider) + 1 :]
            return (provider, model_name)
        # first_segment is not a known provider — check if it looks like one
        # (i.e., lowercase alpha only) which would indicate a typo/unsupported provider
        if (
            first_segment.isalpha()
            and first_segment.islower()
            and len(first_segment) > 2
        ):
            raise ValueError(
                f"Unknown provider: '{first_segment}'. "
                f"Supported providers: {', '.join(SUPPORTED_PROVIDERS)}. "
                f"To use Ollama, omit the prefix or use 'ollama:{model_string}'."
            )
    return (DEFAULT_PROVIDER, model_string)


def call_llm(
    model: str,
    prompt: str,
    schema: dict[str, Any] | None = None,
    temperature: float = 0,
    max_retries: int = MAX_LLM_RETRIES,
) -> str:
    """
    Dispatch an LLM call to the appropriate provider adapter.

    The model string may include an optional provider prefix (e.g., "openai:gpt-5").
    Bare model names without a recognized prefix default to Ollama for backward
    compatibility.

    Args:
        model: Model identifier with optional provider prefix
        prompt: Prompt text to send to the LLM
        schema: Optional Pydantic model JSON schema for structured output
        temperature: Sampling temperature (0 = deterministic)
        max_retries: Maximum retry attempts on failure

    Returns:
        JSON string response from the LLM (or raw text if no schema provided)

    Raises:
        ValueError: If the provider prefix is unrecognized
        Exception: If all retry attempts fail
    """
    provider, model_name = parse_model_string(model)

    if provider == "openai":
        return _call_openai(model_name, prompt, schema, temperature, max_retries)
    return _call_ollama(model_name, prompt, schema, temperature, max_retries)


def _extract_json(text: str) -> str:
    """
    Extract a JSON object from LLM response text.

    Handles cases where the LLM wraps JSON in markdown blocks or adds
    preamble/postamble text. Returns the substring between the first
    '{' and the last '}'.
    """
    text = text.strip()

    if "```json" in text:
        text = text.split("```json")[1].split("```")[0].strip()
    elif "```" in text:
        text = text.split("```")[1].split("```")[0].strip()

    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]

    return text


def _call_ollama(
    model: str,
    prompt: str,
    schema: dict[str, Any] | None,
    temperature: float,
    max_retries: int,
) -> str:
    """
    Call an Ollama model with structured output and exponential backoff retry.

    Handles the gpt-oss model limitation where Ollama's native 'format' parameter
    fails. For those models, the schema is embedded in the prompt text and JSON is
    extracted from the raw response.

    Args:
        model: Bare Ollama model name (e.g., "gpt-oss:20b")
        prompt: Prompt text
        schema: Optional JSON schema for structured output
        temperature: Sampling temperature
        max_retries: Maximum retry attempts

    Returns:
        JSON string response

    Raises:
        Exception: If all retry attempts fail
    """
    # gpt-oss models fail with "failed to load model vocabulary required for format"
    # when using Ollama's native 'format' parameter. Embed the schema in the prompt
    # and extract JSON from the raw response instead.
    # https://github.com/ollama/ollama/issues/11691
    use_native_format = schema is not None and not model.startswith("gpt-oss")

    if schema and not use_native_format:
        prompt += f"\n\nRespond with valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"

    client = _get_ollama_client()

    for attempt in range(max_retries):
        try:
            response = client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                format=schema if use_native_format else None,
                options={"temperature": temperature},
            )
            content = response.message.content

            if not content or content.strip() == "":
                raise ValueError("LLM returned empty response")

            if schema and not use_native_format:
                content = _extract_json(content)

            return content

        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                print(
                    f"  ⚠ Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
            else:
                raise Exception(f"LLM call failed after {max_retries} attempts: {e}")

    raise Exception("Unreachable code: all retry attempts exhausted")


def _add_additional_properties_false(schema: dict[str, Any]) -> dict[str, Any]:
    """
    Recursively add 'additionalProperties: false' to all object-type definitions.

    OpenAI's structured output mode requires this on all object schemas. Pydantic v2's
    model_json_schema() does not include it by default.
    """
    schema = dict(schema)
    if schema.get("type") == "object":
        schema["additionalProperties"] = False
        if "properties" in schema:
            schema["properties"] = {
                k: _add_additional_properties_false(v)
                for k, v in schema["properties"].items()
            }
    if "$defs" in schema:
        schema["$defs"] = {
            k: _add_additional_properties_false(v) for k, v in schema["$defs"].items()
        }
    return schema


def _call_openai(
    model: str,
    prompt: str,
    schema: dict[str, Any] | None,
    temperature: float,
    max_retries: int,
) -> str:
    """
    Call an OpenAI model with structured output and exponential backoff retry.

    Uses response_format with json_schema for structured output, maintaining the
    same JSON string return type as the Ollama adapter.

    Args:
        model: OpenAI model name (e.g., "gpt-5")
        prompt: Prompt text
        schema: Optional JSON schema for structured output
        temperature: Sampling temperature
        max_retries: Maximum retry attempts

    Returns:
        JSON string response

    Raises:
        Exception: If all retry attempts fail
    """
    client = _get_openai_client()

    openai_response_format: Any = None
    if schema is not None:
        processed_schema = _add_additional_properties_false(schema)
        openai_response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": "response_schema",
                "strict": True,
                "schema": processed_schema,
            },
        }

    # Reasoning models (o-series, gpt-5) do not accept temperature or other
    # sampling parameters — omit them entirely to avoid 400 errors.
    is_reasoning_model = bool(_OPENAI_REASONING_MODEL_RE.match(model))
    extra_params: dict[str, Any] = (
        {} if is_reasoning_model else {"temperature": temperature}
    )

    for attempt in range(max_retries):
        try:
            if openai_response_format is not None:
                completion = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    response_format=openai_response_format,
                    **extra_params,
                )
            else:
                completion = client.chat.completions.create(
                    model=model,
                    messages=[{"role": "user", "content": prompt}],
                    **extra_params,
                )
            message = completion.choices[0].message

            if message.refusal:
                raise ValueError(f"OpenAI refused to answer: {message.refusal}")

            content: str | None = message.content

            if not content or content.strip() == "":
                raise ValueError("LLM returned empty response")

            return content

        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2**attempt
                print(
                    f"  ⚠ Attempt {attempt + 1} failed: {e}. Retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
            else:
                raise Exception(f"LLM call failed after {max_retries} attempts: {e}")

    raise Exception("Unreachable code: all retry attempts exhausted")
