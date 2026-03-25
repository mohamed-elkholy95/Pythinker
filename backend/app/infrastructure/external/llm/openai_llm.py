import asyncio
import contextlib
import json
import logging
import re
import time
import uuid
from collections.abc import AsyncGenerator
from typing import Any, ClassVar, TypeVar

import httpx
from openai import NOT_GIVEN, AsyncOpenAI, RateLimitError
from pydantic import BaseModel, ValidationError

from app.core.config import get_settings
from app.core.retry import RetryConfig, calculate_delay
from app.domain.exceptions.base import ConfigurationException, LLMException
from app.domain.external.llm import LLM
from app.domain.external.llm_capabilities import get_capabilities
from app.domain.models.structured_output import (
    StructuredContentFilterError,
    StructuredRefusalError,
    StructuredSchemaValidationError,
    StructuredTruncationError,
)
from app.domain.services.agents.error_handler import TokenLimitExceededError
from app.domain.services.agents.prompt_cache_manager import get_prompt_cache_manager
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

# Sentinel value to distinguish "not provided" from "explicitly None"
_NOT_PROVIDED = object()

logger = logging.getLogger(__name__)


@LLMProviderRegistry.register("openai")
class OpenAILLM(LLM):
    """OpenAI-compatible LLM implementation with multi-key failover support.

    Supports OpenAI, OpenRouter, DeepSeek, and other OpenAI-compatible APIs.
    Uses FAILOVER strategy for automatic key rotation on rate limits (429) and auth errors (401).
    """

    _json_format_warned: ClassVar[set[str]] = set()  # Track models already warned about json_object fallback

    _MESSAGE_VALIDATION_ERROR_TERMS = (
        "'1214'",
        "invalid messages",
        "message format",
        "invalid_request_error",
        "incorrect role",
        "cannot be empty",
        "parameter is illegal",
        "messages parameter is illegal",
    )
    _SLOW_TOOL_CALL_THRESHOLD_SECONDS: ClassVar[float] = 30.0
    _SLOW_TOOL_CALL_TRIP_COUNT: ClassVar[int] = 2
    _SLOW_TOOL_CALL_COOLDOWN_SECONDS: ClassVar[float] = 300.0
    _SLOW_TOOL_BREAKER_DEGRADED_MAX_TOKENS: ClassVar[int] = 1024
    _SLOW_TOOL_BREAKER_DEGRADED_TIMEOUT_SECONDS: ClassVar[float] = 60.0
    _FILE_WRITE_TOOL_NAMES: ClassVar[frozenset[str]] = frozenset({"file_write", "file_append"})

    @staticmethod
    def _has_file_write_tool(tools: list[dict[str, Any]] | None) -> bool:
        """Return True if the tool list includes file_write or file_append."""
        if not tools:
            return False
        for tool in tools:
            func = tool.get("function") or {}
            if func.get("name") in OpenAILLM._FILE_WRITE_TOOL_NAMES:
                return True
        return False

    def __init__(
        self,
        api_key: str | None | object = _NOT_PROVIDED,
        fallback_api_keys: list[str] | None = None,
        redis_client=None,
        model_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        api_base: str | None = None,
    ):
        """Initialize OpenAI-compatible LLM with multi-key failover support.

        Args:
            api_key: Primary API key (defaults to settings if not provided, raises if explicitly None)
            fallback_api_keys: Optional fallback keys (up to 2 fallbacks = 3 total)
            redis_client: Redis client for distributed key coordination
            model_name: Model name (defaults to settings)
            temperature: Sampling temperature (defaults to settings)
            max_tokens: Maximum tokens in response (defaults to settings)
            api_base: API base URL (defaults to settings)
        """
        settings = get_settings()

        # Build key configs (primary + fallbacks)
        # Use sentinel to distinguish "not provided" from "explicitly None"
        if api_key is _NOT_PROVIDED:
            # Not provided - fall back to settings
            primary_key = settings.api_key
        elif api_key is None or (isinstance(api_key, str) and not api_key.strip()):
            # Explicitly None or empty string - error
            raise ConfigurationException("OpenAI/OpenRouter API key is required")
        else:
            # Provided with value
            primary_key = api_key

        if not primary_key:
            raise ConfigurationException("OpenAI/OpenRouter API key is required")

        all_keys = [primary_key]
        if fallback_api_keys:
            all_keys.extend(fallback_api_keys)

        key_configs = [APIKeyConfig(key=k, priority=i) for i, k in enumerate(all_keys) if k and k.strip()]

        # Validate that at least one valid key exists after filtering
        if not key_configs:
            raise ConfigurationException(
                "At least one valid API key is required (all provided keys were empty/whitespace)"
            )

        # FAILOVER strategy for priority-based rotation
        # Keeps using primary key until exhausted, then rotates to fallbacks
        self._key_pool = APIKeyPool(
            provider="openai",
            keys=key_configs,
            redis_client=redis_client,
            strategy=RotationStrategy.FAILOVER,
        )

        self._max_retries = len(key_configs)
        self._model_name = model_name or settings.model_name
        self._temperature = temperature if temperature is not None else settings.temperature
        self._max_tokens = max_tokens if max_tokens is not None else settings.max_tokens
        self._api_base = api_base or settings.api_base

        # Resolve provider capability profile (replaces scattered _is_* booleans)
        from app.infrastructure.external.llm.provider_profile import get_provider_profile

        self._provider_profile = get_provider_profile(self._api_base, self._model_name)

        self._supports_stream_usage = self._detect_stream_usage_support()
        self._last_stream_metadata: dict[str, Any] | None = None
        self._slow_tool_call_streak: int = 0
        self._slow_tool_call_breaker_until: float = 0.0
        self._slow_breaker_missing_fast_model_warned: bool = False
        self._slow_breaker_invalid_fast_model_warned: bool = False

        # Slow tool-call circuit breaker settings (configurable via env)
        self._slow_tool_threshold = float(
            getattr(settings, "llm_slow_tool_threshold", self._SLOW_TOOL_CALL_THRESHOLD_SECONDS)
        )
        self._slow_tool_trip_count = int(getattr(settings, "llm_slow_tool_trip_count", self._SLOW_TOOL_CALL_TRIP_COUNT))
        self._slow_tool_cooldown = float(
            getattr(settings, "llm_slow_tool_cooldown", self._SLOW_TOOL_CALL_COOLDOWN_SECONDS)
        )
        self._slow_breaker_max_tokens = int(
            getattr(settings, "llm_slow_breaker_degraded_max_tokens", self._SLOW_TOOL_BREAKER_DEGRADED_MAX_TOKENS)
        )
        self._slow_breaker_timeout = float(
            getattr(settings, "llm_slow_breaker_degraded_timeout", self._SLOW_TOOL_BREAKER_DEGRADED_TIMEOUT_SECONDS)
        )

        # NOTE: _is_* flags kept for backward compatibility. Prefer self._provider_profile.
        # Detect if using local MLX server (doesn't support native tool calling)
        self._is_mlx_mode = self._detect_mlx_mode()

        # Detect if using ZhipuAI GLM API (z.ai / bigmodel.cn) — has strict message schema
        # GLM-5 requires: system as first message only, strict alternation, no json_object format
        self._is_glm_api = self._detect_glm_api()

        # Detect if using Kimi Code API, GLM, or similar with extended thinking enabled
        self._is_thinking_api = self._detect_thinking_api()

        # Detect if using OpenRouter API — supports native json_schema structured outputs
        self._is_openrouter = self._detect_openrouter()

        # Detect if using DeepSeek API — supports json_object, json_schema, and parallel tool calls
        self._is_deepseek = self._detect_deepseek()

        # Detect if using MiniMax API — OpenAI-compatible with reasoning support
        self._is_minimax = self._detect_minimax()

        # Initialize prompt cache manager for KV-cache optimization
        self._cache_manager = get_prompt_cache_manager(self._model_name)

        # Client will be created with active key on-demand
        self.client: AsyncOpenAI | None = None

        # Per-key client cache — avoids creating a new AsyncOpenAI instance on every call
        self._cached_client: AsyncOpenAI | None = None
        self._cached_client_key: str | None = None
        self._cached_client_base: str | None = None

        tags = []
        if self._is_glm_api:
            tags.append("[GLM API]")
        if self._is_openrouter:
            tags.append("[OpenRouter]")
        if self._is_deepseek:
            tags.append("[DeepSeek]")
        if self._is_minimax:
            tags.append("[MiniMax]")
        tag_str = " " + " ".join(tags) if tags else ""
        logger.info(
            f"Initialized OpenAI LLM with {len(key_configs)} API key(s) "
            f"using FAILOVER strategy, model: {self._model_name}{tag_str}"
        )

    async def get_api_key(self) -> str | None:
        """Get currently active API key from pool.

        Uses wait-for-recovery (MCP Rotator pattern): if all keys are in cooldown,
        waits up to 120s for the soonest-recovering key instead of failing immediately.
        """
        if not hasattr(self, "_key_pool"):
            # Instance created improperly (e.g., with __new__() bypassing __init__)
            return None
        return await self._key_pool.get_healthy_key_or_wait(max_wait_seconds=120.0)

    def _create_timeout(
        self,
        *,
        is_streaming: bool = False,
        is_tool_call: bool = False,
    ) -> httpx.Timeout:
        """Build provider-aware HTTP timeout profile.

        Timeout model follows HTTPX's connect/read/write/pool granularity.
        ``read`` is the primary guardrail for stalled providers.
        """
        settings = get_settings()
        global_timeout = max(0.0, float(getattr(settings, "llm_request_timeout", 0.0) or 0.0))

        profiles: dict[str, dict[str, float]] = {
            "default": {"connect": 10.0, "read": 300.0, "write": 30.0, "pool": 30.0},
            "openai": {"connect": 5.0, "read": 120.0, "write": 30.0, "pool": 30.0},
            "anthropic": {"connect": 5.0, "read": 180.0, "write": 30.0, "pool": 30.0},
            "glm": {"connect": 10.0, "read": 90.0, "write": 30.0, "pool": 30.0},
            "deepseek": {"connect": 5.0, "read": 180.0, "write": 30.0, "pool": 30.0},
            "ollama": {"connect": 3.0, "read": 600.0, "write": 30.0, "pool": 10.0},
        }

        provider_key = getattr(getattr(self, "_provider_profile", None), "name", "default") or "default"
        if provider_key not in profiles:
            provider_key = "default"

        cfg = dict(profiles.get(provider_key, profiles["default"]))
        if is_streaming:
            stream_read_timeout = max(30.0, float(getattr(settings, "llm_stream_read_timeout", 90.0) or 90.0))
            cfg["read"] = min(cfg["read"], stream_read_timeout)
        if is_tool_call:
            tool_read_timeout = getattr(getattr(self, "_provider_profile", None), "tool_read_timeout", 90.0) or 90.0
            cfg["read"] = min(cfg["read"], tool_read_timeout)
        if global_timeout > 0:
            cfg["read"] = min(cfg["read"], global_timeout)

        return httpx.Timeout(
            timeout=None,
            connect=cfg["connect"],
            read=cfg["read"],
            write=cfg["write"],
            pool=cfg["pool"],
        )

    def _is_slow_tool_breaker_active(self, now_monotonic: float | None = None) -> bool:
        now = now_monotonic if now_monotonic is not None else time.monotonic()
        self._refresh_slow_tool_breaker_state(now)
        return now < self._slow_tool_call_breaker_until

    def _refresh_slow_tool_breaker_state(self, now_monotonic: float) -> None:
        """Reset breaker streak once cooldown window has elapsed."""
        breaker_until = getattr(self, "_slow_tool_call_breaker_until", 0.0)
        if breaker_until > 0 and now_monotonic >= breaker_until:
            if getattr(self, "_slow_tool_call_streak", 0) > 0:
                logger.info("Slow tool-call breaker cooldown elapsed; resetting slow-call streak")
            self._slow_tool_call_streak = 0
            # Keep historical timestamp for observability; next trip will overwrite it.

    def _record_tool_call_latency(
        self,
        *,
        duration_seconds: float,
        has_tools: bool,
        fast_model: str,
        now_monotonic: float | None = None,
    ) -> None:
        """Track consecutive slow tool calls and trip fast-model breaker."""
        if not has_tools:
            return

        now = now_monotonic if now_monotonic is not None else time.monotonic()
        self._refresh_slow_tool_breaker_state(now)
        if duration_seconds >= self._slow_tool_threshold:
            self._slow_tool_call_streak += 1
            if self._slow_tool_call_streak >= self._slow_tool_trip_count:
                self._slow_tool_call_breaker_until = now + self._slow_tool_cooldown
                if fast_model:
                    logger.warning(
                        "Slow tool-call circuit breaker tripped (%d calls >= %.0fs); using fast model '%s' for %.0fs",
                        self._slow_tool_call_streak,
                        self._slow_tool_threshold,
                        fast_model,
                        self._slow_tool_cooldown,
                    )
                else:
                    logger.warning(
                        "Slow tool-call circuit breaker tripped (%d calls >= %.0fs) with FAST_MODEL unset; "
                        "cooldown active for %.0fs on primary model",
                        self._slow_tool_call_streak,
                        self._slow_tool_threshold,
                        self._slow_tool_cooldown,
                    )
            return

        if self._slow_tool_call_streak > 0:
            logger.info("Slow tool-call streak reset after %.1fs response", duration_seconds)
        self._slow_tool_call_streak = 0

    def _resolve_slow_tool_breaker_model(
        self,
        *,
        request_tools: list[dict[str, Any]] | None,
        model_override_for_attempt: str | None,
        timeout_fallback_fast_model: str,
    ) -> str | None:
        """Apply slow-tool breaker override policy for one chat request."""
        if not (self._is_slow_tool_breaker_active() and request_tools and not model_override_for_attempt):
            return model_override_for_attempt

        resolved_fast_model = (
            self._resolve_model_override(timeout_fallback_fast_model) if timeout_fallback_fast_model else ""
        )

        if resolved_fast_model and resolved_fast_model != self._model_name:
            logger.warning(
                "Slow tool-call breaker active; routing tool call to fast model '%s'",
                resolved_fast_model,
            )
            return resolved_fast_model

        if resolved_fast_model == self._model_name and timeout_fallback_fast_model:
            if not getattr(self, "_slow_breaker_invalid_fast_model_warned", False):
                logger.error(
                    "Slow tool-call circuit breaker tripped but FAST_MODEL '%s' resolves to primary model '%s'; "
                    "configure a distinct FAST_MODEL to enable automatic model switching.",
                    timeout_fallback_fast_model,
                    self._model_name,
                )
                self._slow_breaker_invalid_fast_model_warned = True
            return model_override_for_attempt

        # Breaker tripped but FAST_MODEL is not configured — use degraded mode
        # (reduced max_tokens + timeout) instead.  Log once at info level;
        # this is an expected operational state, not an error.
        if not getattr(self, "_slow_breaker_missing_fast_model_warned", False):
            logger.info(
                "Slow tool-call circuit breaker active; FAST_MODEL not configured — "
                "using degraded mode (reduced tokens/timeout) with primary model '%s'",
                self._model_name,
            )
            self._slow_breaker_missing_fast_model_warned = True
        return model_override_for_attempt

    def _resolve_distinct_fast_model(self, configured_fast_model: str) -> str:
        """Return a usable FAST_MODEL value only when it differs from primary."""
        if not configured_fast_model:
            return ""

        resolved_fast_model = self._resolve_model_override(configured_fast_model)
        if resolved_fast_model and resolved_fast_model != self._model_name:
            return resolved_fast_model

        if not getattr(self, "_slow_breaker_invalid_fast_model_warned", False):
            logger.warning(
                "FAST_MODEL '%s' resolves to primary model '%s'; model switching disabled (configure a distinct model to enable).",
                configured_fast_model,
                self._model_name,
            )
            self._slow_breaker_invalid_fast_model_warned = True
            self._slow_breaker_missing_fast_model_warned = True
        return ""

    def _should_use_slow_tool_breaker_degraded_mode(
        self,
        *,
        request_tools: list[dict[str, Any]] | None,
        model_override_for_attempt: str | None,
        timeout_fallback_fast_model: str,
        now_monotonic: float | None = None,
    ) -> bool:
        """Return whether degraded guardrails should apply for slow tool calls.

        When the slow-call breaker is active and FAST_MODEL is unavailable, reduce
        tool-call cost locally (tokens + timeout) to protect step budgets.
        """
        if not request_tools:
            return False
        if model_override_for_attempt:
            return False
        if timeout_fallback_fast_model:
            return False
        return self._is_slow_tool_breaker_active(now_monotonic=now_monotonic)

    def _cap_tool_timeout_for_slow_breaker(self, timeout_seconds: float, *, degraded_mode: bool) -> float:
        """Cap tool-call timeout while degraded breaker mode is active."""
        if timeout_seconds <= 0 or not degraded_mode:
            return timeout_seconds
        return min(timeout_seconds, self._slow_breaker_timeout)

    def _cap_tool_max_tokens_for_slow_breaker(self, max_tokens: int, *, degraded_mode: bool) -> int:
        """Cap tool-call output tokens while degraded breaker mode is active."""
        if not degraded_mode:
            return max_tokens
        return min(max_tokens, self._slow_breaker_max_tokens)

    def _resolve_hard_call_timeout(self, settings: Any) -> float:
        """Resolve per-call hard timeout, with GLM override support."""
        default_timeout = max(0.0, float(getattr(settings, "llm_hard_call_timeout", 0.0) or 0.0))
        glm_timeout = max(0.0, float(getattr(settings, "llm_glm_hard_call_timeout", 0.0) or 0.0))
        if getattr(self, "_is_glm_api", False) and glm_timeout > 0:
            return glm_timeout
        return default_timeout

    @staticmethod
    def _combine_call_timeout(*timeouts: float) -> float:
        """Return the tightest positive timeout; 0 means 'no timeout'."""
        positive_timeouts = [timeout for timeout in timeouts if timeout > 0]
        return min(positive_timeouts) if positive_timeouts else 0.0

    async def _get_client(self, *, is_streaming: bool = False, is_tool_call: bool = False) -> AsyncOpenAI:
        """Get OpenAI client with current active key."""
        # If client already set (e.g., by tests), return it
        if hasattr(self, "client") and self.client is not None:
            return self.client

        key = await self.get_api_key()
        if not key:
            key_count = len(self._key_pool.keys) if hasattr(self, "_key_pool") else 1
            raise APIKeysExhaustedError("OpenAI/OpenRouter", key_count)

        # Return cached client if key and base URL are unchanged
        if (
            self._cached_client is not None
            and self._cached_client_key == key
            and self._cached_client_base == self._api_base
        ):
            return self._cached_client

        # Detect if using Kimi Code API and add required headers
        default_headers = None
        if self._api_base and "kimi.com" in self._api_base:
            # Kimi Code API requires User-Agent from recognized coding agents
            default_headers = {
                "User-Agent": "claude-code/1.0",
                "X-Client-Name": "claude-code",
            }
            logger.debug("Using Kimi Code API headers")

        client = AsyncOpenAI(
            api_key=key,
            base_url=self._api_base,
            default_headers=default_headers,
            timeout=self._create_timeout(is_streaming=is_streaming, is_tool_call=is_tool_call),
        )
        self._cached_client = client
        self._cached_client_key = key
        self._cached_client_base = self._api_base
        return client

    def _parse_openai_rate_limit(self, error: Exception) -> int:
        """Parse OpenAI rate limit error for TTL.

        OpenAI includes x-ratelimit-reset-requests header with Unix timestamp.

        Args:
            error: Exception from OpenAI SDK

        Returns:
            TTL in seconds (default: 60)
        """
        # Try to extract reset time from error response headers
        if hasattr(error, "response") and error.response is not None:
            headers = getattr(error.response, "headers", None)
            if headers:
                # OpenAI uses x-ratelimit-reset-requests (Unix timestamp)
                reset_header = headers.get("x-ratelimit-reset-requests") or headers.get("X-RateLimit-Reset-Requests")
                if reset_header:
                    try:
                        import time

                        reset_time = float(reset_header)
                        return max(1, int(reset_time - time.time()))
                    except (ValueError, TypeError):
                        pass

        # Fallback: try to extract from error message
        error_str = str(error)
        if "retry after" in error_str.lower():
            try:
                match = re.search(r"retry after (\d+)", error_str, re.IGNORECASE)
                if match:
                    return int(match.group(1))
            except ValueError:
                pass

        return 60  # Default: 1 minute TTL

    def _detect_stream_usage_support(self) -> bool:
        """Detect whether streaming usage metadata is supported by the API base."""
        base = (self._api_base or "").lower()
        return "openai.com" in base

    def _detect_mlx_mode(self) -> bool:
        """Detect if using local MLX server that needs text-based tool handling."""
        # Check model name for MLX community models
        if "mlx-community" in self._model_name.lower():
            return True
        # Check API base for local servers
        if self._api_base:
            local_indicators = ["localhost", "127.0.0.1", "host.docker.internal", ":8081"]
            if any(indicator in self._api_base.lower() for indicator in local_indicators):
                return True
        return False

    def _detect_thinking_api(self) -> bool:
        """Detect if using an API with extended thinking that requires reasoning_content handling.

        APIs like Kimi Code API and Z.AI GLM enable extended thinking by default.
        When replaying messages, reasoning_content must be preserved or stripped.
        Disabling thinking reduces latency significantly for agentic tool-calling flows.
        """
        if not self._api_base:
            return False

        base = self._api_base.lower()

        # Kimi Code API has extended thinking enabled for Claude models
        if "kimi.com" in base or "kimi.ai" in base:
            return True

        # Z.AI GLM-5/4.7 APIs have thinking enabled by default.
        # Controlled by GLM_DISABLE_THINKING env var (default: true).
        settings = get_settings()
        if getattr(settings, "glm_disable_thinking", True) and getattr(self, "_is_glm_api", False):
            return True

        # Check for Claude models that might have thinking enabled
        # Claude models through third-party APIs may have thinking enabled
        # Be conservative and enable thinking handling for all Claude models
        # through non-Anthropic endpoints
        model_lower = self._model_name.lower()
        return "claude" in model_lower and "anthropic.com" not in base

    def _detect_glm_api(self) -> bool:
        """Detect if using ZhipuAI GLM API (z.ai or bigmodel.cn).

        GLM APIs (e.g. GLM-4, GLM-5) have additional constraints vs standard OpenAI:
        - system role MUST be the very first message (error 1214 otherwise)
        - Does NOT support json_object response format
        - Streaming tool call arguments may have malformed/truncated JSON
        - No parallel tool calls support

        Base URLs: https://api.z.ai/api/paas/v4
                   https://open.bigmodel.cn/api/paas/v4
        """
        if self._api_base:
            base = self._api_base.lower()
            if any(marker in base for marker in ("z.ai", "bigmodel.cn", "zhipuai")):
                return True

        # Also detect by model name (glm- prefix covers glm-4, glm-5, glm-z1, etc.)
        model_lower = self._model_name.lower()
        return model_lower.startswith("glm-") or "glm-z" in model_lower

    def _detect_openrouter(self) -> bool:
        """Detect if using OpenRouter API.

        OpenRouter natively supports json_schema structured outputs for most models,
        including Qwen, Llama, Mistral, etc. Adding ``provider.require_parameters: true``
        ensures OpenRouter only routes to providers that honour the requested parameters.

        Base URL: https://openrouter.ai/api/v1
        """
        if not self._api_base:
            return False
        return "openrouter" in self._api_base.lower()

    def _detect_deepseek(self) -> bool:
        """Detect if using DeepSeek API.

        DeepSeek V3.2 (deepseek-chat) supports:
        - response_format: json_object and json_schema
        - Tool / function calling (including parallel tool calls)
        - 128K context window with automatic prefix caching

        Base URL: https://api.deepseek.com
        """
        if not self._api_base:
            return False
        return "api.deepseek.com" in self._api_base.lower()

    def _detect_minimax(self) -> bool:
        """Detect if using MiniMax API.

        MiniMax M2.7 supports:
        - OpenAI-compatible chat completions at https://api.minimax.io/v1
        - Tool / function calling with parallel tool calls
        - Reasoning/thinking mode (reasoning_split parameter)
        - 1M context window

        Base URLs: https://api.minimax.io/v1 (international)
                   https://api.minimaxi.com/v1 (China)
        """
        if not self._api_base:
            return False
        base = self._api_base.lower()
        return "minimax.io" in base or "minimaxi.com" in base

    def _resolve_model_override(self, model: str | None) -> str:
        """Resolve a model override, falling back to default if incompatible with provider.

        Single-provider APIs (DeepSeek, GLM, Kimi, Ollama) only serve their own models.
        Multi-provider APIs (OpenRouter, OpenAI) can route any model name.
        When a model override targets an incompatible provider, silently fall back
        to self._model_name to prevent "Model Not Exist" errors.

        Args:
            model: Requested model override (from adaptive routing, fast_model, etc.)

        Returns:
            The effective model name to use for the API call.
        """
        if not model or model == self._model_name:
            return self._model_name

        # Multi-provider routers accept any model name
        if getattr(self, "_is_openrouter", False):
            return model

        # Single-provider APIs: only accept their own model family
        if getattr(self, "_is_deepseek", False) and not model.startswith("deepseek"):
            logger.debug("Model override '%s' incompatible with DeepSeek API, using '%s'", model, self._model_name)
            return self._model_name

        if getattr(self, "_is_glm_api", False) and not model.startswith("glm"):
            logger.debug("Model override '%s' incompatible with GLM API, using '%s'", model, self._model_name)
            return self._model_name

        if getattr(self, "_is_thinking_api", False) and "kimi" not in model:
            logger.debug("Model override '%s' incompatible with Kimi API, using '%s'", model, self._model_name)
            return self._model_name

        if getattr(self, "_is_minimax", False) and not model.lower().startswith("minimax"):
            logger.debug("Model override '%s' incompatible with MiniMax API, using '%s'", model, self._model_name)
            return self._model_name

        # For standard OpenAI API (api.openai.com), reject non-OpenAI model names
        base = (self._api_base or "").lower()
        if "api.openai.com" in base:
            openai_prefixes = ("gpt-", "o1", "o3", "o4", "chatgpt-", "ft:")
            if not model.startswith(openai_prefixes):
                logger.debug("Model override '%s' incompatible with OpenAI API, using '%s'", model, self._model_name)
                return self._model_name

        return model

    @staticmethod
    def _repair_tool_args_json(args_str: str) -> str:
        """Repair malformed or truncated JSON in tool call arguments.

        LLMs can truncate tool call argument JSON when hitting output token
        limits.  Common failure modes:
          - Missing closing braces/brackets (e.g. ``{"query": "foo"``)
          - Truncation mid-string-value (e.g. ``{"content": "# Cla``)
          - Trailing text after valid JSON (e.g. ``{"a": 1} extra``)

        The repair pipeline is **provider-agnostic** — it works for GLM,
        OpenAI, Anthropic, DeepSeek, Ollama, and any future provider.

        Args:
            args_str: Raw arguments string from tool call.

        Returns:
            Valid JSON string.  On total failure, returns ``"{}"``.
        """
        if not args_str or not args_str.strip():
            return "{}"

        stripped = args_str.strip()

        # ── Fast path: already valid JSON ────────────────────────────
        try:
            json.loads(stripped)
            return stripped
        except json.JSONDecodeError:
            pass

        # ── Stage 1: Close open string literals ──────────────────────
        # Walk the string tracking whether we're inside a JSON string.
        # If the text ends mid-string, close it so brace-balancing works.
        repaired = OpenAILLM._close_truncated_json(stripped)

        # ── Stage 2: Try parsing the closed version directly ─────────
        try:
            json.loads(repaired)
            logger.debug("Repaired truncated tool args JSON (string closure)")
            return repaired
        except json.JSONDecodeError:
            pass

        # ── Stage 3: Balance unclosed braces / brackets ──────────────
        try:
            open_braces = repaired.count("{") - repaired.count("}")
            open_brackets = repaired.count("[") - repaired.count("]")
            balanced = repaired + ("]" * max(0, open_brackets)) + ("}" * max(0, open_braces))
            json.loads(balanced)
            logger.debug(
                "Repaired truncated tool args JSON (string closure + %d brace(s), %d bracket(s))",
                max(0, open_braces),
                max(0, open_brackets),
            )
            return balanced
        except Exception:
            logger.debug("Stage 3 brace-balancing failed, trying next strategy")

        # ── Stage 4: Strip trailing garbage after valid JSON ─────────
        # Some providers append extra text after the JSON object.
        try:
            first_brace = stripped.find("{")
            if first_brace >= 0:
                depth = 0
                in_str = False
                escape = False
                end_idx = -1
                for i in range(first_brace, len(stripped)):
                    ch = stripped[i]
                    if escape:
                        escape = False
                        continue
                    if ch == "\\":
                        escape = True
                        continue
                    if ch == '"':
                        in_str = not in_str
                        continue
                    if in_str:
                        continue
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            end_idx = i
                            break
                if end_idx > 0:
                    candidate = stripped[first_brace : end_idx + 1]
                    json.loads(candidate)
                    logger.debug("Extracted valid JSON from tool args (stripped trailing text)")
                    return candidate
        except Exception:
            logger.debug("Stage 4 trailing-garbage extraction failed")

        # ── Stage 5: Last resort — return empty object ───────────────
        logger.warning(
            "Could not repair tool args JSON, using empty object. Original: %s",
            args_str[:120],
        )
        return "{}"

    @staticmethod
    def _close_truncated_json(text: str) -> str:
        """Close an open string literal at the end of truncated JSON.

        Walks the text tracking JSON string state (respecting backslash
        escapes).  If the text ends inside a string, appends a closing
        ``"``.  Also strips a trailing incomplete escape (``\\``).

        This is the key piece that makes brace-balancing reliable: once
        every string is properly closed, counting ``{`` vs ``}`` reflects
        the actual structure depth.
        """
        in_string = False
        i = 0
        length = len(text)
        while i < length:
            ch = text[i]
            if in_string:
                if ch == "\\":
                    i += 2  # skip escaped character
                    continue
                if ch == '"':
                    in_string = False
            else:
                if ch == '"':
                    in_string = True
            i += 1

        if in_string:
            # Truncated inside a string — strip trailing incomplete escape
            # then close the string.
            text = text.removesuffix("\\")
            text += '"'

        return text

    async def _record_usage(self, response: Any) -> None:
        """Record usage from OpenAI response if usage context is set.

        Args:
            response: OpenAI API response containing usage info
        """
        ctx = get_usage_context()
        if not ctx:
            return

        try:
            # Extract usage from OpenAI response
            usage = getattr(response, "usage", None)
            if not usage:
                return

            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0

            # OpenAI uses prompt_tokens_details for cached tokens
            prompt_details = getattr(usage, "prompt_tokens_details", None)
            cached_tokens = 0
            if prompt_details:
                cached_tokens = getattr(prompt_details, "cached_tokens", 0) or 0
            completion_details = getattr(usage, "completion_tokens_details", None)
            reasoning_tokens = 0
            if completion_details:
                reasoning_tokens = getattr(completion_details, "reasoning_tokens", 0) or 0

            # Lazy import to avoid circular dependency
            from app.application.services.usage_service import get_usage_service

            usage_service = get_usage_service()

            await usage_service.record_llm_usage(
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                model=ctx.model_override or self._model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
                provider_usage_raw={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": getattr(usage, "total_tokens", prompt_tokens + completion_tokens) or 0,
                    "prompt_tokens_details": {
                        "cached_tokens": cached_tokens,
                    },
                    "completion_tokens_details": {
                        "reasoning_tokens": reasoning_tokens,
                    },
                },
            )
        except Exception as e:  # Broad catch: telemetry must not crash the LLM call path
            logger.warning("Failed to record usage: %s: %s", type(e).__name__, e)

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
                provider_usage_raw={
                    "prompt_tokens": prompt_tokens,
                    "completion_tokens": completion_tokens,
                    "total_tokens": prompt_tokens + completion_tokens,
                    "prompt_tokens_details": {
                        "cached_tokens": cached_tokens,
                    },
                },
            )
        except Exception as e:  # Broad catch: telemetry must not crash the LLM call path
            logger.warning("Failed to record usage counts: %s: %s", type(e).__name__, e)

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
        except Exception as e:  # Broad catch: telemetry must not crash the LLM call path
            logger.warning("Failed to record streaming usage: %s", e)

    def _tools_to_text(self, tools: list[dict[str, Any]]) -> str:
        """Convert OpenAI tools format to text description for MLX models."""
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
        """Inject tool definitions into the system prompt for MLX mode."""
        if not tools:
            return messages

        tools_text = self._tools_to_text(tools)
        tool_instruction = f"""
<available_tools>
You have access to the following tools. You MUST use these tools to complete tasks.

## CRITICAL RULES FOR TOOL CALLING:

1. **EVERY ACTION REQUIRES A TOOL CALL** - You cannot complete ANY task without calling tools.
   - To search the web: CALL info_search_web
   - To browse a website: CALL browser_agent_* tools
   - To write a file: CALL file_write
   - To read a file: CALL file_read
   - Describing an action is NOT the same as doing it!

2. **EXACT FORMAT REQUIRED** - To call a tool, output ONLY this JSON:
```json
{{"tool_call": {{"name": "TOOL_NAME", "arguments": {{"param1": "value1", "param2": "value2"}}}}}}
```

3. **ONE TOOL CALL PER RESPONSE** - Call one tool, wait for result, then call next tool.

4. **DO NOT SKIP TOOLS** - If a step requires writing a file, you MUST call file_write.
   Simply stating "I will write the file" does NOT write the file!

## EXAMPLES:

To search the web:
```json
{{"tool_call": {{"name": "info_search_web", "arguments": {{"query": "best mechanical keyboards 2025", "date_range": "past_year"}}}}}}
```

To write a markdown report:
```json
{{"tool_call": {{"name": "file_write", "arguments": {{"path": "/home/ubuntu/report.md", "content": "# Report Title\\n\\nContent here..."}}}}}}
```

To extract data from a webpage:
```json
{{"tool_call": {{"name": "browser_agent_extract", "arguments": {{"url": "https://example.com", "data_description": "product specifications"}}}}}}
```

## AVAILABLE TOOLS:
{tools_text}
</available_tools>

**REMEMBER: Output ONLY the JSON tool_call object when using a tool. No explanation before or after.**

/no_think
"""

        # Make a copy of messages
        new_messages = []
        system_found = False

        for msg in messages:
            msg_copy = dict(msg)
            if msg_copy.get("role") == "system":
                # Append tool instructions to system message
                msg_copy["content"] = msg_copy.get("content", "") + "\n\n" + tool_instruction
                system_found = True
            new_messages.append(msg_copy)

        # If no system message, add one
        if not system_found:
            new_messages.insert(0, {"role": "system", "content": tool_instruction})

        return new_messages

    def _convert_messages_for_mlx(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert messages with tool_calls to plain text format for MLX."""
        converted = []
        for msg in messages:
            msg_copy = dict(msg)
            role = msg_copy.get("role", "")

            # Convert assistant messages with tool_calls to plain text
            if role == "assistant" and msg_copy.get("tool_calls"):
                tool_calls = msg_copy.pop("tool_calls", [])
                content = msg_copy.get("content") or ""

                # Convert tool calls to JSON text
                for tc in tool_calls:
                    func = tc.get("function", {})
                    tool_json = {
                        "tool_call": {
                            "name": func.get("name"),
                            "arguments": json.loads(func.get("arguments", "{}"))
                            if isinstance(func.get("arguments"), str)
                            else func.get("arguments", {}),
                        }
                    }
                    content += f"\n```json\n{json.dumps(tool_json, indent=2)}\n```"

                msg_copy["content"] = content.strip() or "I'll use a tool."

            # Convert tool response messages to user messages
            elif role == "tool":
                tool_content = msg_copy.get("content", "")
                tool_name = msg_copy.get("name", "tool")
                msg_copy = {"role": "user", "content": f"[Tool Result from {tool_name}]:\n{tool_content}"}

            # Ensure content is always a string (not None)
            if msg_copy.get("content") is None:
                msg_copy["content"] = ""

            converted.append(msg_copy)

        return converted

    def _parse_tool_call_from_text(
        self,
        content: str,
        available_tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        """Parse tool call from text response for MLX mode.

        After extraction, validates required parameters against the tool
        schema. Invalid tool calls (missing required params) are logged
        and rejected.
        """
        if not content:
            return None

        # Try to find JSON tool_call in the response
        # Pattern 1 & 2: Code blocks (reliable delimiters)
        patterns = [
            r'```json\s*(\{.*?"tool_call".*?\})\s*```',  # Markdown code block
            r'```\s*(\{.*?"tool_call".*?\})\s*```',  # Generic code block
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            for match in matches:
                result = self._try_parse_tool_call_json(match)
                if result and self._validate_and_log_tool_call(result, available_tools):
                    return result

        # Pattern 3: Balanced brace extraction for inline JSON (handles nested braces)
        result = self._extract_balanced_json_tool_call(content)
        if result and self._validate_and_log_tool_call(result, available_tools):
            return result

        return None

    def _validate_and_log_tool_call(
        self,
        result: dict[str, Any],
        available_tools: list[dict[str, Any]] | None,
    ) -> bool:
        """Validate an extracted tool call and log validation result.

        Returns True if valid, False if rejected.
        """
        tool_calls = result.get("tool_calls", [])
        if not tool_calls:
            return True  # No tool calls to validate

        tc = tool_calls[0]
        func = tc.get("function", {})
        tool_name = func.get("name", "")
        try:
            arguments = json.loads(func.get("arguments", "{}"))
        except (json.JSONDecodeError, TypeError):
            arguments = {}

        is_valid, error_msg = self._validate_extracted_tool_call(
            tool_name,
            arguments,
            available_tools,
        )

        if not is_valid:
            logger.warning(
                "Text-extracted tool call rejected: %s (model=%s)",
                error_msg,
                self._model_name,
            )
            return False

        return True

    def _try_parse_tool_call_json(self, text: str) -> dict[str, Any] | None:
        """Try to parse a tool_call JSON string into a tool call dict."""
        try:
            data = json.loads(text)
            if "tool_call" in data:
                tc = data["tool_call"]
                return {
                    "role": "assistant",
                    "content": "",
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
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
        return None

    def _apply_tool_arg_validation(
        self,
        result: dict[str, Any],
        tools: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Validate tool call arguments against schemas for truncation-prone providers.

        On failure: log warning and flag the tool call as having bad args so the
        agent layer can inject a synthetic error tool response.
        """
        tool_schemas: dict[str, dict[str, Any]] = {}
        for t in tools:
            func = t.get("function", {})
            if func.get("name"):
                tool_schemas[func["name"]] = func.get("parameters", {})

        for tc in result.get("tool_calls", []):
            func = tc.get("function", {})
            name = func.get("name", "")
            schema = tool_schemas.get(name)
            if not schema:
                continue
            try:
                args = json.loads(func.get("arguments", "{}"))
            except (json.JSONDecodeError, TypeError):
                tc["_validation_errors"] = ["Malformed JSON in arguments"]
                continue
            errors = self._validate_tool_args_static(args, schema)
            if errors:
                logger.warning(
                    "Tool arg validation failed for %s: %s (model=%s)",
                    name,
                    errors,
                    self._model_name,
                )
                tc["_validation_errors"] = errors
        return result

    @staticmethod
    def _validate_tool_args_static(args: dict[str, Any], schema: dict[str, Any]) -> list[str]:
        """Validate tool call arguments against JSON schema.

        Returns list of error messages (empty = valid).
        Lightweight check — only validates required fields and basic types.
        """
        required = schema.get("required", [])
        properties = schema.get("properties", {})

        errors: list[str] = [f"Missing required field: '{field}'" for field in required if field not in args]

        for field, value in args.items():
            if field in properties:
                expected_type = properties[field].get("type")
                if expected_type == "string" and not isinstance(value, str):
                    errors.append(f"Field '{field}' must be string, got {type(value).__name__}")
                elif expected_type == "boolean" and not isinstance(value, bool):
                    errors.append(f"Field '{field}' must be boolean, got {type(value).__name__}")
                elif expected_type == "integer" and not isinstance(value, int):
                    errors.append(f"Field '{field}' must be integer, got {type(value).__name__}")

        return errors

    @staticmethod
    def _validate_extracted_tool_call(
        tool_name: str,
        arguments: dict[str, Any],
        available_tools: list[dict[str, Any]] | None,
    ) -> tuple[bool, str]:
        """Validate that a text-extracted tool call has required parameters.

        Checks the extracted arguments against the tool's JSON schema to
        catch malformed calls from prose-based extraction (e.g. GLM-5's
        non-native tool calling).

        Args:
            tool_name: Name of the extracted tool
            arguments: Parsed arguments dict
            available_tools: List of tool schemas (OpenAI format)

        Returns:
            Tuple of (is_valid, error_message)
        """
        if not tool_name:
            return False, "Missing tool name in extracted call"

        if not available_tools:
            return True, ""  # No schema to validate against

        # Find matching tool schema
        tool_schema: dict[str, Any] | None = None
        for tool in available_tools:
            fn = tool.get("function", {})
            if fn.get("name") == tool_name:
                tool_schema = fn.get("parameters", {})
                break

        if tool_schema is None:
            return False, f"Unknown tool: {tool_name}"

        # Check required parameters
        required = tool_schema.get("required", [])
        missing = [p for p in required if p not in arguments]
        if missing:
            return False, f"Tool {tool_name} missing required params: {missing}"

        return True, ""

    def _extract_balanced_json_tool_call(self, content: str) -> dict[str, Any] | None:
        """Extract tool_call JSON using balanced brace matching (handles nested objects)."""
        search_start = 0
        while True:
            idx = content.find('"tool_call"', search_start)
            if idx == -1:
                break
            # Walk backwards to find opening brace
            brace_start = content.rfind("{", 0, idx)
            if brace_start == -1:
                search_start = idx + 1
                continue
            # Walk forward with brace counting
            depth = 0
            for i in range(brace_start, len(content)):
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = content[brace_start : i + 1]
                        result = self._try_parse_tool_call_json(candidate)
                        if result:
                            return result
                        break
            search_start = idx + 1
        return None

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

    def _strip_reasoning_content(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Strip reasoning_content from assistant messages to avoid thinking API errors.

        When APIs like Kimi have extended thinking enabled, they expect reasoning_content
        in all assistant messages with tool_calls. Since we don't preserve reasoning_content
        in our message history, we need to strip any existing reasoning_content fields
        to avoid validation errors.

        This is necessary because:
        1. The API returns messages with reasoning_content when thinking is enabled
        2. We store messages without reasoning_content (it's internal to the model)
        3. When replaying, the API sees messages that should have thinking but don't
        4. This causes: "thinking is enabled but reasoning_content is missing"
        """
        if not self._is_thinking_api:
            return messages

        cleaned = []
        for msg in messages:
            msg_copy = dict(msg)

            # Remove reasoning_content if present (we don't preserve it)
            msg_copy.pop("reasoning_content", None)

            # For assistant messages with tool_calls, ensure content is present
            # Some APIs expect content to be present even if empty
            if msg_copy.get("role") == "assistant" and msg_copy.get("tool_calls") and msg_copy.get("content") is None:
                msg_copy["content"] = ""

            cleaned.append(msg_copy)

        return cleaned

    def _coerce_content_to_text(self, content: Any) -> str:
        """Normalize mixed/structured content into plain text for strict providers."""
        if content is None:
            return ""

        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    text_value = item.get("text")
                    if isinstance(text_value, str):
                        parts.append(text_value)
                        continue
                    with contextlib.suppress(Exception):
                        parts.append(json.dumps(item, ensure_ascii=False, sort_keys=True))
                elif item is not None:
                    parts.append(str(item))
            return "\n".join(part for part in parts if part).strip()

        with contextlib.suppress(Exception):
            return json.dumps(content, ensure_ascii=False, default=str)
        return str(content)

    def _is_message_validation_error(self, error: Exception) -> bool:
        """Return True when provider rejected the request due to message schema."""
        error_text = str(error).lower()
        return any(term in error_text for term in self._MESSAGE_VALIDATION_ERROR_TERMS)

    def _build_validation_recovery_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Build a strict fallback payload when providers reject message schema."""
        recovered: list[dict[str, Any]] = []
        allowed_roles = {"system", "user", "assistant", "tool"}

        for msg in messages:
            role = str(msg.get("role", "user"))
            if role == "developer":
                role = "system"
            if role not in allowed_roles:
                role = "user"

            msg_copy = dict(msg)
            msg_copy["role"] = role

            if role == "assistant" and msg_copy.get("tool_calls"):
                msg_copy = self._convert_orphaned_assistant(msg_copy)

            content_text = self._coerce_content_to_text(msg_copy.get("content")).strip()

            if role == "tool":
                tool_name = str(msg_copy.get("name") or "unknown_tool")
                tool_result = content_text or "{}"
                # Use "user" role so tool results don't land adjacent to the
                # converted assistant message above — GLM error 1214 rejects
                # two consecutive "assistant" messages.
                recovered.append(
                    {
                        "role": "user",
                        "content": f"[Tool result: {tool_name}]\n{tool_result}",
                    }
                )
                continue

            if not content_text:
                if role == "system":
                    content_text = "You are a helpful assistant."
                elif role == "assistant":
                    content_text = "[No assistant content]"
                else:
                    content_text = "[No user content]"

            recovered.append({"role": role, "content": content_text})

        if not recovered:
            recovered = [{"role": "user", "content": "Please continue."}]

        if recovered[0]["role"] == "assistant":
            recovered.insert(0, {"role": "system", "content": "Continue the conversation."})

        return self._sanitize_messages(recovered)

    @staticmethod
    def _needs_proactive_sanitize(provider_profile: Any) -> bool:
        """Return True for providers known to reject non-standard message schemas.

        These providers (kimi, GLM) have strict requirements around role names and
        message structure. Pre-sanitizing their transcripts eliminates the 1-7s
        latency penalty of a failed first attempt followed by recovery retry.
        """
        return getattr(provider_profile, "strict_schema", False)

    def _sanitize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sanitize messages for strict OpenAI-compatible APIs (Zhipu GLM, OpenRouter, etc.).

        Many OpenAI-compatible APIs are stricter than OpenAI itself about message schema.
        This method ensures all messages conform to the strictest common denominator:

        1. Role normalization — 'developer' role converted to 'system' (GLM only accepts
           system/user/assistant/tool)
        2. Content is always a string (never None/null) — GLM rejects null content
        3. Non-standard fields are removed (only role, content, tool_calls, tool_call_id,
           name allowed)
        4. Tool response messages use standard 'name' field (not 'function_name')
        5. tool_calls entries have valid structure with required 'type' field
        6. Empty messages are dropped to prevent "content cannot be empty" errors
        """
        # Standard fields per role (OpenAI Chat Completions API spec)
        _standard_fields = {
            "system": {"role", "content", "name"},
            "user": {"role", "content", "name"},
            "assistant": {"role", "content", "tool_calls", "name", "refusal"},
            "tool": {"role", "content", "tool_call_id", "name"},
        }

        sanitized = []
        for msg in messages:
            msg_copy = dict(msg)
            # Deep-copy tool_calls to avoid mutating originals
            if "tool_calls" in msg_copy and isinstance(msg_copy["tool_calls"], list):
                msg_copy["tool_calls"] = [
                    {**tc, "function": dict(tc["function"])}
                    if isinstance(tc, dict) and "function" in tc
                    else dict(tc)
                    if isinstance(tc, dict)
                    else tc
                    for tc in msg_copy["tool_calls"]
                ]
            role = msg_copy.get("role", "user")

            # 1. Normalize roles for strict APIs
            # GLM and similar only accept: system, user, assistant, tool
            if role == "developer":
                msg_copy["role"] = "system"
                role = "system"

            # 2. Ensure content is always a string (never None)
            content = msg_copy.get("content")
            if content is None:
                msg_copy["content"] = ""
            elif not isinstance(content, str):
                msg_copy["content"] = self._coerce_content_to_text(content)

            # 3. Convert non-standard 'function_name' to standard 'name' for tool messages
            if role == "tool" and "function_name" in msg_copy:
                if "name" not in msg_copy:
                    msg_copy["name"] = msg_copy["function_name"]
                del msg_copy["function_name"]

            # 4. Remove non-standard fields that strict APIs reject
            allowed = _standard_fields.get(role, {"role", "content"})
            # Keep internal fields prefixed with '_' (like _finish_reason) — stripped by SDK
            extra_keys = {k for k in msg_copy if k not in allowed and not k.startswith("_")}
            for key in extra_keys:
                del msg_copy[key]

            # 5a. Ensure required fields for tool messages (GLM strict schema)
            # After field removal, tool messages MUST have name and tool_call_id
            if role == "tool":
                if not msg_copy.get("name"):
                    msg_copy["name"] = "unknown_tool"
                else:
                    msg_copy["name"] = str(msg_copy["name"])
                if not msg_copy.get("tool_call_id"):
                    msg_copy["tool_call_id"] = f"call_{uuid.uuid4().hex[:8]}"
                else:
                    msg_copy["tool_call_id"] = str(msg_copy["tool_call_id"])

            # 5b. Validate tool_calls structure if present
            if msg_copy.get("tool_calls"):
                valid_calls = []
                for tc in msg_copy["tool_calls"]:
                    if isinstance(tc, dict) and tc.get("function"):
                        # Ensure all required fields exist (GLM rejects empty type)
                        tc.setdefault("id", f"call_{uuid.uuid4().hex[:8]}")
                        tc.setdefault("type", "function")
                        func = tc["function"]
                        func.setdefault("name", "unknown")
                        if func.get("arguments") is None:
                            func["arguments"] = "{}"
                        elif not isinstance(func["arguments"], str):
                            func["arguments"] = json.dumps(func["arguments"])
                        else:
                            # Any provider can truncate tool call JSON when hitting
                            # output token limits.  Apply universal repair.
                            func["arguments"] = self._repair_tool_args_json(func["arguments"])
                        valid_calls.append(tc)
                if valid_calls:
                    msg_copy["tool_calls"] = valid_calls
                else:
                    # Remove tool_calls entirely if empty (some APIs reject null/empty)
                    msg_copy.pop("tool_calls", None)

            sanitized.append(msg_copy)

        # 6. Merge consecutive same-role messages (Zhipu GLM error 1214).
        # GLM requires strict user↔assistant alternation. After trimming or
        # role normalisation, adjacent messages of the same role can appear.
        # Merging their content is the safest recovery that preserves context.
        deduped: list[dict[str, Any]] = []
        for msg_copy in sanitized:
            role = msg_copy.get("role")
            if (
                deduped
                and deduped[-1].get("role") == role
                and role in ("user", "assistant")
                and not msg_copy.get("tool_calls")
                and not deduped[-1].get("tool_calls")
            ):
                prev_content = deduped[-1].get("content") or ""
                curr_content = msg_copy.get("content") or ""
                deduped[-1]["content"] = f"{prev_content}\n{curr_content}".strip()
            else:
                deduped.append(msg_copy)

        # 7. GLM-specific: ensure the system message is always first.
        # GLM-5 / GLM-4 rejects any system message that is not in position 0
        # (error code 1214). After merging/deduplication, a system message can
        # appear at a non-zero index — move it to the front.
        if getattr(self, "_is_glm_api", False):
            system_msgs = [m for m in deduped if m.get("role") == "system"]
            non_system_msgs = [m for m in deduped if m.get("role") != "system"]
            if system_msgs:
                # If multiple system messages were produced (edge case), merge them
                if len(system_msgs) > 1:
                    merged_content = "\n".join(m.get("content") or "" for m in system_msgs).strip()
                    system_msgs = [{"role": "system", "content": merged_content}]
                deduped = system_msgs + non_system_msgs
            # Ensure the conversation starts with user (not assistant) after system
            first_non_system = next((m for m in deduped if m.get("role") != "system"), None)
            if first_non_system and first_non_system.get("role") == "assistant":
                logger.debug("GLM API: prepending placeholder user message before leading assistant message")
                insert_pos = len(system_msgs) if system_msgs else 0
                deduped.insert(insert_pos, {"role": "user", "content": "Please continue."})

        return deduped

    @staticmethod
    def _tool_calls_to_text(tool_calls: list[dict[str, Any]]) -> str:
        """Convert tool_calls to a text description for context preservation.

        When orphaned assistant messages with tool_calls must be cleaned up,
        this preserves the context of what was attempted rather than discarding
        the entire message.
        """
        parts = []
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "unknown")
            raw_args = func.get("arguments", "{}")
            # Ensure args is a string (may be a parsed dict after internal processing)
            args_str = raw_args if isinstance(raw_args, str) else json.dumps(raw_args, ensure_ascii=False)
            # Truncate large arguments for readability
            if len(args_str) > 200:
                args_str = args_str[:200] + "..."
            parts.append(f"[Previously called {name}]")
        return "\n".join(parts)

    def _convert_orphaned_assistant(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Convert an orphaned assistant message with tool_calls into a text-only message.

        Preserves the content and a text description of the attempted tool calls
        so the LLM retains context about what was tried.
        """
        tool_calls = msg.get("tool_calls", [])
        original_content = msg.get("content") or ""
        tool_text = self._tool_calls_to_text(tool_calls)

        combined = f"{original_content}\n{tool_text}".strip() if original_content else tool_text

        converted = dict(msg)
        converted.pop("tool_calls", None)
        converted["content"] = combined
        return converted

    def _validate_and_fix_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Validate message sequence and fix tool_call/tool_response ordering issues.

        Ensures every assistant message with tool_calls is followed by the
        corresponding tool responses before any other message type.

        Orphaned assistant messages (with tool_calls but no matching tool responses)
        are converted to text-only messages preserving context about what was attempted,
        rather than being removed entirely.
        """
        if not messages:
            return messages

        # First, strip reasoning_content for thinking APIs
        messages = self._strip_reasoning_content(messages)

        # Sanitize all messages for strict API compatibility
        messages = self._sanitize_messages(messages)

        fixed_messages = []
        pending_tool_ids = set()

        for _i, msg in enumerate(messages):
            role = msg.get("role", "")

            # Check if this is an assistant message with tool_calls
            if role == "assistant" and msg.get("tool_calls"):
                # If we have pending tool_ids from a previous assistant message,
                # that means we never got responses — convert to text to preserve context
                if pending_tool_ids:
                    logger.debug(
                        f"Converting orphaned assistant message with unfulfilled tool_calls: {pending_tool_ids}"
                    )
                    # Find and convert the last assistant message with tool_calls
                    for j in range(len(fixed_messages) - 1, -1, -1):
                        if fixed_messages[j].get("role") == "assistant" and fixed_messages[j].get("tool_calls"):
                            fixed_messages[j] = self._convert_orphaned_assistant(fixed_messages[j])
                            break
                    pending_tool_ids = set()

                # Track the new tool_call_ids
                pending_tool_ids = {tc.get("id") for tc in msg.get("tool_calls", []) if tc.get("id")}
                fixed_messages.append(msg)

            elif role == "tool":
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id in pending_tool_ids:
                    pending_tool_ids.discard(tool_call_id)
                    fixed_messages.append(msg)
                elif not pending_tool_ids:
                    # Orphaned tool response — skip it (debug-level: recurs every LLM call
                    # until the stale message is naturally evicted from conversation history)
                    logger.debug(f"Removing orphaned tool response with id: {tool_call_id}")
                else:
                    # Drop mismatched tool responses while a specific sequence is pending.
                    # Keeping them can create orphan tool messages and break strict APIs.
                    logger.warning(
                        "Dropping mismatched tool response with id %s while pending ids are %s",
                        tool_call_id,
                        sorted(pending_tool_ids),
                    )

            else:
                # Regular message (user/system/assistant without tool_calls)
                if pending_tool_ids:
                    # Incomplete tool sequence — convert assistant to text instead of removing
                    logger.debug("Incomplete tool sequence detected, converting assistant message to text")
                    for j in range(len(fixed_messages) - 1, -1, -1):
                        if fixed_messages[j].get("role") == "assistant" and fixed_messages[j].get("tool_calls"):
                            fixed_messages[j] = self._convert_orphaned_assistant(fixed_messages[j])
                            break
                    # Also remove any orphaned tool responses after the converted assistant
                    pending_tool_ids = set()

                fixed_messages.append(msg)

        # Handle trailing incomplete tool sequence
        if pending_tool_ids:
            logger.debug("Trailing incomplete tool sequence, converting last assistant message to text")
            for j in range(len(fixed_messages) - 1, -1, -1):
                if fixed_messages[j].get("role") == "assistant" and fixed_messages[j].get("tool_calls"):
                    fixed_messages[j] = self._convert_orphaned_assistant(fixed_messages[j])
                    break

        if len(fixed_messages) != len(messages):
            logger.info(f"Fixed message sequence: {len(messages)} -> {len(fixed_messages)} messages")

        return fixed_messages

    def _llm_concurrency_slot(self):
        """Return an async context manager that guards one LLM API slot.

        When ``llm_concurrency_enabled`` is True the global ``LLMConcurrencyLimiter``
        semaphore is acquired for the duration of the call so that concurrent
        sessions cannot flood a single-key API provider.  When disabled a
        no-op ``nullcontext`` is returned so callers need no conditional logic.
        """
        from contextlib import nullcontext

        if bool(getattr(get_settings(), "llm_concurrency_enabled", True)):
            from app.domain.services.concurrency.llm_limiter import get_llm_limiter

            return get_llm_limiter().acquire()
        return nullcontext()

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
        """Send chat request to OpenAI API with automatic key rotation and retry.

        Args:
            messages: List of messages in OpenAI format
            tools: Optional list of tools
            response_format: Optional response format
            tool_choice: Optional tool choice configuration
            enable_caching: Whether to enable prompt caching
            model: Optional model override (unified adaptive routing)
            temperature: Optional temperature override (unified adaptive routing)
            max_tokens: Optional max_tokens override (unified adaptive routing)
            _attempt: Internal retry counter for key rotation

        Returns:
            Response message in OpenAI format
        """
        # Check retry limit to prevent infinite recursion
        max_retries = getattr(self, "_max_retries", 3)  # Default to 3 if not set
        if _attempt >= max_retries:
            key_count = len(self._key_pool.keys) if hasattr(self, "_key_pool") else 1
            raise RuntimeError(f"All {key_count} OpenAI/OpenRouter API keys exhausted after {_attempt} attempts")

        # Validate and fix message sequence before sending
        base_messages = self._validate_and_fix_messages(messages)

        # MLX mode: convert tools to text-based format
        original_tools = tools
        request_tools = tools
        request_messages = base_messages
        if self._is_mlx_mode and request_tools:
            logger.info(f"MLX mode: Converting {len(request_tools)} tools to text-based format")
            request_messages = self._convert_messages_for_mlx(request_messages)
            request_messages = self._inject_tools_into_messages(request_messages, request_tools)
            request_tools = None  # Don't pass tools parameter to MLX

        # Apply cache optimization for message structure
        if enable_caching and self._cache_manager:
            request_messages = self._cache_manager.prepare_messages_for_caching(request_messages)

        # Get healthy key and create client after request shape is known.
        try:
            client = await self._get_client(is_tool_call=bool(request_tools))
        except RuntimeError as e:
            # All keys exhausted
            raise RuntimeError(str(e)) from e

        settings = get_settings()
        llm_tool_max_tokens = max(0, int(getattr(settings, "llm_tool_max_tokens", 0) or 0))
        _settings_tool_timeout = max(0.0, float(getattr(settings, "llm_tool_request_timeout", 0.0) or 0.0))
        # Use the higher of settings and provider profile to avoid asyncio guard
        # firing before the httpx read timeout for slow providers (e.g. GLM-5).
        # Fallback to 0.0 (not 90.0) when profile is absent so tests that inject
        # low timeouts via settings are not overridden.
        _profile_tool_timeout = getattr(getattr(self, "_provider_profile", None), "tool_read_timeout", 0.0) or 0.0
        llm_tool_request_timeout = max(_settings_tool_timeout, _profile_tool_timeout)
        llm_tool_timeout_max_retries = max(0, int(getattr(settings, "llm_tool_timeout_max_retries", 0) or 0))
        llm_request_timeout = max(0.0, float(getattr(settings, "llm_request_timeout", 0.0) or 0.0))
        hard_call_timeout = self._resolve_hard_call_timeout(settings)
        timeout_fallback_fast_model = self._resolve_distinct_fast_model(
            str(getattr(settings, "fast_model", "") or "").strip()
        )
        model_override_for_attempt = model
        tool_timeout_retries = 0
        timeout_fallback_used = False
        model_override_for_attempt = self._resolve_slow_tool_breaker_model(
            request_tools=request_tools,
            model_override_for_attempt=model_override_for_attempt,
            timeout_fallback_fast_model=timeout_fallback_fast_model,
        )
        slow_tool_breaker_timeout_logged = False
        slow_tool_breaker_token_cap_logged = False

        max_retries = 3
        base_delay = 1.0
        validation_recovery_attempted = False

        # Proactive sanitization for strict providers — eliminates first-attempt
        # schema rejections that add 1-7s latency on every call.
        if self._needs_proactive_sanitize(getattr(self, "_provider_profile", None)):
            request_messages = self._build_validation_recovery_messages(request_messages)
            validation_recovery_attempted = True  # Don't re-sanitize on retry

        # Hold one concurrency slot for the entire retry loop so that retry storms
        # (e.g. 5 consecutive 90s timeouts from concurrent sessions) cannot exhaust
        # all available semaphore slots simultaneously.
        async with self._llm_concurrency_slot():
            return await self._ask_inner(
                base_messages=base_messages,
                request_messages=request_messages,
                request_tools=request_tools,
                original_tools=original_tools,
                response_format=response_format,
                tool_choice=tool_choice,
                enable_caching=enable_caching,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                _attempt=_attempt,
                client=client,
                settings=settings,
                llm_tool_max_tokens=llm_tool_max_tokens,
                llm_tool_request_timeout=llm_tool_request_timeout,
                llm_tool_timeout_max_retries=llm_tool_timeout_max_retries,
                llm_request_timeout=llm_request_timeout,
                hard_call_timeout=hard_call_timeout,
                timeout_fallback_fast_model=timeout_fallback_fast_model,
                model_override_for_attempt=model_override_for_attempt,
                timeout_fallback_used=timeout_fallback_used,
                slow_tool_breaker_timeout_logged=slow_tool_breaker_timeout_logged,
                slow_tool_breaker_token_cap_logged=slow_tool_breaker_token_cap_logged,
                max_retries=max_retries,
                base_delay=base_delay,
                validation_recovery_attempted=validation_recovery_attempted,
                tool_timeout_retries=tool_timeout_retries,
                messages=messages,
                tools=tools,
            )

    async def _ask_inner(
        self,
        *,
        base_messages: list[dict[str, Any]],
        request_messages: list[dict[str, Any]],
        request_tools: list[dict[str, Any]] | None,
        original_tools: list[dict[str, Any]] | None,
        response_format: dict[str, Any] | None,
        tool_choice: str | None,
        enable_caching: bool,
        model: str | None,
        temperature: float | None,
        max_tokens: int | None,
        _attempt: int,
        client: Any,
        settings: Any,
        llm_tool_max_tokens: int,
        llm_tool_request_timeout: float,
        llm_tool_timeout_max_retries: int,
        llm_request_timeout: float,
        hard_call_timeout: float,
        timeout_fallback_fast_model: str,
        model_override_for_attempt: str | None,
        timeout_fallback_used: bool,
        slow_tool_breaker_timeout_logged: bool,
        slow_tool_breaker_token_cap_logged: bool,
        max_retries: int,
        base_delay: float,
        validation_recovery_attempted: bool,
        tool_timeout_retries: int,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """Execute the retry loop for ask(). Called from ask() under the concurrency slot."""
        for attempt in range(max_retries + 1):  # every try
            response = None
            tool_request_timeout = llm_tool_request_timeout
            degraded_mode = self._should_use_slow_tool_breaker_degraded_mode(
                request_tools=request_tools,
                model_override_for_attempt=model_override_for_attempt,
                timeout_fallback_fast_model=timeout_fallback_fast_model,
            )
            if request_tools and llm_tool_request_timeout > 0 and tool_timeout_retries > 0:
                tool_request_timeout = llm_tool_request_timeout * (2**tool_timeout_retries)
                if llm_request_timeout > 0:
                    tool_request_timeout = min(tool_request_timeout, llm_request_timeout)
            capped_tool_request_timeout = self._cap_tool_timeout_for_slow_breaker(
                tool_request_timeout,
                degraded_mode=degraded_mode,
            )
            if (
                request_tools
                and capped_tool_request_timeout < tool_request_timeout
                and not slow_tool_breaker_timeout_logged
            ):
                logger.warning(
                    "Slow tool-call breaker active without FAST_MODEL; tightening tool timeout from %.1fs to %.1fs",
                    tool_request_timeout,
                    capped_tool_request_timeout,
                )
                slow_tool_breaker_timeout_logged = True
            tool_request_timeout = capped_tool_request_timeout
            call_timeout = self._combine_call_timeout(
                tool_request_timeout if request_tools else llm_request_timeout,
                hard_call_timeout,
            )

            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))  # back off
                    logger.info(f"Retrying API request (attempt {attempt + 1}/{max_retries + 1}) after {delay}s delay")
                    await asyncio.sleep(delay)

                # Use overrides if provided (Unified Adaptive Routing)
                effective_model = self._resolve_model_override(model_override_for_attempt)
                effective_temperature = temperature if temperature is not None else self._temperature
                effective_max_tokens = max_tokens if max_tokens is not None else self._max_tokens
                _file_write_max = getattr(settings, "llm_file_write_max_tokens", 0)
                if request_tools and llm_tool_max_tokens > 0 and effective_max_tokens > llm_tool_max_tokens:
                    if self._has_file_write_tool(request_tools) and _file_write_max > 0:
                        effective_max_tokens = min(effective_max_tokens, _file_write_max)
                        logger.debug(
                            "file_write tool detected — using elevated max_tokens %s (not capped to %s)",
                            effective_max_tokens,
                            llm_tool_max_tokens,
                        )
                    else:
                        logger.debug(
                            "Capping tool-call max_tokens from %s to %s for model %s",
                            effective_max_tokens,
                            llm_tool_max_tokens,
                            effective_model,
                        )
                        effective_max_tokens = llm_tool_max_tokens
                if request_tools:
                    capped_max_tokens = self._cap_tool_max_tokens_for_slow_breaker(
                        effective_max_tokens,
                        degraded_mode=degraded_mode,
                    )
                    if capped_max_tokens < effective_max_tokens and not slow_tool_breaker_token_cap_logged:
                        logger.warning(
                            "Slow tool-call breaker active without FAST_MODEL; capping tool-call max_tokens from %s to %s",
                            effective_max_tokens,
                            capped_max_tokens,
                        )
                        slow_tool_breaker_token_cap_logged = True
                    effective_max_tokens = capped_max_tokens

                # GPT-5 nano/mini and o1/o3 models have different parameter requirements
                is_new_model = effective_model.startswith(("gpt-5", "o1", "o3"))

                # Build parameters based on model type
                params = {
                    "model": effective_model,
                    "messages": request_messages,
                }

                if is_new_model:
                    # GPT-5+ models use max_completion_tokens and don't support custom temperature
                    params["max_completion_tokens"] = effective_max_tokens
                else:
                    # Older models use max_tokens and support temperature
                    params["max_tokens"] = effective_max_tokens
                    params["temperature"] = effective_temperature

                # For thinking APIs (Kimi, etc.), explicitly disable extended thinking
                # to avoid reasoning_content errors when replaying messages
                if self._is_thinking_api:
                    params["extra_body"] = {"thinking": {"type": "disabled"}}

                # MiniMax: separate thinking into reasoning_details field
                # to keep content clean for JSON extraction and user display
                if getattr(self, "_is_minimax", False):
                    extra = params.get("extra_body", {})
                    extra["reasoning_split"] = True
                    params["extra_body"] = extra

                # OpenRouter: ensure routing to providers that honour response_format
                if getattr(self, "_is_openrouter", False) and response_format:
                    extra = params.get("extra_body", {})
                    extra.setdefault("provider", {})["require_parameters"] = True
                    params["extra_body"] = extra

                llm_call_start = time.monotonic()

                # ── In-flight watchdog ────────────────────────────────
                # Logs a warning every 30s while the LLM call is pending
                # so hangs are visible in real-time instead of silent.
                _watchdog_interval = 30.0
                _watchdog_task: asyncio.Task | None = None

                async def _watchdog(
                    *,
                    _interval: float = _watchdog_interval,
                    _start: float = llm_call_start,
                    _model: str = effective_model,
                    _has_tools: bool = bool(request_tools),
                    _attempt: int = attempt,
                ) -> None:
                    while True:
                        await asyncio.sleep(_interval)
                        _elapsed = time.monotonic() - _start
                        logger.warning(
                            "LLM call in-flight for %.0fs (model=%s, tools=%s, attempt=%s) — still waiting",
                            _elapsed,
                            _model,
                            "yes" if _has_tools else "no",
                            _attempt + 1,
                        )

                _watchdog_task = asyncio.create_task(_watchdog())

                try:
                    if request_tools:
                        # OpenAI API mode with native tool support
                        logger.debug(f"Sending request with tools, model: {effective_model}, attempt: {attempt + 1}")
                        # Some providers (DeepSeek, etc.) don't support response_format with tools
                        # Only pass response_format for official OpenAI endpoints
                        use_response_format = response_format if self._supports_response_format_with_tools() else None
                        tool_call = client.chat.completions.create(
                            **params,
                            tools=request_tools,
                            response_format=use_response_format or NOT_GIVEN,
                            tool_choice=tool_choice,
                            parallel_tool_calls=self._supports_parallel_tool_calls(),
                        )
                        if call_timeout > 0:
                            response = await asyncio.wait_for(tool_call, timeout=call_timeout)
                        else:
                            response = await tool_call
                    else:
                        # MLX mode or no tools
                        logger.debug(
                            f"Sending request without native tools, model: {effective_model}, MLX mode: {self._is_mlx_mode}, attempt: {attempt + 1}"
                        )
                        completion_call = client.chat.completions.create(
                            **params,
                            response_format=(response_format if not self._is_mlx_mode else None) or NOT_GIVEN,
                        )
                        if call_timeout > 0:
                            response = await asyncio.wait_for(completion_call, timeout=call_timeout)
                        else:
                            response = await completion_call
                finally:
                    _watchdog_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await _watchdog_task

                llm_call_duration = time.monotonic() - llm_call_start
                self._record_tool_call_latency(
                    duration_seconds=llm_call_duration,
                    has_tools=bool(request_tools),
                    fast_model=timeout_fallback_fast_model,
                )
                _slow = get_settings().llm_slow_request_threshold
                if llm_call_duration > _slow * 2:
                    log_fn = logger.error
                elif llm_call_duration > _slow:
                    log_fn = logger.warning
                else:
                    log_fn = logger.info
                log_fn(
                    f"LLM ask() completed in {llm_call_duration:.1f}s "
                    f"(model={effective_model}, tools={'yes' if request_tools else 'no'}, "
                    f"attempt={attempt + 1})"
                )

                logger.debug(f"Response from API: {response.model_dump()}")

                if not response or not response.choices:
                    error_msg = f"API returned invalid response (no choices) on attempt {attempt + 1}"
                    logger.error(error_msg)
                    if attempt == max_retries:
                        raise LLMException(f"Failed after {max_retries + 1} attempts: {error_msg}")
                    continue

                # Track usage if context is set
                await self._record_usage(response)

                # Record Prometheus metrics

                with contextlib.suppress(Exception):
                    from app.core.prometheus_metrics import record_llm_call

                    _usage = getattr(response, "usage", None)
                    record_llm_call(
                        model=effective_model,
                        status="success",
                        latency=llm_call_duration,
                        prompt_tokens=getattr(_usage, "prompt_tokens", 0) or 0,
                        completion_tokens=getattr(_usage, "completion_tokens", 0) or 0,
                        cached_tokens=getattr(getattr(_usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0,
                    )

                result = response.choices[0].message.model_dump()

                # Check finish_reason for truncation detection
                finish_reason = response.choices[0].finish_reason
                if finish_reason == "length":
                    logger.warning(
                        "LLM response truncated (finish_reason=length, max_tokens=%s)",
                        self._max_tokens,
                    )
                    result["_finish_reason"] = "length"
                    # Flag tool calls as potentially truncated so the agent
                    # layer can avoid executing garbage args and instead
                    # request a retry with a smaller payload.
                    if result.get("tool_calls"):
                        result["_tool_args_truncated"] = True
                elif finish_reason not in ("stop", "end_turn", "tool_calls"):
                    logger.debug(f"LLM finish_reason: {finish_reason}")

                # MLX mode: parse tool calls from text response
                if self._is_mlx_mode and original_tools:
                    content = result.get("content", "")
                    parsed_tool_call = self._parse_tool_call_from_text(content, original_tools)
                    if parsed_tool_call:
                        logger.info("MLX mode: Parsed tool call from text response")
                        return parsed_tool_call

                # Tool argument pre-validation for truncation-prone providers
                _profile = getattr(self, "_provider_profile", None)
                if result.get("tool_calls") and request_tools and getattr(_profile, "tool_arg_truncation_prone", False):
                    result = self._apply_tool_arg_validation(result, request_tools)

                # Record success using the key that was actually used for this request
                # (not get_api_key() which may have rotated since the request started).
                try:
                    _used_key = getattr(self, "_cached_client_key", None)
                    if _used_key:
                        self._key_pool.record_success(_used_key)
                except Exception:
                    logger.debug("record_success failed", exc_info=True)

                return result

            except TimeoutError as e:
                timeout_seconds = (
                    call_timeout
                    if call_timeout > 0
                    else (tool_request_timeout if request_tools and tool_request_timeout > 0 else llm_request_timeout)
                )
                logger.warning(
                    "LLM request timed out after %.1fs (model=%s, tools=%s, attempt=%s/%s)",
                    timeout_seconds,
                    effective_model,
                    "yes" if request_tools else "no",
                    attempt + 1,
                    max_retries + 1,
                )

                if request_tools and tool_timeout_retries < llm_tool_timeout_max_retries:
                    tool_timeout_retries += 1
                    if timeout_fallback_fast_model and not timeout_fallback_used:
                        model_override_for_attempt = timeout_fallback_fast_model
                        timeout_fallback_used = True
                        logger.warning(
                            "Retrying timed-out tool call with fast model '%s' (retry %s/%s)",
                            timeout_fallback_fast_model,
                            tool_timeout_retries,
                            llm_tool_timeout_max_retries,
                        )
                    else:
                        logger.warning(
                            "Retrying timed-out tool call (retry %s/%s)",
                            tool_timeout_retries,
                            llm_tool_timeout_max_retries,
                        )
                    continue

                if not request_tools and timeout_fallback_fast_model and not timeout_fallback_used:
                    model_override_for_attempt = timeout_fallback_fast_model
                    timeout_fallback_used = True
                    logger.warning(
                        "Retrying timed-out non-tool call with fast model '%s'",
                        timeout_fallback_fast_model,
                    )
                    continue

                with contextlib.suppress(Exception):
                    from app.core.prometheus_metrics import record_llm_call

                    record_llm_call(
                        model=effective_model,
                        status="error",
                        latency=time.monotonic() - llm_call_start,
                    )
                raise LLMException(
                    f"LLM request timed out after {timeout_seconds:.1f}s (model={effective_model}, tools={'yes' if request_tools else 'no'})"
                ) from e

            except RateLimitError as e:
                # Parse rate limit TTL and mark key exhausted
                key = await self.get_api_key()
                if key:
                    ttl = self._parse_openai_rate_limit(e)
                    await self._key_pool.mark_exhausted(key, ttl_seconds=ttl)
                    # Short-circuit: if no healthy keys remain after marking, raise immediately
                    # instead of making another API call that will also fail with 429.
                    if not await self._key_pool.get_healthy_key():
                        key_count = len(self._key_pool.keys) if hasattr(self, "_key_pool") else 1
                        raise APIKeysExhaustedError("OpenAI/OpenRouter", key_count) from e
                    max_retries = getattr(self, "_max_retries", 3)
                    logger.warning(
                        f"OpenAI rate limit hit, rotating to next key (attempt {_attempt + 1}/{max_retries})"
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

            except Exception as e:  # Broad catch: dispatches across OpenAI/GLM/MLX/Kimi provider errors
                # Check for authentication errors (401) and rotate keys
                error_msg = str(e).lower()
                if "401" in error_msg or "unauthorized" in error_msg or "authentication" in error_msg:
                    key = await self.get_api_key()
                    if key:
                        await self._key_pool.mark_invalid(key)
                        max_retries = getattr(self, "_max_retries", 3)
                        logger.error(
                            f"OpenAI authentication error, rotating to next key (attempt {_attempt + 1}/{max_retries})"
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
                error_msg = str(e).lower()

                # Check for MLX-specific content type error
                if "only 'text' content type is supported" in error_msg:
                    logger.warning("MLX content type error detected, enabling MLX mode for retry")
                    self._is_mlx_mode = True
                    if original_tools:
                        request_messages = self._convert_messages_for_mlx(base_messages)
                        request_messages = self._inject_tools_into_messages(request_messages, original_tools)
                        request_tools = None
                        if enable_caching and self._cache_manager:
                            request_messages = self._cache_manager.prepare_messages_for_caching(request_messages)
                    continue

                # Check for token limit errors and raise specific exception
                if any(
                    term in error_msg
                    for term in [
                        "context_length_exceeded",
                        "maximum context length",
                        "too many tokens",
                        "max_tokens",
                        "context window",
                    ]
                ):
                    logger.warning(f"Token limit exceeded: {e}")
                    raise TokenLimitExceededError(str(e)) from e

                # Detect message validation errors from strict APIs (Zhipu GLM error 1214, etc.).
                # We attempt one emergency payload rewrite before failing.
                if self._is_message_validation_error(e):
                    if not validation_recovery_attempted:
                        recovered_messages = self._build_validation_recovery_messages(base_messages)
                        if recovered_messages != base_messages:
                            validation_recovery_attempted = True
                            base_messages = recovered_messages
                            request_messages = recovered_messages
                            request_tools = original_tools
                            if self._is_mlx_mode and request_tools:
                                request_messages = self._convert_messages_for_mlx(request_messages)
                                request_messages = self._inject_tools_into_messages(request_messages, request_tools)
                                request_tools = None
                            if enable_caching and self._cache_manager:
                                request_messages = self._cache_manager.prepare_messages_for_caching(request_messages)
                            logger.warning(
                                "API rejected message schema on attempt %d; retrying once with simplified transcript",
                                attempt + 1,
                            )
                            continue
                    logger.error(
                        f"API message validation error (likely strict schema): {e!s}. "
                        f"Messages were sanitized and recovery payload was exhausted."
                    )
                    raise

                error_log = f"Error calling API on attempt {attempt + 1}: {e!s}"
                logger.error(error_log)
                if attempt == max_retries:
                    with contextlib.suppress(Exception):
                        from app.core.prometheus_metrics import record_llm_call

                        record_llm_call(
                            model=effective_model,
                            status="error",
                            latency=time.monotonic() - llm_call_start,
                        )
                    raise e
                continue
        # This should never be reached - all paths should either return or raise
        raise LLMException(f"LLM request failed after {max_retries + 1} attempts with no response")

    @staticmethod
    def _extract_json_from_text(text: str) -> str | None:
        """Extract outermost JSON object from text using balanced-brace matching.

        Useful when the LLM returns JSON embedded in prose or thinking content.

        Args:
            text: Text that may contain a JSON object

        Returns:
            Extracted JSON string, or None if no valid JSON found
        """
        # Find the first '{' that could start a JSON object
        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i in range(start, len(text)):
            ch = text[i]

            if escape_next:
                escape_next = False
                continue

            if ch == "\\":
                if in_string:
                    escape_next = True
                continue

            if ch == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    # Validate it's actually parseable JSON
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        # Try next opening brace
                        next_start = text.find("{", start + 1)
                        if next_start == -1:
                            return None
                        start = next_start
                        depth = 0
                        # Reset and continue from new start
                        continue

        return None

    def get_cache_metrics(self) -> dict[str, Any]:
        """Get prompt caching performance metrics"""
        if self._cache_manager:
            return self._cache_manager.get_metrics()
        return {}

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

        Uses OpenAI's native JSON schema support for type-safe responses.
        Falls back to json_object mode + Pydantic validation for compatibility.

        Note: Multi-key rotation not implemented for structured output.
        Uses the primary key only.

        Args:
            messages: List of messages
            response_model: Pydantic model class for response validation
            tools: Optional tools (usually None for structured output)
            tool_choice: Optional tool choice
            enable_caching: Whether to use prompt caching
            model: Optional model override for adaptive model selection (DeepCode Phase 1)
            temperature: Optional temperature override (uses self._temperature if None)
            max_tokens: Optional max_tokens override (uses self._max_tokens if None)

        Returns:
            Validated Pydantic model instance
        """
        # Get client with current active key
        client = await self._get_client(is_tool_call=bool(tools))
        # Validate and fix message sequence
        base_messages = self._validate_and_fix_messages(messages)

        # Apply cache optimization
        request_messages = base_messages
        if enable_caching and self._cache_manager:
            request_messages = self._cache_manager.prepare_messages_for_caching(request_messages)

        # Build and normalize JSON schema for strict-mode compatibility.
        schema = self._normalize_strict_json_schema(response_model.model_json_schema())

        # Detect if model supports native structured outputs (GPT-4o+, GPT-5+, OpenRouter)
        supports_strict_schema = self._supports_structured_output()

        # Determine if instructor library should handle validation.
        # Instructor is skipped for thinking APIs (need special reasoning_content handling)
        # and when tools are provided (instructor doesn't mix well with tool calling).
        from app.infrastructure.external.llm.instructor_adapter import (
            INSTRUCTOR_AVAILABLE,
            patch_client,
            select_instructor_mode,
        )

        settings = get_settings()
        use_instructor = (
            INSTRUCTOR_AVAILABLE
            and getattr(settings, "use_instructor_structured_output", True)
            and not self._is_thinking_api
            and not tools
        )
        patched_client = None
        if use_instructor:
            mode = select_instructor_mode(
                supports_json_schema=supports_strict_schema,
                supports_json_object=self._supports_json_object_format(),
                is_openrouter=getattr(self, "_is_openrouter", False),
            )
            patched_client = patch_client(client, mode)
            logger.info(
                "Using instructor (mode=%s) for structured output (model=%s, schema=%s)",
                mode,
                self._model_name,
                response_model.__name__,
            )

        max_retries = 3
        base_delay = 1.0
        # Flag to control thinking API behavior across retries.
        # Starts True for thinking APIs; set to False if empty response
        # indicates the model needs thinking enabled to produce output.
        disable_thinking = self._is_thinking_api
        validation_recovery_attempted = False

        # Proactive sanitization for strict providers — eliminates first-attempt
        # schema rejections that add 1-7s latency on every call.
        if self._needs_proactive_sanitize(getattr(self, "_provider_profile", None)):
            request_messages = self._build_validation_recovery_messages(request_messages)
            validation_recovery_attempted = True  # Don't re-sanitize on retry

        # Use model override if provided (DeepCode Phase 1: adaptive model selection)
        effective_model = self._resolve_model_override(model)

        # Hold one concurrency slot for the entire retry loop.
        async with self._llm_concurrency_slot():
            for attempt in range(max_retries + 1):
                try:
                    if attempt > 0:
                        delay = base_delay * (2 ** (attempt - 1))
                        logger.info(f"Retrying structured request (attempt {attempt + 1}/{max_retries + 1})")
                        await asyncio.sleep(delay)

                    is_new_model = effective_model.startswith(("gpt-5", "o1", "o3"))
                    attempt_messages = [dict(message) for message in request_messages]
                    params = {
                        "model": effective_model,
                        "messages": attempt_messages,
                    }

                    effective_max_tokens = max_tokens if max_tokens is not None else self._max_tokens
                    effective_temperature = temperature if temperature is not None else self._temperature
                    if is_new_model:
                        params["max_completion_tokens"] = effective_max_tokens
                    else:
                        params["max_tokens"] = effective_max_tokens
                        params["temperature"] = effective_temperature

                    # For thinking APIs (Kimi, etc.), disable extended thinking unless
                    # a previous empty response indicated thinking is needed for output
                    if disable_thinking:
                        params["extra_body"] = {"thinking": {"type": "disabled"}}

                    # MiniMax: separate thinking into reasoning_details field
                    if getattr(self, "_is_minimax", False):
                        extra = params.get("extra_body", {})
                        extra["reasoning_split"] = True
                        params["extra_body"] = extra

                    if supports_strict_schema:
                        # Use native structured output with strict schema
                        params["response_format"] = {
                            "type": "json_schema",
                            "json_schema": {"name": response_model.__name__, "strict": True, "schema": schema},
                        }
                        # OpenRouter: ensure routing only to providers that honour json_schema
                        if getattr(self, "_is_openrouter", False):
                            extra = params.get("extra_body", {})
                            extra.setdefault("provider", {})["require_parameters"] = True
                            params["extra_body"] = extra
                    elif self._supports_json_object_format():
                        # Use json_object if provider supports it
                        params["response_format"] = {"type": "json_object"}
                        logger.debug("Using json_object response format")
                    else:
                        # Provider doesn't support json_object - use prompt-based JSON
                        if self._model_name not in OpenAILLM._json_format_warned:
                            OpenAILLM._json_format_warned.add(self._model_name)
                            logger.info(
                                "Provider doesn't support json_object format, using prompt-based JSON for %s",
                                self._model_name,
                            )
                        else:
                            logger.debug("Using prompt-based JSON fallback for %s", self._model_name)
                        json_instruction = (
                            "\n\nCRITICAL: You must respond with valid JSON matching this schema:\n"
                            f"{json.dumps(schema, indent=2)}\n\n"
                            "Respond with ONLY the JSON object, no other text or explanation."
                        )
                        # Add instruction to system message or create one
                        if params["messages"] and params["messages"][0]["role"] == "system":
                            params["messages"][0]["content"] += json_instruction
                        else:
                            params["messages"].insert(0, {"role": "system", "content": json_instruction})

                    if tools:
                        params["tools"] = tools
                        params["tool_choice"] = tool_choice
                        params["parallel_tool_calls"] = False

                    llm_call_start = time.monotonic()

                    # Timeout guard — ask_structured() must not hang indefinitely.
                    # Uses the same LLM_REQUEST_TIMEOUT as ask() (default 90s).
                    _structured_timeout = max(
                        90.0,
                        float(getattr(settings, "llm_request_timeout", 0.0) or 0.0),
                    )

                    # ── instructor path ──────────────────────────────────────
                    if patched_client and not tools:
                        # Instructor handles response_format, JSON parsing, and
                        # Pydantic validation internally.  We pop response_format
                        # to avoid double-setting it.
                        params.pop("response_format", None)

                        # MiniMax prompt reinforcement: MiniMax-M2.7 sometimes
                        # returns narrative text instead of JSON even when
                        # response_format or instructor is used.  A prompt-level
                        # JSON-only instruction drastically reduces first-attempt
                        # failures (observed 100% narrative on chart analysis).
                        if getattr(self, "_is_minimax", False):
                            _json_reminder = (
                                "\n\nIMPORTANT: Respond with ONLY a valid JSON object. "
                                "Do NOT include any explanation, reasoning, markdown, "
                                "or text outside the JSON object."
                            )
                            _msgs = params.get("messages", [])
                            if _msgs and _msgs[0].get("role") == "system":
                                _msgs[0] = {**_msgs[0], "content": _msgs[0]["content"] + _json_reminder}
                            elif _msgs:
                                _msgs.insert(0, {"role": "system", "content": _json_reminder.strip()})

                        try:
                            result, completion = await asyncio.wait_for(
                                patched_client.chat.completions.create_with_completion(
                                    response_model=response_model,
                                    max_retries=1,
                                    **params,
                                ),
                                timeout=_structured_timeout,
                            )
                        except TimeoutError:
                            llm_call_duration = time.monotonic() - llm_call_start
                            logger.warning(
                                "LLM ask_structured() [instructor] timed out after %.1fs "
                                "(model=%s, schema=%s, attempt=%d/%d)",
                                llm_call_duration,
                                effective_model,
                                response_model.__name__,
                                attempt + 1,
                                max_retries + 1,
                            )
                            if attempt < max_retries:
                                continue
                            raise TimeoutError(
                                f"ask_structured() timed out after {_structured_timeout}s on attempt {attempt + 1}"
                            ) from None
                        llm_call_duration = time.monotonic() - llm_call_start
                        _slow = get_settings().llm_slow_request_threshold
                        log_fn = logger.warning if llm_call_duration > _slow else logger.info
                        log_fn(
                            f"LLM ask_structured() [instructor] completed in {llm_call_duration:.1f}s "
                            f"(model={effective_model}, schema={response_model.__name__}, "
                            f"attempt={attempt + 1})"
                        )
                        await self._record_usage(completion)
                        # Record Prometheus metrics

                        with contextlib.suppress(Exception):
                            from app.core.prometheus_metrics import record_llm_call

                            _usage = getattr(completion, "usage", None)
                            record_llm_call(
                                model=effective_model,
                                status="success",
                                latency=llm_call_duration,
                                prompt_tokens=getattr(_usage, "prompt_tokens", 0) or 0,
                                completion_tokens=getattr(_usage, "completion_tokens", 0) or 0,
                                cached_tokens=getattr(
                                    getattr(_usage, "prompt_tokens_details", None), "cached_tokens", 0
                                )
                                or 0,
                            )
                        return result

                    # ── manual path (fallback) ───────────────────────────────
                    try:
                        response = await asyncio.wait_for(
                            client.chat.completions.create(**params),
                            timeout=_structured_timeout,
                        )
                    except TimeoutError:
                        llm_call_duration = time.monotonic() - llm_call_start
                        logger.warning(
                            "LLM ask_structured() timed out after %.1fs (model=%s, schema=%s, attempt=%d/%d)",
                            llm_call_duration,
                            effective_model,
                            response_model.__name__,
                            attempt + 1,
                            max_retries + 1,
                        )
                        if attempt < max_retries:
                            continue
                        raise TimeoutError(
                            f"ask_structured() timed out after {_structured_timeout}s on attempt {attempt + 1}"
                        ) from None
                    llm_call_duration = time.monotonic() - llm_call_start
                    _slow = get_settings().llm_slow_request_threshold
                    log_fn = logger.warning if llm_call_duration > _slow else logger.info
                    log_fn(
                        f"LLM ask_structured() completed in {llm_call_duration:.1f}s "
                        f"(model={effective_model}, schema={response_model.__name__}, "
                        f"attempt={attempt + 1})"
                    )

                    # Record usage for structured requests
                    await self._record_usage(response)

                    # Record Prometheus metrics

                    with contextlib.suppress(Exception):
                        from app.core.prometheus_metrics import record_llm_call

                        _usage = getattr(response, "usage", None)
                        record_llm_call(
                            model=effective_model,
                            status="success",
                            latency=llm_call_duration,
                            prompt_tokens=getattr(_usage, "prompt_tokens", 0) or 0,
                            completion_tokens=getattr(_usage, "completion_tokens", 0) or 0,
                            cached_tokens=getattr(getattr(_usage, "prompt_tokens_details", None), "cached_tokens", 0)
                            or 0,
                        )

                    if not response or not response.choices:
                        if attempt == max_retries:
                            raise LLMException("API returned invalid response")
                        continue

                    message = response.choices[0].message
                    content = message.content

                    refusal_message = getattr(message, "refusal", None)
                    if refusal_message:
                        raise StructuredRefusalError(str(refusal_message))

                    # For reasoning models (Kimi Code, o1, etc.), check reasoning_content if content is empty
                    if not content and hasattr(message, "reasoning_content") and message.reasoning_content:
                        logger.info("Using reasoning_content as fallback for empty content field")
                        content = message.reasoning_content

                    # Check for truncation before parsing
                    finish_reason = response.choices[0].finish_reason
                    if finish_reason == "content_filter":
                        raise StructuredContentFilterError("Structured output blocked by content filter")
                    if finish_reason == "length":
                        logger.warning("Structured output truncated (finish_reason=length), retrying")
                        if attempt == max_retries:
                            # Last resort: attempt JSON repair on the partial response before failing.
                            # Some models (e.g. glm-4.7) truncate mid-JSON but the partial output
                            # may still be recoverable via balanced-brace extraction + Pydantic
                            # partial validation.
                            if content:
                                try:
                                    extracted = self._extract_json_from_text(content)
                                    if extracted:
                                        partial_parsed = json.loads(extracted)
                                        result = response_model.model_validate(partial_parsed)
                                        logger.info(
                                            "Recovered truncated structured output via JSON repair (model=%s, schema=%s)",
                                            self._model_name,
                                            response_model.__name__,
                                        )
                                        return result
                                except Exception as repair_err:
                                    logger.debug("JSON repair on truncated output failed: %s", repair_err)
                            raise StructuredTruncationError("Structured output truncated after all retries")
                        continue

                    if not content:
                        # For thinking APIs: empty content with thinking disabled means
                        # the model's primary output mechanism was suppressed. Retry with
                        # thinking enabled and extract JSON from reasoning output.
                        if disable_thinking:
                            logger.warning(
                                "Thinking API returned empty content with thinking disabled — "
                                "retrying with thinking enabled"
                            )
                            disable_thinking = False
                            continue
                        if attempt == max_retries:
                            raise LLMException("Empty response content")
                        continue

                    # Parse and validate with Pydantic (fast path via model_validate_json)
                    try:
                        return response_model.model_validate_json(content)
                    except ValidationError:
                        # Try balanced-brace extraction for JSON embedded in prose/thinking
                        extracted = self._extract_json_from_text(content)
                        if extracted:
                            logger.info("Extracted JSON from prose via balanced-brace matching")
                            return response_model.model_validate_json(extracted)
                        raise
                except (StructuredRefusalError, StructuredContentFilterError, StructuredTruncationError):
                    raise
                except (ValidationError, json.JSONDecodeError) as e:
                    logger.warning(f"Structured validation error on attempt {attempt + 1}: {e}")

                    # Instructor recovery: when instructor fails because the
                    # model returned narrative instead of JSON (common with
                    # MiniMax), try to extract JSON from the raw response
                    # content before burning a retry.
                    if patched_client and not tools:
                        _raw_content: str | None = None
                        with contextlib.suppress(Exception):
                            # instructor wraps the completion; try common locations
                            _last = getattr(e, "last_completion", None) or getattr(e, "response", None)
                            if _last and hasattr(_last, "choices") and _last.choices:
                                _raw_content = getattr(_last.choices[0].message, "content", None)
                            # InstructorRetryException nests the actual content differently
                            if not _raw_content and hasattr(e, "__cause__") and e.__cause__:
                                _cause = e.__cause__
                                _lc = getattr(_cause, "last_completion", None)
                                if _lc and hasattr(_lc, "choices") and _lc.choices:
                                    _raw_content = getattr(_lc.choices[0].message, "content", None)
                        if _raw_content:
                            _extracted = self._extract_json_from_text(_raw_content)
                            if _extracted:
                                try:
                                    result = response_model.model_validate_json(_extracted)
                                    logger.info(
                                        "Recovered structured output from instructor failure via JSON extraction "
                                        "(model=%s, schema=%s)",
                                        effective_model,
                                        response_model.__name__,
                                    )
                                    return result
                                except Exception:
                                    logger.debug("JSON extraction recovery also failed, will retry")
                    if attempt == max_retries:
                        try:
                            from app.core.prometheus_metrics import llm_json_parse_failures_total

                            llm_json_parse_failures_total.inc({"model": self._model_name, "method": "ask_structured"})
                        except Exception:
                            logger.debug("Failed to record ask_structured parse failure metric", exc_info=True)
                        raise StructuredSchemaValidationError(f"Failed to validate structured response: {e}") from e
                except RateLimitError as e:
                    retry_after = None
                    if hasattr(e, "response") and e.response is not None:
                        retry_after_header = e.response.headers.get("Retry-After") or e.response.headers.get(
                            "retry-after"
                        )
                        if retry_after_header:
                            with contextlib.suppress(ValueError, TypeError):
                                retry_after = float(retry_after_header)
                    if retry_after is None:
                        # Use centralized exponential backoff
                        retry_config = RetryConfig(
                            base_delay=base_delay,
                            exponential_base=2.0,
                            max_delay=60.0,
                            jitter=True,
                        )
                        retry_after = calculate_delay(attempt + 1, retry_config)
                    logger.warning(
                        f"OpenAI rate limit hit on structured request attempt {attempt + 1}/{max_retries + 1}, "
                        f"retrying after {retry_after:.1f}s"
                    )
                    if attempt == max_retries:
                        raise
                    await asyncio.sleep(retry_after)
                except (
                    Exception
                ) as e:  # Broad catch: dispatches across multi-provider errors; re-raises on final attempt
                    error_msg = str(e).lower()
                    if any(
                        term in error_msg
                        for term in [
                            "context_length_exceeded",
                            "maximum context length",
                            "too many tokens",
                            "max_tokens",
                            "context window",
                        ]
                    ):
                        raise TokenLimitExceededError(str(e)) from e

                    if self._is_message_validation_error(e):
                        if not validation_recovery_attempted:
                            recovered_messages = self._build_validation_recovery_messages(base_messages)
                            if recovered_messages != base_messages:
                                validation_recovery_attempted = True
                                base_messages = recovered_messages
                                request_messages = recovered_messages
                                if enable_caching and self._cache_manager:
                                    request_messages = self._cache_manager.prepare_messages_for_caching(
                                        request_messages
                                    )
                                logger.warning(
                                    "Structured request message validation failed on attempt %d; "
                                    "retrying once with simplified transcript",
                                    attempt + 1,
                                )
                                continue
                        raise
                    if attempt == max_retries:
                        raise
                    logger.warning(f"Structured request failed on attempt {attempt + 1}: {e}")

            raise LLMException("Failed to get structured response after all retries")

    def _capabilities(self):
        return get_capabilities(self._model_name, self._api_base)

    @classmethod
    def _normalize_strict_json_schema(cls, schema: dict[str, Any]) -> dict[str, Any]:
        """Normalize schema for strict structured output requirements."""
        if not isinstance(schema, dict):
            return schema

        def _walk(node: Any) -> Any:
            if isinstance(node, dict):
                if node.get("type") == "object" or "properties" in node:
                    properties = node.get("properties")
                    if isinstance(properties, dict):
                        node["required"] = sorted(properties.keys())
                        if "additionalProperties" not in node:
                            node["additionalProperties"] = False
                for key, value in list(node.items()):
                    node[key] = _walk(value)
            elif isinstance(node, list):
                return [_walk(item) for item in node]
            return node

        return _walk(dict(schema))

    def _supports_structured_output(self) -> bool:
        """Check if model supports strict json_schema structured output."""
        if self._is_mlx_mode:
            return False
        return self._capabilities().json_schema

    def _supports_response_format_with_tools(self) -> bool:
        """Check if provider supports response_format + tools combination."""
        caps = self._capabilities()
        return caps.json_schema and caps.tool_use

    def _supports_parallel_tool_calls(self) -> bool:
        """Check if provider supports parallel tool calls."""
        return self._capabilities().parallel_tool_calls

    def _supports_json_object_format(self) -> bool:
        """Check if provider supports json_object response format."""
        return self._capabilities().json_object

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
        """Stream chat response from OpenAI API with automatic key rotation.

        Args:
            messages: List of messages
            tools: Optional tools for function calling
            response_format: Optional response format
            tool_choice: Optional tool choice
            enable_caching: Whether to use prompt caching
            model: Optional model override for adaptive model selection (DeepCode Phase 1)
            _attempt: Internal retry counter for key rotation

        Yields:
            Content chunks as strings
        """
        # Check retry limit
        max_retries = getattr(self, "_max_retries", 3)
        if _attempt >= max_retries:
            self._last_stream_metadata = {
                "finish_reason": "error",
                "truncated": False,
                "provider": "openai",
                "error": "all_keys_exhausted",
            }
            key_count = len(self._key_pool.keys) if hasattr(self, "_key_pool") else 1
            raise RuntimeError(f"All {key_count} OpenAI/OpenRouter API keys exhausted after {_attempt} attempts")

        self._last_stream_metadata = None

        # Get healthy key and create client
        try:
            client = await self._get_client(is_streaming=True, is_tool_call=bool(tools))
        except RuntimeError as e:
            # All keys exhausted
            self._last_stream_metadata = {
                "finish_reason": "error",
                "truncated": False,
                "provider": "openai",
                "error": "all_keys_exhausted",
            }
            raise RuntimeError(str(e)) from e

        # Validate and fix message sequence
        base_messages = self._validate_and_fix_messages(messages)

        # MLX mode doesn't support streaming well, fall back to regular ask
        if self._is_mlx_mode:
            result = await self.ask(
                base_messages,
                tools,
                response_format,
                tool_choice,
                enable_caching,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                _attempt=_attempt,
            )
            content = result.get("content", "")
            finish_reason = result.get("_finish_reason")
            self._last_stream_metadata = {
                "finish_reason": finish_reason or "stop",
                "truncated": finish_reason == "length",
                "provider": "openai",
            }
            if content:
                yield content
            return

        # Apply cache optimization
        request_messages = base_messages
        if enable_caching and self._cache_manager:
            request_messages = self._cache_manager.prepare_messages_for_caching(request_messages)

        validation_recovery_attempted = False

        # Proactive sanitization for strict providers — eliminates first-attempt
        # schema rejections that add 1-7s latency on every call.
        if self._needs_proactive_sanitize(getattr(self, "_provider_profile", None)):
            request_messages = self._build_validation_recovery_messages(request_messages)
            validation_recovery_attempted = True  # Don't re-sanitize on retry

        # Use model override if provided (DeepCode Phase 1: adaptive model selection)
        effective_model = self._resolve_model_override(model)

        # Hold one concurrency slot for the entire streaming loop so that concurrent
        # sessions cannot overwhelm a single-key API provider with parallel requests.
        async with self._llm_concurrency_slot():
            while True:
                is_new_model = effective_model.startswith(("gpt-5", "o1", "o3"))
                params = {
                    "model": effective_model,
                    "messages": request_messages,
                    "stream": True,
                }
                if self._supports_stream_usage:
                    params["stream_options"] = {"include_usage": True}

                effective_max_tokens = max_tokens if max_tokens is not None else self._max_tokens
                effective_temperature = temperature if temperature is not None else self._temperature
                if is_new_model:
                    params["max_completion_tokens"] = effective_max_tokens
                else:
                    params["max_tokens"] = effective_max_tokens
                    params["temperature"] = effective_temperature

                # For thinking APIs (Kimi, etc.), explicitly disable extended thinking
                if self._is_thinking_api:
                    params["extra_body"] = {"thinking": {"type": "disabled"}}

                # MiniMax: separate thinking into reasoning_details field
                if getattr(self, "_is_minimax", False):
                    extra = params.get("extra_body", {})
                    extra["reasoning_split"] = True
                    params["extra_body"] = extra

                if tools:
                    params["tools"] = tools
                    params["tool_choice"] = tool_choice
                    params["parallel_tool_calls"] = False

                if response_format and not tools:
                    params["response_format"] = response_format

                completion_parts: list[str] = []
                usage_counts: dict[str, int] | None = None
                finish_reason: str | None = None

                try:
                    stream_start = time.monotonic()
                    ttft_logged = False
                    stream = await client.chat.completions.create(**params)

                    async for chunk in stream:
                        if getattr(chunk, "usage", None):
                            usage = chunk.usage
                            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                            completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                            prompt_details = getattr(usage, "prompt_tokens_details", None)
                            cached_tokens = (getattr(prompt_details, "cached_tokens", 0) or 0) if prompt_details else 0
                            usage_counts = {
                                "prompt_tokens": prompt_tokens,
                                "completion_tokens": completion_tokens,
                                "cached_tokens": cached_tokens,
                            }
                        if chunk.choices:
                            delta = chunk.choices[0].delta
                            if chunk.choices[0].finish_reason:
                                finish_reason = chunk.choices[0].finish_reason
                            if delta.content:
                                if not ttft_logged:
                                    ttft = time.monotonic() - stream_start
                                    log_fn = logger.warning if ttft > 10 else logger.info
                                    log_fn(f"LLM ask_stream() TTFT={ttft:.1f}s (model={effective_model})")
                                    ttft_logged = True
                                completion_parts.append(delta.content)
                                yield delta.content
                            if delta.tool_calls:
                                logger.warning(
                                    "ask_stream received tool_call chunks - tool calls are not "
                                    "supported in streaming mode. Use ask() for tool-calling requests."
                                )

                    stream_duration = time.monotonic() - stream_start
                    _slow = getattr(
                        get_settings(),
                        "llm_slow_stream_threshold",
                        get_settings().llm_slow_request_threshold,
                    )
                    if stream_duration > _slow * 2:
                        log_fn = logger.error
                    elif stream_duration > _slow:
                        log_fn = logger.warning
                    else:
                        log_fn = logger.info
                    log_fn(
                        f"LLM ask_stream() completed in {stream_duration:.1f}s "
                        f"(model={effective_model}, chars={len(''.join(completion_parts))})"
                    )

                    if usage_counts:
                        await self._record_usage_counts(
                            prompt_tokens=usage_counts["prompt_tokens"],
                            completion_tokens=usage_counts["completion_tokens"],
                            cached_tokens=usage_counts["cached_tokens"],
                        )
                    else:
                        await self._record_stream_usage(
                            request_messages,
                            "".join(completion_parts),
                            tools=tools,
                        )

                    normalized_finish_reason = finish_reason or "stop"
                    self._last_stream_metadata = {
                        "finish_reason": normalized_finish_reason,
                        "truncated": normalized_finish_reason == "length",
                        "provider": "openai",
                    }
                    if normalized_finish_reason == "length":
                        logger.warning("OpenAI streaming response truncated (finish_reason=length)")

                    # Record success using the key that was actually used for this request.
                    try:
                        _used_key = getattr(self, "_cached_client_key", None)
                        if _used_key:
                            self._key_pool.record_success(_used_key)
                    except Exception:
                        logger.debug("record_success failed", exc_info=True)

                    return

                except httpx.ReadTimeout:
                    # Provider stopped sending chunks for longer than the read timeout.
                    # If content was already streamed, treat as truncation (not fatal).
                    # The caller's delivery integrity gate handles truncation recovery.
                    stream_elapsed = time.monotonic() - stream_start
                    streamed_chars = sum(len(p) for p in completion_parts)
                    if completion_parts:
                        logger.warning(
                            "LLM ask_stream() read timeout after %.1fs — treating %d chars as truncated (model=%s)",
                            stream_elapsed,
                            streamed_chars,
                            effective_model,
                        )
                        self._last_stream_metadata = {
                            "finish_reason": "length",
                            "truncated": True,
                            "provider": "openai",
                            "error": "read_timeout_mid_stream",
                        }
                        # Don't raise — caller already has the partial content via earlier yields.
                        # Setting truncated=True triggers the continuation/retry logic.
                        return
                    else:
                        logger.error(
                            "LLM ask_stream() read timeout before any content (%.1fs, model=%s)",
                            stream_elapsed,
                            effective_model,
                        )
                        self._last_stream_metadata = {
                            "finish_reason": "error",
                            "truncated": False,
                            "provider": "openai",
                            "error": "read_timeout_no_content",
                        }
                        raise RuntimeError(
                            f"LLM stream read timeout after {stream_elapsed:.0f}s with no content (model={effective_model})"
                        ) from None

                except RateLimitError as e:
                    self._last_stream_metadata = {
                        "finish_reason": "error",
                        "truncated": False,
                        "provider": "openai",
                        "error": "rate_limit",
                    }
                    # Parse rate limit TTL and mark key exhausted
                    key = await self.get_api_key()
                    if key:
                        ttl = self._parse_openai_rate_limit(e)
                        await self._key_pool.mark_exhausted(key, ttl_seconds=ttl)
                        max_retries = getattr(self, "_max_retries", 3)
                        logger.warning(
                            f"OpenAI stream rate limit hit, rotating to next key (attempt {_attempt + 1}/{max_retries})"
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
                except (
                    Exception
                ) as e:  # Broad catch: dispatches across multi-provider errors; re-raises on final attempt
                    error_msg = str(e).lower()

                    # Check for authentication errors (401) and rotate keys
                    if "401" in error_msg or "unauthorized" in error_msg or "authentication" in error_msg:
                        self._last_stream_metadata = {
                            "finish_reason": "error",
                            "truncated": False,
                            "provider": "openai",
                            "error": "authentication_error",
                        }
                        key = await self.get_api_key()
                        if key:
                            await self._key_pool.mark_invalid(key)
                            max_retries = getattr(self, "_max_retries", 3)
                            logger.error(
                                f"OpenAI stream authentication error, rotating to next key (attempt {_attempt + 1}/{max_retries})"
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

                    if (
                        self._is_message_validation_error(e)
                        and not validation_recovery_attempted
                        and not completion_parts
                    ):
                        recovered_messages = self._build_validation_recovery_messages(base_messages)
                        if recovered_messages != base_messages:
                            validation_recovery_attempted = True
                            base_messages = recovered_messages
                            request_messages = recovered_messages
                            if enable_caching and self._cache_manager:
                                request_messages = self._cache_manager.prepare_messages_for_caching(request_messages)
                            logger.warning(
                                "ask_stream retrying once with simplified transcript after schema validation error"
                            )
                            continue

                    self._last_stream_metadata = {
                        "finish_reason": "error",
                        "truncated": False,
                        "provider": "openai",
                        "error": type(e).__name__,
                    }
                    if any(
                        term in error_msg
                        for term in [
                            "context_length_exceeded",
                            "maximum context length",
                            "too many tokens",
                            "max_tokens",
                            "context window",
                        ]
                    ):
                        raise TokenLimitExceededError(str(e)) from e
                    raise
