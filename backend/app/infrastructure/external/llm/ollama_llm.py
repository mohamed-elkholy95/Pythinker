"""Ollama Local LLM Implementation

Provides integration with Ollama for running local LLMs.
Supports all Ollama-compatible models including Llama, Mistral, Phi, etc.
"""

import asyncio
import contextlib
import json
import logging
from collections.abc import AsyncGenerator
from typing import Any, TypeVar

import httpx
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.retry import RetryConfig, calculate_delay, llm_retry
from app.domain.exceptions.base import LLMException
from app.domain.external.llm import LLM
from app.domain.services.agents.error_handler import TokenLimitExceededError
from app.domain.services.agents.token_manager import TokenManager
from app.domain.services.agents.usage_context import get_usage_context
from app.infrastructure.external.http_pool import HTTPClientPool
from app.infrastructure.external.llm.factory import LLMProviderRegistry

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)


@LLMProviderRegistry.register("ollama")
class OllamaLLM(LLM):
    """Ollama local LLM implementation.

    Uses Ollama's REST API for local model inference.
    Supports tool use through text-based prompting.
    """

    def __init__(
        self,
        base_url: str | None = None,
        model_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """Initialize Ollama LLM.

        Args:
            base_url: Ollama server URL (defaults to localhost:11434)
            model_name: Model name (defaults to llama3.2)
            temperature: Sampling temperature (defaults to settings)
            max_tokens: Maximum tokens in response (defaults to settings)
        """
        settings = get_settings()

        self._base_url = (base_url or getattr(settings, "ollama_base_url", None) or "http://localhost:11434").rstrip(
            "/"
        )

        self._model_name = model_name or getattr(settings, "ollama_model", None) or "llama3.2"

        self._temperature = temperature if temperature is not None else settings.temperature
        self._max_tokens = max_tokens if max_tokens is not None else settings.max_tokens
        self._last_stream_metadata: dict[str, Any] | None = None

        self._api_url = f"{self._base_url}/api"

        logger.info(f"Initialized Ollama LLM with model: {self._model_name} at {self._base_url}")

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def last_stream_metadata(self) -> dict[str, Any] | None:
        return self._last_stream_metadata

    def _tools_to_text(self, tools: list[dict[str, Any]]) -> str:
        """Convert OpenAI tools format to text description.

        Args:
            tools: List of tools in OpenAI format

        Returns:
            Text description of available tools
        """
        if not tools:
            return ""

        tool_descriptions = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                name = func.get("name", "unknown")
                desc = func.get("description", "No description")
                params = func.get("parameters", {})

                # Format parameters
                param_str = ""
                if params.get("properties"):
                    param_parts = []
                    required = params.get("required", [])
                    for param_name, param_info in params["properties"].items():
                        param_type = param_info.get("type", "any")
                        param_desc = param_info.get("description", "")
                        is_required = param_name in required
                        req_marker = " (required)" if is_required else " (optional)"
                        param_parts.append(f"    - {param_name}: {param_type}{req_marker} - {param_desc}")
                    param_str = "\n" + "\n".join(param_parts)

                tool_descriptions.append(f"- **{name}**: {desc}{param_str}")

        return "\n".join(tool_descriptions)

    def _inject_tools_into_messages(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Inject tool definitions into the system prompt.

        Args:
            messages: List of messages
            tools: List of tools

        Returns:
            Modified messages with tool instructions
        """
        if not tools:
            return messages

        tools_text = self._tools_to_text(tools)
        tool_instruction = f"""
You have access to the following tools:

{tools_text}

To use a tool, respond with ONLY a JSON object in this format:
```json
{{"tool_call": {{"name": "TOOL_NAME", "arguments": {{"param1": "value1"}}}}}}
```

Do not include any text before or after the JSON when calling a tool.
"""

        # Make a copy and inject into system message
        new_messages = []
        system_found = False

        for msg in messages:
            msg_copy = dict(msg)
            if msg_copy.get("role") == "system":
                msg_copy["content"] = msg_copy.get("content", "") + "\n\n" + tool_instruction
                system_found = True
            new_messages.append(msg_copy)

        if not system_found:
            new_messages.insert(0, {"role": "system", "content": tool_instruction})

        return new_messages

    def _convert_messages_for_ollama(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert messages to Ollama format.

        Handles tool calls and tool responses.

        Args:
            messages: List of messages in OpenAI format

        Returns:
            List of messages in Ollama format
        """
        converted = []

        for msg in messages:
            msg_copy = dict(msg)
            role = msg_copy.get("role", "")

            # Convert assistant messages with tool_calls to plain text
            if role == "assistant" and msg_copy.get("tool_calls"):
                tool_calls = msg_copy.pop("tool_calls", [])
                content = msg_copy.get("content") or ""

                for tc in tool_calls:
                    func = tc.get("function", {})
                    args = func.get("arguments", "{}")
                    if isinstance(args, str):
                        try:
                            args = json.loads(args)
                        except json.JSONDecodeError:
                            args = {}

                    tool_json = {"tool_call": {"name": func.get("name"), "arguments": args}}
                    content += f"\n```json\n{json.dumps(tool_json, indent=2)}\n```"

                msg_copy["content"] = content.strip() or "I'll use a tool."
                msg_copy["role"] = "assistant"

            # Convert tool response messages to user messages
            elif role == "tool":
                tool_content = msg_copy.get("content", "")
                tool_name = msg_copy.get("name", "tool")
                msg_copy = {"role": "user", "content": f"[Tool Result from {tool_name}]:\n{tool_content}"}

            # Ensure content is always a string
            if msg_copy.get("content") is None:
                msg_copy["content"] = ""

            converted.append(msg_copy)

        return converted

    def _parse_tool_call_from_text(self, content: str) -> dict[str, Any] | None:
        """Parse tool call from text response.

        Args:
            content: Response text

        Returns:
            Parsed tool call in OpenAI format or None
        """
        if not content:
            return None

        import re
        import uuid

        patterns = [
            r'```json\s*(\{.*?"tool_call".*?\})\s*```',
            r'```\s*(\{.*?"tool_call".*?\})\s*```',
            r'(\{[^{}]*"tool_call"[^{}]*\{[^{}]*\}[^{}]*\})',
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    data = json.loads(match)
                    if "tool_call" in data:
                        tc = data["tool_call"]
                        return {
                            "role": "assistant",
                            "content": None,
                            "tool_calls": [
                                {
                                    "id": f"call_{uuid.uuid4().hex[:8]}",
                                    "type": "function",
                                    "function": {
                                        "name": tc.get("name"),
                                        "arguments": json.dumps(tc.get("arguments", {})),
                                    },
                                }
                            ],
                        }
                except json.JSONDecodeError:
                    continue

        return None

    @llm_retry
    async def ask(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        tool_choice: str | None = None,
        enable_caching: bool = True,
    ) -> dict[str, Any]:
        """Send chat request to Ollama API.

        Uses @llm_retry (3 attempts, 2-30s exponential backoff) for transient
        network failures (TimeoutError, ConnectionError, ConnectionResetError).
        Non-transient errors like TokenLimitExceededError propagate immediately.

        Args:
            messages: List of messages in OpenAI format
            tools: Optional list of tools (converted to text prompts)
            response_format: Optional response format
            tool_choice: Optional tool choice configuration
            enable_caching: Whether to enable caching (not used)

        Returns:
            Response message in OpenAI format
        """
        # Convert messages for Ollama
        ollama_messages = self._convert_messages_for_ollama(messages)

        # Inject tools as text instructions
        if tools:
            ollama_messages = self._inject_tools_into_messages(ollama_messages, tools)

        try:
            client = await HTTPClientPool.get_client(
                name="ollama",
                base_url=self._api_url,
                timeout=120.0,
            )
            response = await client.post(
                "/chat",
                json={
                    "model": self._model_name,
                    "messages": ollama_messages,
                    "stream": False,
                    "options": {
                        "temperature": self._temperature,
                        "num_predict": self._max_tokens,
                    },
                },
            )
            response.raise_for_status()

            data = response.json()
            content = data.get("message", {}).get("content", "")

            # Try to parse tool call from response
            if tools:
                parsed_tool_call = self._parse_tool_call_from_text(content)
                if parsed_tool_call:
                    return parsed_tool_call

            return {"role": "assistant", "content": content, "tool_calls": None}

        except httpx.HTTPStatusError as e:
            error_msg = str(e).lower()
            if "context" in error_msg or "token" in error_msg:
                raise TokenLimitExceededError(str(e)) from e
            raise

    async def ask_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        enable_caching: bool = True,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Send chat request with structured output validation.

        Uses JSON mode and Pydantic validation.

        Args:
            messages: List of messages
            response_model: Pydantic model class for response validation
            tools: Optional additional tools
            tool_choice: Optional tool choice
            enable_caching: Whether to use caching

        Returns:
            Validated Pydantic model instance
        """
        schema = response_model.model_json_schema()

        # Add instruction to return JSON
        schema_instruction = {
            "role": "system",
            "content": f"""You must respond with valid JSON matching this schema:
{json.dumps(schema, indent=2)}

Respond ONLY with the JSON object, no other text.""",
        }

        enhanced_messages = [schema_instruction, *list(messages)]

        max_retries = 3
        for attempt in range(max_retries + 1):
            try:
                response = await self.ask(messages=enhanced_messages, enable_caching=enable_caching)

                content = response.get("content", "")

                # Try to extract JSON from response
                import re

                json_match = re.search(r"\{[\s\S]*\}", content)
                if json_match:
                    parsed = json.loads(json_match.group())
                    return response_model.model_validate(parsed)

                raise LLMException(f"No valid JSON found in response: {content[:100]}")

            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error on attempt {attempt + 1}: {e}")
                if attempt == max_retries:
                    raise LLMException(f"Failed to parse JSON response: {e}") from e

        raise LLMException("Failed to get structured response after all retries")

    async def _stream_ollama_response(
        self,
        ollama_messages: list[dict[str, Any]],
        metadata: dict[str, Any],
    ) -> AsyncGenerator[str, None]:
        """Stream Ollama chat response. Updates metadata with usage_counts and finish_reason."""
        managed_client = await HTTPClientPool.get_client(
            name="ollama-stream",
            base_url=self._api_url,
            timeout=120.0,
        )
        async with managed_client.client.stream(
            "POST",
            "/chat",
            json={
                "model": self._model_name,
                "messages": ollama_messages,
                "stream": True,
                "options": {
                    "temperature": self._temperature,
                    "num_predict": self._max_tokens,
                },
            },
        ) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if line:
                    try:
                        data = json.loads(line)
                        if data.get("done") is True:
                            metadata["finish_reason"] = data.get("done_reason") or metadata.get("finish_reason")
                        prompt_eval = data.get("prompt_eval_count")
                        eval_count = data.get("eval_count")
                        if prompt_eval is not None or eval_count is not None:
                            metadata["usage_counts"] = {
                                "prompt_tokens": prompt_eval or 0,
                                "completion_tokens": eval_count or 0,
                            }
                        if data.get("message", {}).get("content"):
                            yield data["message"]["content"]
                    except json.JSONDecodeError:
                        continue

    # Transient exceptions for stream retry (same as llm_retry)
    _STREAM_RETRY_EXCEPTIONS = (
        TimeoutError,
        ConnectionError,
        ConnectionResetError,
        ConnectionRefusedError,
        BrokenPipeError,
        OSError,
    )

    async def ask_stream(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        tool_choice: str | None = None,
        enable_caching: bool = True,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from Ollama API.

        Uses inline retry (3 attempts, 2-30s backoff) for transient connection
        failures on stream establishment. Non-transient errors propagate immediately.

        Args:
            messages: List of messages
            tools: Optional tools
            response_format: Optional response format
            tool_choice: Optional tool choice
            enable_caching: Whether to use caching

        Yields:
            Content chunks as strings
        """
        self._last_stream_metadata = None

        # Convert messages for Ollama
        ollama_messages = self._convert_messages_for_ollama(messages)

        if tools:
            ollama_messages = self._inject_tools_into_messages(ollama_messages, tools)

        completion_parts: list[str] = []
        usage_counts: dict[str, int] | None = None
        finish_reason: str | None = None
        stream_retry_config = RetryConfig(
            max_attempts=3,
            base_delay=2.0,
            max_delay=30.0,
            exponential_base=2.0,
            jitter=True,
        )

        metadata: dict[str, Any] = {"usage_counts": None, "finish_reason": None}
        try:
            for attempt in range(1, stream_retry_config.max_attempts + 1):
                try:
                    async for content in self._stream_ollama_response(ollama_messages, metadata):
                        completion_parts.append(content)
                        yield content

                    usage_counts = metadata["usage_counts"]
                    finish_reason = metadata["finish_reason"]

                    # Stream completed successfully - record usage and set metadata
                    if usage_counts:
                        await self._record_usage_counts(
                            prompt_tokens=usage_counts["prompt_tokens"],
                            completion_tokens=usage_counts["completion_tokens"],
                            cached_tokens=0,
                        )
                    else:
                        await self._record_stream_usage(messages, "".join(completion_parts), tools=tools)

                    normalized_finish_reason = finish_reason or "stop"
                    if normalized_finish_reason in {"max_tokens", "length"}:
                        normalized_finish_reason = "length"
                    self._last_stream_metadata = {
                        "finish_reason": normalized_finish_reason,
                        "truncated": normalized_finish_reason == "length",
                        "provider": "ollama",
                    }
                    if normalized_finish_reason == "length":
                        logger.warning("Ollama streaming response truncated (done_reason indicates length)")
                    break  # Success - exit retry loop

                except self._STREAM_RETRY_EXCEPTIONS as e:
                    if attempt >= stream_retry_config.max_attempts:
                        logger.error(
                            "Ollama stream failed after %d attempts: %s",
                            attempt,
                            e,
                        )
                        raise
                    delay = calculate_delay(attempt, stream_retry_config)
                    logger.warning(
                        "Ollama stream attempt %d/%d failed, retrying in %.2fs: %s",
                        attempt,
                        stream_retry_config.max_attempts,
                        delay,
                        e,
                    )
                    await asyncio.sleep(delay)
                except httpx.HTTPStatusError:
                    raise  # Do not retry HTTP status errors
        except httpx.HTTPStatusError as e:
            self._last_stream_metadata = {
                "finish_reason": "error",
                "truncated": False,
                "provider": "ollama",
                "error": "http_error",
            }
            error_msg = str(e).lower()
            if "context" in error_msg or "token" in error_msg:
                raise TokenLimitExceededError(str(e)) from e
            raise

    async def _record_usage_counts(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        model_override: str | None = None,
    ) -> None:
        """Record usage from explicit token counts."""
        ctx = get_usage_context()
        if not ctx:
            return

        try:
            from app.application.services.usage_service import get_usage_service

            usage_service = get_usage_service()
            model_name = model_override or ctx.model_override or self._model_name
            await usage_service.record_llm_usage(
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                model=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
            )
        except Exception as e:
            logger.warning(f"Failed to record usage counts: {e}")

    async def _record_stream_usage(
        self,
        messages: list[dict[str, Any]],
        completion_text: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        """Record usage for streaming responses using token estimation."""
        ctx = get_usage_context()
        if not ctx:
            return

        try:
            token_manager = TokenManager(ctx.model_override or self._model_name)
            prompt_tokens = token_manager.count_messages_tokens(messages)
            if tools:
                prompt_tokens += token_manager.count_tokens(json.dumps(tools))
            completion_tokens = token_manager.count_tokens(completion_text)

            await self._record_usage_counts(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=0,
            )
        except Exception as e:
            logger.warning(f"Failed to record streaming usage: {e}")


# Test function
if __name__ == "__main__":
    import asyncio

    async def test():
        llm = OllamaLLM()

        with contextlib.suppress(Exception):
            await llm.ask([{"role": "user", "content": "What is 2 + 2? Answer briefly."}])

    asyncio.run(test())
