"""Anthropic Claude LLM Implementation

Provides integration with Anthropic's Claude models using the official SDK.
Supports Claude Opus 4, Sonnet 4, and other Claude models.
"""

import asyncio
import inspect
import json
import logging
import re
from collections.abc import AsyncGenerator
from typing import Any, TypeVar

from pydantic import BaseModel

from app.core.config import get_settings
from app.domain.exceptions.base import ConfigurationException
from app.domain.external.llm import LLM
from app.domain.models.structured_output import (
    StructuredRefusalError,
    StructuredSchemaValidationError,
    StructuredTruncationError,
)
from app.domain.services.agents.error_handler import TokenLimitExceededError
from app.domain.services.agents.token_manager import TokenManager
from app.domain.services.agents.usage_context import get_usage_context
from app.infrastructure.external.key_pool import (
    APIKeyConfig,
    APIKeyPool,
    APIKeysExhaustedError,
    RotationStrategy,
)
from app.infrastructure.external.llm.factory import LLMProviderRegistry

T = TypeVar("T", bound=BaseModel)

logger = logging.getLogger(__name__)

# Check if anthropic is installed
try:
    import anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic package not installed. Run: pip install anthropic")


@LLMProviderRegistry.register("anthropic")
class AnthropicLLM(LLM):
    """Anthropic Claude LLM implementation.

    Uses the official Anthropic Python SDK for Claude API access.
    Supports tool use, structured outputs, and streaming.
    """

    def __init__(
        self,
        api_key: str | None = None,
        fallback_api_keys: list[str] | None = None,
        redis_client=None,
        model_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ):
        """Initialize Anthropic LLM with multi-key failover support.

        Args:
            api_key: Primary Anthropic API key (defaults to settings)
            fallback_api_keys: Optional fallback keys (up to 2 fallbacks = 3 total)
            redis_client: Redis client for distributed key coordination
            model_name: Model name (defaults to settings)
            temperature: Sampling temperature (defaults to settings)
            max_tokens: Maximum tokens in response (defaults to settings)
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

        settings = get_settings()

        # Build key configs (primary + fallbacks)
        primary_key = api_key or settings.anthropic_api_key
        if not primary_key:
            raise ConfigurationException("Anthropic API key is required")

        all_keys = [primary_key]
        if fallback_api_keys:
            all_keys.extend(fallback_api_keys)

        key_configs = [APIKeyConfig(key=k, priority=i) for i, k in enumerate(all_keys) if k and k.strip()]

        # FAILOVER strategy to preserve prompt caching benefits
        # Cache is tied to API key - switching keys loses cache (~90% cost increase)
        # FAILOVER keeps using primary key until exhausted, maximizing cache hits
        self._key_pool = APIKeyPool(
            provider="anthropic",
            keys=key_configs,
            redis_client=redis_client,
            strategy=RotationStrategy.FAILOVER,  # Cache-aware strategy
        )

        self._max_retries = len(key_configs)
        self._model_name = model_name or settings.anthropic_model_name
        self._temperature = temperature if temperature is not None else settings.temperature
        self._max_tokens = max_tokens if max_tokens is not None else settings.max_tokens
        self._last_stream_metadata: dict[str, Any] | None = None

        # Client will be created with active key on-demand
        self.client: Any = None

        logger.info(
            f"Initialized Anthropic LLM with {len(key_configs)} API key(s) "
            f"using FAILOVER strategy (cache-aware), model: {self._model_name}"
        )

    async def get_api_key(self) -> str | None:
        """Get currently active API key from pool.

        Uses wait-for-recovery (MCP Rotator pattern): if all keys are in cooldown,
        waits up to 120s for the soonest-recovering key instead of failing immediately.
        """
        return await self._key_pool.get_healthy_key_or_wait(max_wait_seconds=120.0)

    async def _get_client(self) -> Any:
        """Get Anthropic client with current active key."""
        key = await self.get_api_key()
        if not key:
            raise APIKeysExhaustedError("Anthropic", len(self._key_pool.keys))

        # Track the key used for this request (for record_success accuracy)
        self._last_used_key = key
        # Create new client with active key
        return anthropic.AsyncAnthropic(api_key=key)

    def _parse_anthropic_rate_limit(self, error: Exception) -> int:
        """Parse Anthropic rate limit error for TTL.

        Anthropic includes anthropic-ratelimit-tokens-reset header.

        Args:
            error: Exception from Anthropic SDK

        Returns:
            TTL in seconds (default: 60)
        """
        # Try to extract reset time from error message
        error_str = str(error)
        if "retry after" in error_str.lower():
            try:
                # Extract seconds from error message
                match = re.search(r"retry after (\d+)", error_str, re.IGNORECASE)
                if match:
                    return int(match.group(1))
            except ValueError:
                pass

        return 60  # Default: 1 minute TTL

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

    def start_health_probe(self, interval_seconds: float = 300.0) -> None:
        """Start periodic API key health probing via the key pool."""
        if hasattr(self, "_key_pool"):
            self._key_pool.start_health_probe(interval_seconds=interval_seconds)

    def stop_health_probe(self) -> None:
        """Stop API key health probing."""
        if hasattr(self, "_key_pool"):
            self._key_pool.stop_health_probe()

    async def _record_usage(self, response: Any) -> None:
        """Record usage from Anthropic response if usage context is set.

        Args:
            response: Anthropic API response containing usage info
        """
        ctx = get_usage_context()
        if not ctx:
            return

        try:
            # Extract usage from Anthropic response
            usage = getattr(response, "usage", None)
            if not usage:
                return

            input_tokens = getattr(usage, "input_tokens", 0)
            output_tokens = getattr(usage, "output_tokens", 0)
            cache_read_tokens = getattr(usage, "cache_read_input_tokens", 0)
            cache_creation_tokens = getattr(usage, "cache_creation_input_tokens", 0)

            # Total cached tokens = read from cache + created for cache
            cached_tokens = cache_read_tokens + cache_creation_tokens

            # Lazy import to avoid circular dependency
            from app.application.services.usage_service import get_usage_service

            usage_service = get_usage_service()

            await usage_service.record_llm_usage(
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                model=ctx.model_override or self._model_name,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                cached_tokens=cached_tokens,
                provider_usage_raw={
                    "input_tokens": input_tokens,
                    "output_tokens": output_tokens,
                    "cache_read_input_tokens": cache_read_tokens,
                    "cache_creation_input_tokens": cache_creation_tokens,
                    "total_tokens": input_tokens + output_tokens,
                    "estimated": False,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to record usage: {e}")

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

            from app.application.services.usage_service import get_usage_service

            usage_service = get_usage_service()

            await usage_service.record_llm_usage(
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                model=ctx.model_override or self._model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=0,
                provider_usage_raw={
                    "input_tokens": prompt_tokens,
                    "output_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "estimated": True,
                },
            )
        except Exception as e:
            logger.warning(f"Failed to record streaming usage: {e}")

    def _convert_openai_tools_to_anthropic(
        self, tools: list[dict[str, Any]], enable_caching: bool = True
    ) -> list[dict[str, Any]]:
        """Convert OpenAI tool format to Anthropic format with cache optimization.

        When caching is enabled, marks the last tool definition with cache_control
        to create a cache boundary. Since tools are static across calls, this enables
        Anthropic to cache the tool definitions + system prompt together for 45-80%
        cost reduction (ArXiv 2601.06007).

        Args:
            tools: List of tools in OpenAI format
            enable_caching: Whether to add cache control markers

        Returns:
            List of tools in Anthropic format
        """
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append(
                    {
                        "name": func.get("name"),
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {"type": "object", "properties": {}}),
                    }
                )

        # Mark last tool with cache_control for optimal prefix caching
        if enable_caching and anthropic_tools:
            anthropic_tools[-1]["cache_control"] = {"type": "ephemeral"}

        return anthropic_tools

    def _convert_openai_messages_to_anthropic(
        self, messages: list[dict[str, Any]]
    ) -> tuple[str | None, list[dict[str, Any]]]:
        """Convert OpenAI message format to Anthropic format.

        Args:
            messages: List of messages in OpenAI format

        Returns:
            Tuple of (system_prompt, anthropic_messages)
        """
        system_prompt = None
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                # Anthropic uses a separate system parameter
                system_prompt = content
                continue

            if role == "assistant":
                # Handle assistant messages with tool calls
                if msg.get("tool_calls"):
                    tool_use_blocks = []
                    for tc in msg.get("tool_calls", []):
                        func = tc.get("function", {})
                        args = func.get("arguments", "{}")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}

                        tool_use_blocks.append(
                            {"type": "tool_use", "id": tc.get("id", ""), "name": func.get("name", ""), "input": args}
                        )

                    # Include text content if present
                    if content:
                        anthropic_messages.append(
                            {"role": "assistant", "content": [{"type": "text", "text": content}, *tool_use_blocks]}
                        )
                    else:
                        anthropic_messages.append({"role": "assistant", "content": tool_use_blocks})
                else:
                    anthropic_messages.append({"role": "assistant", "content": content or ""})

            elif role == "tool":
                # Convert tool response to Anthropic format
                anthropic_messages.append(
                    {
                        "role": "user",
                        "content": [
                            {"type": "tool_result", "tool_use_id": msg.get("tool_call_id", ""), "content": content}
                        ],
                    }
                )

            elif role == "user":
                anthropic_messages.append({"role": "user", "content": content})

        return system_prompt, anthropic_messages

    def _convert_anthropic_response_to_openai(self, response: Any) -> dict[str, Any]:
        """Convert Anthropic response to OpenAI format.

        Args:
            response: Anthropic API response

        Returns:
            Response in OpenAI format
        """
        result = {"role": "assistant", "content": None, "tool_calls": None}

        text_content = []
        tool_calls = []

        if not response.content:
            # Handle empty/None content from Anthropic
            logger.warning("Anthropic response has empty content")
            return result

        for block in response.content:
            if block.type == "text":
                text_content.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append(
                    {
                        "id": block.id,
                        "type": "function",
                        "function": {"name": block.name, "arguments": json.dumps(block.input)},
                    }
                )

        if text_content:
            result["content"] = "\n".join(text_content)

        if tool_calls:
            result["tool_calls"] = tool_calls

        # Check stop_reason for truncation detection
        stop_reason = getattr(response, "stop_reason", None)
        if stop_reason == "max_tokens":
            logger.warning("Anthropic response truncated (stop_reason=max_tokens)")
            result["_finish_reason"] = "length"
        elif stop_reason:
            # Normalize: "end_turn" → "stop", "tool_use" → "tool_calls"
            result["_finish_reason"] = stop_reason

        return result

    def _prepare_system_with_caching(self, system_prompt: str, enable_caching: bool) -> Any:
        """Prepare system prompt with cache control for Anthropic.

        When caching is enabled, marks the system prompt for ephemeral caching
        which can reduce token costs by up to 90% on repeated requests.

        Args:
            system_prompt: The system prompt text
            enable_caching: Whether to enable prompt caching

        Returns:
            System prompt with cache control markers if caching enabled
        """
        if not enable_caching or not system_prompt:
            return system_prompt

        # Use Anthropic's cache control format for ephemeral caching
        # This marks the system prompt as cacheable for subsequent requests
        return [{"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral"}}]

    async def ask(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        tool_choice: str | None = None,
        enable_caching: bool = True,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        _attempt: int = 0,
    ) -> dict[str, Any]:
        """Send chat request to Anthropic API with automatic key rotation.

        Args:
            messages: List of messages in OpenAI format
            tools: Optional list of tools in OpenAI format
            response_format: Optional response format (limited support)
            tool_choice: Optional tool choice configuration
            enable_caching: Whether to enable prompt caching (up to 90% token savings)
            model: Optional model override (unified adaptive routing)
            temperature: Optional temperature override (unified adaptive routing)
            max_tokens: Optional max_tokens override (unified adaptive routing)
            _attempt: Internal retry counter

        Returns:
            Response message in OpenAI format
        """
        # Check retry limit to prevent infinite recursion
        if _attempt >= self._max_retries:
            raise APIKeysExhaustedError("Anthropic", len(self._key_pool.keys))

        # Get healthy key and create client
        try:
            client = await self._get_client()
        except APIKeysExhaustedError:
            raise

        try:
            # Convert messages to Anthropic format
            system_prompt, anthropic_messages = self._convert_openai_messages_to_anthropic(messages)

            # Build request parameters
            # ORDER MATTERS FOR CACHE OPTIMIZATION:
            # 1. system prompt (cached via _prepare_system_with_caching)
            # 2. tools (cached via cache_control on last tool)
            # 3. messages (dynamic, never cached)
            # This order maximizes Anthropic's prefix cache hit rate (ArXiv 2601.06007)
            effective_model = model or self._model_name
            effective_max_tokens = max_tokens if max_tokens is not None else self._max_tokens
            effective_temperature = temperature if temperature is not None else self._temperature

            params = {
                "model": effective_model,
                "max_tokens": effective_max_tokens,
                "messages": anthropic_messages,
            }

            # Native structured output path via output_config.format (preferred).
            if response_format and response_format.get("type") == "json_schema":
                json_schema = response_format.get("json_schema", {})
                schema_obj = json_schema.get("schema")
                if isinstance(schema_obj, dict):
                    params["output_config"] = {
                        "format": {
                            "type": "json_schema",
                            "name": json_schema.get("name", "structured_output"),
                            "schema": schema_obj,
                        }
                    }

            # Anthropic uses temperature differently - 0 to 1
            if effective_temperature is not None:
                params["temperature"] = min(1.0, max(0.0, effective_temperature))

            # Apply cache control to system prompt for token savings
            if system_prompt:
                params["system"] = self._prepare_system_with_caching(system_prompt, enable_caching)

            if tools:
                params["tools"] = self._convert_openai_tools_to_anthropic(tools, enable_caching=enable_caching)

                # Handle tool_choice
                if tool_choice == "required":
                    params["tool_choice"] = {"type": "any"}
                elif tool_choice == "none":
                    params["tool_choice"] = {"type": "none"}
                # "auto" is the default

            # Explicitly disable extended thinking to avoid reasoning_content errors
            # When thinking is enabled, all assistant messages must include thinking blocks
            params["thinking"] = {"type": "disabled"}

            response = await client.messages.create(**params)

            # Track usage if context is set
            await self._record_usage(response)

            # Record success using the key that was actually used for this request.
            try:
                _used_key = getattr(self, "_last_used_key", None)
                if _used_key:
                    self._key_pool.record_success(_used_key)
            except Exception:
                logger.debug("record_success failed", exc_info=True)

            return self._convert_anthropic_response_to_openai(response)

        except anthropic.RateLimitError as e:
            # Parse rate limit TTL and mark key exhausted
            key = await self.get_api_key()
            if key:
                ttl = self._parse_anthropic_rate_limit(e)
                await self._key_pool.mark_exhausted(key, ttl_seconds=ttl)
                logger.warning(
                    f"Anthropic rate limit hit, rotating to next key (attempt {_attempt + 1}/{self._max_retries})"
                )
                # Retry with next key
                return await self.ask(
                    messages,
                    tools,
                    response_format,
                    tool_choice,
                    enable_caching,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    _attempt=_attempt + 1,
                )
            raise

        except anthropic.AuthenticationError:
            # Invalid API key - mark as invalid and rotate
            key = await self.get_api_key()
            if key:
                await self._key_pool.mark_invalid(key)
                logger.error(
                    f"Anthropic authentication error, rotating to next key (attempt {_attempt + 1}/{self._max_retries})"
                )
                # Retry with next key
                return await self.ask(
                    messages,
                    tools,
                    response_format,
                    tool_choice,
                    enable_caching,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    _attempt=_attempt + 1,
                )
            raise

        except anthropic.BadRequestError as e:
            error_msg = str(e).lower()
            if "token" in error_msg or "context" in error_msg:
                raise TokenLimitExceededError(str(e)) from e
            raise

        except Exception as e:
            logger.error(f"Anthropic API error on attempt {_attempt + 1}: {e}")
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
        """Send chat request with strict structured output validation."""
        return await self._ask_structured_output_config(
            messages=messages,
            response_model=response_model,
            enable_caching=enable_caching,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def _ask_structured_output_config(
        self,
        *,
        messages: list[dict[str, str]],
        response_model: type[T],
        enable_caching: bool,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> T:
        schema = response_model.model_json_schema()
        response = await self.ask(
            messages=messages,
            response_format={
                "type": "json_schema",
                "json_schema": {"name": response_model.__name__, "schema": schema},
            },
            enable_caching=enable_caching,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        finish_reason = response.get("_finish_reason")
        if finish_reason == "refusal":
            raise StructuredRefusalError("Anthropic refusal for structured output")
        if finish_reason == "length":
            raise StructuredTruncationError("Anthropic structured output truncated")

        content = response.get("content")
        if not isinstance(content, str) or not content.strip():
            raise StructuredSchemaValidationError("Anthropic output_config returned empty content")

        try:
            return response_model.model_validate_json(content)
        except Exception as exc:
            raise StructuredSchemaValidationError(str(exc)) from exc

    async def ask_stream(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        tool_choice: str | None = None,
        enable_caching: bool = True,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        _attempt: int = 0,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from Anthropic API with automatic key rotation.

        Args:
            messages: List of messages
            tools: Optional tools for function calling
            response_format: Optional response format
            tool_choice: Optional tool choice
            enable_caching: Whether to use prompt caching
            _attempt: Internal retry counter

        Yields:
            Content chunks as strings
        """
        # Check retry limit
        if _attempt >= self._max_retries:
            self._last_stream_metadata = {
                "finish_reason": "error",
                "truncated": False,
                "provider": "anthropic",
                "error": "all_keys_exhausted",
            }
            raise APIKeysExhaustedError("Anthropic", len(self._key_pool.keys))

        self._last_stream_metadata = None

        # Get healthy key and create client
        try:
            client = await self._get_client()
        except APIKeysExhaustedError:
            self._last_stream_metadata = {
                "finish_reason": "error",
                "truncated": False,
                "provider": "anthropic",
                "error": "all_keys_exhausted",
            }
            raise

        # Convert messages to Anthropic format
        system_prompt, anthropic_messages = self._convert_openai_messages_to_anthropic(messages)

        effective_model = model or self._model_name
        effective_max_tokens = max_tokens if max_tokens is not None else self._max_tokens
        effective_temperature = temperature if temperature is not None else self._temperature
        params = {
            "model": effective_model,
            "max_tokens": effective_max_tokens,
            "messages": anthropic_messages,
        }

        if effective_temperature is not None:
            params["temperature"] = min(1.0, max(0.0, effective_temperature))

        # Apply cache control to system prompt for token savings (same as ask())
        if system_prompt:
            params["system"] = self._prepare_system_with_caching(system_prompt, enable_caching)

        if tools:
            params["tools"] = self._convert_openai_tools_to_anthropic(tools, enable_caching=enable_caching)

        # Explicitly disable extended thinking for streaming
        params["thinking"] = {"type": "disabled"}

        completion_parts: list[str] = []

        try:
            async with client.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    completion_parts.append(text)
                    yield text

                stop_reason = None
                final_message_getter = getattr(stream, "get_final_message", None)
                if callable(final_message_getter):
                    final_message = final_message_getter()
                    if inspect.isawaitable(final_message):
                        final_message = await final_message
                    stop_reason = getattr(final_message, "stop_reason", None)

            if completion_parts:
                await self._record_stream_usage(messages, "".join(completion_parts), tools=tools)
            else:
                await self._record_stream_usage(messages, "", tools=tools)

            normalized_finish_reason = "length" if stop_reason == "max_tokens" else (stop_reason or "stop")
            self._last_stream_metadata = {
                "finish_reason": normalized_finish_reason,
                "truncated": normalized_finish_reason == "length",
                "provider": "anthropic",
            }
            if normalized_finish_reason == "length":
                logger.warning("Anthropic streaming response truncated (stop_reason=max_tokens)")

            # Record success on the key pool for adaptive TTL learning.
            try:
                success_key = await self.get_api_key()
                if success_key:
                    self._key_pool.record_success(success_key)
            except Exception:
                logger.debug("record_success failed", exc_info=True)

            return  # Success

        except anthropic.BadRequestError as e:
            self._last_stream_metadata = {
                "finish_reason": "error",
                "truncated": False,
                "provider": "anthropic",
                "error": "bad_request",
            }
            error_msg = str(e).lower()
            if "token" in error_msg or "context" in error_msg:
                raise TokenLimitExceededError(str(e)) from e
            raise

        except anthropic.RateLimitError as e:
            self._last_stream_metadata = {
                "finish_reason": "error",
                "truncated": False,
                "provider": "anthropic",
                "error": "rate_limit",
            }
            # Parse rate limit TTL and mark key exhausted
            key = await self.get_api_key()
            if key:
                ttl = self._parse_anthropic_rate_limit(e)
                await self._key_pool.mark_exhausted(key, ttl_seconds=ttl)
                logger.warning(
                    f"Anthropic stream rate limit hit, rotating to next key (attempt {_attempt + 1}/{self._max_retries})"
                )
                # Retry with next key (recursively yield from new attempt)
                async for chunk in self.ask_stream(
                    messages,
                    tools,
                    response_format,
                    tool_choice,
                    enable_caching,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    _attempt=_attempt + 1,
                ):
                    yield chunk
                return
            raise

        except anthropic.AuthenticationError:
            self._last_stream_metadata = {
                "finish_reason": "error",
                "truncated": False,
                "provider": "anthropic",
                "error": "authentication_error",
            }
            # Invalid API key - mark as invalid and rotate
            key = await self.get_api_key()
            if key:
                await self._key_pool.mark_invalid(key)
                logger.error(
                    f"Anthropic stream authentication error, rotating to next key (attempt {_attempt + 1}/{self._max_retries})"
                )
                # Retry with next key (recursively yield from new attempt)
                async for chunk in self.ask_stream(
                    messages,
                    tools,
                    response_format,
                    tool_choice,
                    enable_caching,
                    model=model,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    _attempt=_attempt + 1,
                ):
                    yield chunk
                return
            raise

        except (anthropic.APIConnectionError, anthropic.InternalServerError) as e:
            self._last_stream_metadata = {
                "finish_reason": "error",
                "truncated": False,
                "provider": "anthropic",
                "error": type(e).__name__,
            }
            logger.error(f"Anthropic stream error on attempt {_attempt + 1}: {e}")
            raise


# Test function
if __name__ == "__main__":
    import asyncio
    import os

    async def test():
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return

        llm = AnthropicLLM(api_key=api_key)

        await llm.ask([{"role": "user", "content": "What is 2 + 2?"}])

    asyncio.run(test())
