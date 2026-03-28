"""
Unit tests for processing/llm_client.py

Tests multi-provider LLM dispatch, provider adapters (Ollama and OpenAI),
JSON extraction, and client lifecycle management.
"""

import unittest
from unittest.mock import Mock, patch

import processing.llm_client as llm_client
from processing.llm_client import (
    parse_model_string,
    call_llm,
    _call_ollama,
    _call_openai,
    _extract_json,
    _get_ollama_client,
    _get_openai_client,
)
from tests.fixtures.mock_helpers import (
    create_mock_ollama_client,
    create_mock_openai_client,
)


class TestParseModelString(unittest.TestCase):
    """Tests for parse_model_string() provider prefix parsing."""

    def test_openai_prefix(self):
        """'openai:gpt-5' parses to ('openai', 'gpt-5')"""
        self.assertEqual(parse_model_string("openai:gpt-5"), ("openai", "gpt-5"))

    def test_ollama_prefix(self):
        """'ollama:gpt-oss:20b' parses to ('ollama', 'gpt-oss:20b')"""
        self.assertEqual(
            parse_model_string("ollama:gpt-oss:20b"), ("ollama", "gpt-oss:20b")
        )

    def test_ollama_prefix_simple_model(self):
        """'ollama:llama3' parses to ('ollama', 'llama3')"""
        self.assertEqual(parse_model_string("ollama:llama3"), ("ollama", "llama3"))

    def test_bare_name_with_colon_defaults_to_ollama(self):
        """'gpt-oss:20b' defaults to ('ollama', 'gpt-oss:20b') for backward compatibility"""
        self.assertEqual(parse_model_string("gpt-oss:20b"), ("ollama", "gpt-oss:20b"))

    def test_bare_name_without_colon_defaults_to_ollama(self):
        """'llama3' defaults to ('ollama', 'llama3')"""
        self.assertEqual(parse_model_string("llama3"), ("ollama", "llama3"))

    def test_unknown_provider_raises_value_error(self):
        """Unknown provider prefix raises ValueError"""
        with self.assertRaises(ValueError) as ctx:
            parse_model_string("anthropic:claude")
        self.assertIn("anthropic", str(ctx.exception))
        self.assertIn("Unknown provider", str(ctx.exception))

    def test_empty_string_defaults_to_ollama(self):
        """Empty model string defaults to ollama provider"""
        provider, model = parse_model_string("")
        self.assertEqual(provider, "ollama")
        self.assertEqual(model, "")


class TestCallLLMDispatch(unittest.TestCase):
    """Tests that call_llm() routes to the correct provider adapter."""

    @patch("processing.llm_client._call_ollama")
    def test_dispatches_to_ollama_with_prefix(self, mock_ollama):
        """'ollama:gpt-oss:20b' routes to _call_ollama with 'gpt-oss:20b'"""
        mock_ollama.return_value = '{"topics": []}'
        call_llm("ollama:gpt-oss:20b", "test prompt")
        mock_ollama.assert_called_once_with("gpt-oss:20b", "test prompt", None, 0, 6)

    @patch("processing.llm_client._call_openai")
    def test_dispatches_to_openai_with_prefix(self, mock_openai):
        """'openai:gpt-5' routes to _call_openai with 'gpt-5'"""
        mock_openai.return_value = '{"topics": []}'
        call_llm("openai:gpt-5", "test prompt")
        mock_openai.assert_called_once_with("gpt-5", "test prompt", None, 0, 6)

    @patch("processing.llm_client._call_ollama")
    def test_dispatches_bare_name_to_ollama(self, mock_ollama):
        """Bare model name 'gpt-oss:20b' routes to _call_ollama"""
        mock_ollama.return_value = '{"topics": []}'
        call_llm("gpt-oss:20b", "test prompt")
        mock_ollama.assert_called_once_with("gpt-oss:20b", "test prompt", None, 0, 6)

    @patch("processing.llm_client._call_ollama")
    def test_passes_all_parameters_to_adapter(self, mock_ollama):
        """All parameters are forwarded correctly to the adapter."""
        mock_ollama.return_value = '{"result": "ok"}'
        schema = {"type": "object"}
        call_llm(
            "ollama:llama3", "my prompt", schema=schema, temperature=0.5, max_retries=3
        )
        mock_ollama.assert_called_once_with("llama3", "my prompt", schema, 0.5, 3)

    def test_unknown_provider_raises_before_calling_adapter(self):
        """Unknown provider raises ValueError without calling any adapter."""
        with self.assertRaises(ValueError):
            call_llm("anthropic:claude", "test prompt")


class TestCallOllama(unittest.TestCase):
    """Tests for the Ollama provider adapter."""

    def setUp(self):
        # Reset global cached client before each test
        llm_client._ollama_client = None

    @patch("processing.llm_client._get_ollama_client")
    def test_successful_call(self, mock_get_client):
        """Successful Ollama call returns response content."""
        mock_client = create_mock_ollama_client('{"topics": ["bike_lanes"]}')
        mock_get_client.return_value = mock_client

        result = _call_ollama("llama3", "test prompt", None, 0, 3)
        self.assertEqual(result, '{"topics": ["bike_lanes"]}')

    @patch("processing.llm_client._get_ollama_client")
    def test_passes_temperature_in_options(self, mock_get_client):
        """Temperature is passed inside the options dict."""
        mock_client = create_mock_ollama_client('{"result": "ok"}')
        mock_get_client.return_value = mock_client

        _call_ollama("llama3", "test prompt", None, 0.7, 3)

        call_kwargs = mock_client.chat.call_args[1]
        self.assertEqual(call_kwargs["options"]["temperature"], 0.7)

    @patch("processing.llm_client._get_ollama_client")
    def test_native_format_for_non_gpt_oss_models(self, mock_get_client):
        """Non-gpt-oss models use the native format parameter."""
        mock_client = create_mock_ollama_client('{"topics": []}')
        mock_get_client.return_value = mock_client
        schema = {"type": "object"}

        _call_ollama("llama3", "test prompt", schema, 0, 3)

        call_kwargs = mock_client.chat.call_args[1]
        self.assertEqual(call_kwargs["format"], schema)

    @patch("processing.llm_client._get_ollama_client")
    def test_gpt_oss_schema_in_prompt(self, mock_get_client):
        """gpt-oss models embed schema in prompt and pass format=None."""
        mock_client = create_mock_ollama_client('{"topics": []}')
        mock_get_client.return_value = mock_client
        schema = {"type": "object"}

        _call_ollama("gpt-oss:20b", "base prompt", schema, 0, 3)

        call_kwargs = mock_client.chat.call_args[1]
        self.assertIsNone(call_kwargs["format"])
        # Schema should be embedded in the prompt
        message_content = call_kwargs["messages"][0]["content"]
        self.assertIn("Respond with valid JSON matching this schema", message_content)

    @patch("processing.llm_client._get_ollama_client")
    def test_gpt_oss_json_extraction(self, mock_get_client):
        """gpt-oss markdown-wrapped JSON is extracted correctly."""
        raw_response = 'Here is the JSON:\n```json\n{"topics": ["bike_lanes"]}\n```'
        mock_client = create_mock_ollama_client(raw_response)
        mock_get_client.return_value = mock_client
        schema = {"type": "object"}

        result = _call_ollama("gpt-oss:20b", "test prompt", schema, 0, 3)
        self.assertEqual(result, '{"topics": ["bike_lanes"]}')

    @patch("processing.llm_client._get_ollama_client")
    @patch("time.sleep")
    @patch("builtins.print")
    def test_retry_on_failure(self, mock_print, mock_sleep, mock_get_client):
        """Failed calls retry with exponential backoff."""
        success_response = Mock()
        success_response.message.content = '{"topics": []}'

        mock_client = Mock()
        mock_client.chat.side_effect = [
            Exception("First failure"),
            Exception("Second failure"),
            success_response,
        ]
        mock_get_client.return_value = mock_client

        result = _call_ollama("llama3", "test prompt", None, 0, 6)
        self.assertEqual(result, '{"topics": []}')
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_any_call(1)  # 2^0
        mock_sleep.assert_any_call(2)  # 2^1

    @patch("processing.llm_client._get_ollama_client")
    @patch("time.sleep")
    @patch("builtins.print")
    def test_max_retries_raises(self, mock_print, mock_sleep, mock_get_client):
        """All retries exhausted raises an exception."""
        mock_client = Mock()
        mock_client.chat.side_effect = Exception("Always fails")
        mock_get_client.return_value = mock_client

        with self.assertRaises(Exception) as ctx:
            _call_ollama("llama3", "test prompt", None, 0, 3)
        self.assertIn("failed after 3 attempts", str(ctx.exception))

    @patch("processing.llm_client._get_ollama_client")
    @patch("time.sleep")
    @patch("builtins.print")
    def test_empty_response_triggers_retry(
        self, mock_print, mock_sleep, mock_get_client
    ):
        """Empty response triggers retry."""
        empty_response = Mock()
        empty_response.message.content = ""
        mock_client = Mock()
        mock_client.chat.return_value = empty_response
        mock_get_client.return_value = mock_client

        with self.assertRaises(Exception) as ctx:
            _call_ollama("llama3", "test prompt", None, 0, 2)
        self.assertIn("empty response", str(ctx.exception).lower())

    @patch("processing.llm_client._get_ollama_client")
    @patch("time.sleep")
    @patch("builtins.print")
    def test_whitespace_response_triggers_retry(
        self, mock_print, mock_sleep, mock_get_client
    ):
        """Whitespace-only response triggers retry."""
        whitespace_response = Mock()
        whitespace_response.message.content = "   \n\t  "
        mock_client = Mock()
        mock_client.chat.return_value = whitespace_response
        mock_get_client.return_value = mock_client

        with self.assertRaises(Exception) as ctx:
            _call_ollama("llama3", "test prompt", None, 0, 2)
        self.assertIn("empty response", str(ctx.exception).lower())


class TestCallOpenAI(unittest.TestCase):
    """Tests for the OpenAI provider adapter."""

    def setUp(self):
        llm_client._openai_client = None

    @patch("processing.llm_client._get_openai_client")
    def test_successful_call(self, mock_get_client):
        """Successful OpenAI call returns choices[0].message.content."""
        mock_client = create_mock_openai_client('{"topics": ["bike_lanes"]}')
        mock_get_client.return_value = mock_client

        result = _call_openai("gpt-5", "test prompt", None, 0, 3)
        self.assertEqual(result, '{"topics": ["bike_lanes"]}')

    @patch("processing.llm_client._get_openai_client")
    def test_passes_temperature_for_standard_models(self, mock_get_client):
        """Temperature is passed as a top-level kwarg for standard (non-reasoning) models."""
        mock_client = create_mock_openai_client('{"result": "ok"}')
        mock_get_client.return_value = mock_client

        _call_openai("gpt-4o", "test prompt", None, 0.5, 3)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertEqual(call_kwargs["temperature"], 0.5)
        self.assertNotIn("options", call_kwargs)

    @patch("processing.llm_client._get_openai_client")
    def test_omits_temperature_for_reasoning_models(self, mock_get_client):
        """Reasoning models (o-series, gpt-5) must not receive temperature param."""
        mock_client = create_mock_openai_client('{"result": "ok"}')
        mock_get_client.return_value = mock_client

        for model in ("gpt-5", "gpt-5-mini", "o1", "o3-mini", "o4-mini"):
            mock_client.chat.completions.create.reset_mock()
            _call_openai(model, "test prompt", None, 0, 3)
            call_kwargs = mock_client.chat.completions.create.call_args[1]
            self.assertNotIn(
                "temperature",
                call_kwargs,
                msg=f"temperature should be omitted for reasoning model '{model}'",
            )

    @patch("processing.llm_client._get_openai_client")
    def test_schema_passed_as_response_format(self, mock_get_client):
        """Schema is wrapped in the json_schema response_format structure."""
        mock_client = create_mock_openai_client('{"topics": []}')
        mock_get_client.return_value = mock_client
        schema = {"type": "object", "properties": {"topics": {"type": "array"}}}

        _call_openai("gpt-5", "test prompt", schema, 0, 3)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertIn("response_format", call_kwargs)
        rf = call_kwargs["response_format"]
        self.assertEqual(rf["type"], "json_schema")
        self.assertIn("json_schema", rf)
        self.assertEqual(rf["json_schema"]["name"], "response_schema")
        self.assertTrue(rf["json_schema"]["strict"])

    @patch("processing.llm_client._get_openai_client")
    def test_no_response_format_when_schema_is_none(self, mock_get_client):
        """No response_format in kwargs when schema is None."""
        mock_client = create_mock_openai_client("plain text response")
        mock_get_client.return_value = mock_client

        _call_openai("gpt-5", "test prompt", None, 0, 3)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        self.assertNotIn("response_format", call_kwargs)

    @patch("processing.llm_client._get_openai_client")
    @patch("time.sleep")
    @patch("builtins.print")
    def test_retry_on_failure(self, mock_print, mock_sleep, mock_get_client):
        """Failed OpenAI calls retry with exponential backoff."""
        success_mock = create_mock_openai_client('{"topics": []}')
        success_response = success_mock.chat.completions.create.return_value

        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = [
            Exception("First failure"),
            Exception("Second failure"),
            success_response,
        ]
        mock_get_client.return_value = mock_client

        result = _call_openai("gpt-5", "test prompt", None, 0, 6)
        self.assertEqual(result, '{"topics": []}')
        self.assertEqual(mock_sleep.call_count, 2)

    @patch("processing.llm_client._get_openai_client")
    @patch("time.sleep")
    @patch("builtins.print")
    def test_max_retries_raises(self, mock_print, mock_sleep, mock_get_client):
        """All OpenAI retries exhausted raises exception."""
        mock_client = Mock()
        mock_client.chat.completions.create.side_effect = Exception("Always fails")
        mock_get_client.return_value = mock_client

        with self.assertRaises(Exception) as ctx:
            _call_openai("gpt-5", "test prompt", None, 0, 3)
        self.assertIn("failed after 3 attempts", str(ctx.exception))

    @patch("processing.llm_client._get_openai_client")
    @patch("time.sleep")
    @patch("builtins.print")
    def test_empty_response_triggers_retry(
        self, mock_print, mock_sleep, mock_get_client
    ):
        """Empty OpenAI response content triggers retry."""
        mock_client = create_mock_openai_client("")
        mock_get_client.return_value = mock_client

        with self.assertRaises(Exception) as ctx:
            _call_openai("gpt-5", "test prompt", None, 0, 2)
        self.assertIn("empty response", str(ctx.exception).lower())

    @patch("processing.llm_client._get_openai_client")
    @patch("time.sleep")
    @patch("builtins.print")
    def test_refusal_treated_as_error(self, mock_print, mock_sleep, mock_get_client):
        """OpenAI content policy refusal is treated as an error and retried."""
        mock_client = Mock()
        mock_choice = Mock()
        mock_choice.message.refusal = "I cannot answer that."
        mock_choice.message.content = None
        mock_response = Mock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        with self.assertRaises(Exception) as ctx:
            _call_openai("gpt-5", "test prompt", None, 0, 2)
        self.assertIn("refused", str(ctx.exception).lower())

    @patch("processing.llm_client._get_openai_client")
    @patch("time.sleep")
    @patch("builtins.print")
    def test_api_key_error_propagated(self, mock_print, mock_sleep, mock_get_client):
        """AuthenticationError propagates after exhausting retries."""
        from openai import AuthenticationError
        import httpx

        mock_client = Mock()
        auth_error = AuthenticationError(
            "Invalid API key",
            response=httpx.Response(
                401, request=httpx.Request("POST", "https://api.openai.com")
            ),
            body=None,
        )
        mock_client.chat.completions.create.side_effect = auth_error
        mock_get_client.return_value = mock_client

        with self.assertRaises(Exception):
            _call_openai("gpt-5", "test prompt", None, 0, 2)


class TestClientLifecycle(unittest.TestCase):
    """Tests for lazy client initialization and caching."""

    def setUp(self):
        llm_client._ollama_client = None
        llm_client._openai_client = None

    def tearDown(self):
        llm_client._ollama_client = None
        llm_client._openai_client = None

    @patch("processing.llm_client.Client")
    def test_ollama_client_created_on_first_use(self, mock_client_class):
        """Ollama client is constructed exactly once and cached."""
        mock_instance = Mock()
        mock_client_class.return_value = mock_instance

        result1 = _get_ollama_client()
        result2 = _get_ollama_client()

        mock_client_class.assert_called_once()
        self.assertIs(result1, result2)

    @patch("processing.llm_client.OpenAI")
    def test_openai_client_created_on_first_use(self, mock_openai_class):
        """OpenAI client is constructed exactly once and cached."""
        mock_instance = Mock()
        mock_openai_class.return_value = mock_instance

        result1 = _get_openai_client()
        result2 = _get_openai_client()

        mock_openai_class.assert_called_once()
        self.assertIs(result1, result2)

    @patch("processing.llm_client.Client")
    def test_ollama_client_timeout_set(self, mock_client_class):
        """Ollama client is created with 360s timeout."""
        mock_client_class.return_value = Mock()
        _get_ollama_client()
        mock_client_class.assert_called_once_with(timeout=360.0)

    @patch("processing.llm_client.OpenAI")
    def test_openai_client_timeout_set(self, mock_openai_class):
        """OpenAI client is created with 120s timeout."""
        mock_openai_class.return_value = Mock()
        _get_openai_client()
        mock_openai_class.assert_called_once_with(timeout=120.0)


class TestExtractJson(unittest.TestCase):
    """Tests for _extract_json() utility function."""

    def test_clean_json_passthrough(self):
        """Clean JSON passes through unchanged."""
        result = _extract_json('{"topics": []}')
        self.assertEqual(result, '{"topics": []}')

    def test_markdown_json_block(self):
        """JSON inside ```json block is extracted."""
        result = _extract_json('```json\n{"topics": []}\n```')
        self.assertEqual(result, '{"topics": []}')

    def test_generic_markdown_block(self):
        """JSON inside generic ``` block is extracted."""
        result = _extract_json('```\n{"topics": []}\n```')
        self.assertEqual(result, '{"topics": []}')

    def test_json_with_preamble(self):
        """JSON following preamble text is extracted."""
        result = _extract_json('Here is the result: {"topics": []}')
        self.assertEqual(result, '{"topics": []}')

    def test_json_with_postamble(self):
        """JSON preceding trailing text is extracted."""
        result = _extract_json('{"topics": []} Hope this helps!')
        self.assertEqual(result, '{"topics": []}')

    def test_nested_json(self):
        """Nested JSON objects are preserved."""
        input_json = '{"outer": {"inner": "value"}}'
        result = _extract_json(input_json)
        self.assertEqual(result, input_json)


if __name__ == "__main__":
    unittest.main()
