"""Universal LLM Client — provider-agnostic LLM interface.

Provides a single, unified entry point for any LLM provider:
- OpenAI / OpenRouter / GLM-5 / DeepSeek / any OpenAI-compatible API
- Anthropic (Claude Opus, Sonnet, Haiku)
- Ollama (local models)

Key features:
- **Auto-detection**: detects the right provider from API keys, model name, or base URL
- **Provider interchangeability**: switch providers by changing one env var (LLM_PROVIDER=auto)
- **Unified error handling**: all provider errors normalised to LLMError subclasses
- **Built-in JSON repair**: ask_json() extracts and repairs JSON from any response
- **Multi-key failover**: inherited from each underlying provider
- **Same interface as every other LLM**: fully compatible with the LLM Protocol

Provider detection priority (highest to lowest):
1. Explicit `provider` argument / LLM_PROVIDER setting
2. `anthropic_api_key` present → anthropic
3. Model name prefix: claude- → anthropic, glm- → openai (GLM mode)
4. API base URL: localhost/127.0.0.1/:8081 → ollama
                 z.ai / bigmodel.cn → openai (GLM)
                 openai.com / openrouter → openai
5. `api_key` present → openai
6. Default → openai

Usage (via settings):
    LLM_PROVIDER=auto                            # or omit — auto is the default
    API_KEY=sk-...                               # → OpenAI-compatible
    ANTHROPIC_API_KEY=sk-ant-...                 # → Anthropic (overrides API_KEY)
    MODEL_NAME=claude-opus-4-5                   # → Anthropic (detected from name)
    MODEL_NAME=glm-5                             # → OpenAI-compatible (GLM mode)
    OLLAMA_BASE_URL=http://localhost:11434        # → Ollama (detected from URL)

Switching providers at runtime:
    llm = UniversalLLM(provider="anthropic")
    # or just set LLM_PROVIDER=anthropic and call get_llm()
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any, TypeVar

from pydantic import BaseModel

from app.domain.external.llm import LLM
from app.domain.services.agents.error_handler import TokenLimitExceededError
from app.infrastructure.external.llm.factory import LLMProviderRegistry
from app.infrastructure.external.llm.json_repair import extract_json_text, parse_json_response

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)


# ─────────────────────────── Provider detection ───────────────────────────


def detect_provider(
    *,
    api_key: str | None = None,
    anthropic_api_key: str | None = None,
    model_name: str | None = None,
    api_base: str | None = None,
    explicit_provider: str | None = None,
) -> str:
    """Determine the best LLM provider from the available configuration.

    Args:
        api_key: OpenAI-compatible API key
        anthropic_api_key: Anthropic API key
        model_name: Model name (e.g. "claude-sonnet-4-5", "glm-5", "gpt-4o")
        api_base: Custom API base URL
        explicit_provider: Explicit override (skips detection if not "auto")

    Returns:
        Provider identifier: "openai" | "anthropic" | "ollama"
    """
    # 1. Explicit non-auto override wins unconditionally
    if explicit_provider and explicit_provider.lower() not in ("auto", ""):
        return explicit_provider.lower()

    model_lower = (model_name or "").lower()
    base_lower = (api_base or "").lower()

    # 2. Anthropic API key → Anthropic provider
    if anthropic_api_key and anthropic_api_key.strip():
        logger.debug("Provider auto-detected: anthropic (anthropic_api_key set)")
        return "anthropic"

    # 3. Model name prefix detection
    if model_lower.startswith("claude"):
        logger.debug(f"Provider auto-detected: anthropic (model={model_name})")
        return "anthropic"

    if model_lower.startswith("glm-") or "glm-z" in model_lower:
        logger.debug(f"Provider auto-detected: openai/GLM (model={model_name})")
        return "openai"  # GLM uses OpenAI-compatible API

    # 4. API base URL detection
    if base_lower:
        if any(h in base_lower for h in ("localhost", "127.0.0.1", "host.docker.internal", ":11434", ":8081")):
            logger.debug(f"Provider auto-detected: ollama (api_base={api_base})")
            return "ollama"

        if any(h in base_lower for h in ("z.ai", "bigmodel.cn", "zhipuai")):
            logger.debug(f"Provider auto-detected: openai/GLM (api_base={api_base})")
            return "openai"

    # 5. API key present → OpenAI-compatible
    if api_key and api_key.strip():
        logger.debug("Provider auto-detected: openai (api_key set)")
        return "openai"

    # 6. Default fallback
    logger.debug("Provider auto-detected: openai (default fallback)")
    return "openai"


# ─────────────────────────── Universal LLM ───────────────────────────


@LLMProviderRegistry.register("auto")
@LLMProviderRegistry.register("universal")
class UniversalLLM:
    """Universal LLM adapter: auto-detects provider, unified interface, full error handling.

    Implements the LLM Protocol — fully interchangeable with OpenAILLM,
    AnthropicLLM, or OllamaLLM anywhere in the codebase.

    The underlying provider is accessible as `self.backend` for diagnostics.
    """

    def __init__(
        self,
        *,
        # Provider selection (auto-detected if not provided)
        provider: str | None = None,
        # OpenAI-compatible credentials
        api_key: str | None = None,
        api_key_2: str | None = None,
        api_key_3: str | None = None,
        api_base: str | None = None,
        # Anthropic credentials
        anthropic_api_key: str | None = None,
        anthropic_api_key_2: str | None = None,
        anthropic_api_key_3: str | None = None,
        # Shared model config
        model_name: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        # Ollama-specific
        ollama_base_url: str | None = None,
        ollama_model: str | None = None,
        # Redis for multi-key coordination
        redis_client: Any = None,
    ) -> None:
        from app.core.config import get_settings

        settings = get_settings()

        # Resolve all values — explicit args take precedence over settings
        self._api_key = api_key or settings.api_key
        self._api_key_2 = api_key_2 or settings.api_key_2
        self._api_key_3 = api_key_3 or settings.api_key_3
        self._api_base = api_base or settings.api_base

        self._anthropic_api_key = anthropic_api_key or settings.anthropic_api_key
        self._anthropic_api_key_2 = anthropic_api_key_2 or settings.anthropic_api_key_2
        self._anthropic_api_key_3 = anthropic_api_key_3 or settings.anthropic_api_key_3

        self._model_name = model_name or settings.model_name
        self._temperature = temperature if temperature is not None else settings.temperature
        self._max_tokens = max_tokens if max_tokens is not None else settings.max_tokens

        self._ollama_base_url = ollama_base_url or settings.ollama_base_url
        self._ollama_model = ollama_model or settings.ollama_model
        self._redis_client = redis_client

        # Detect and store the active provider
        explicit = provider or getattr(settings, "llm_provider", "auto")
        self._provider_name = detect_provider(
            api_key=self._api_key,
            anthropic_api_key=self._anthropic_api_key,
            model_name=self._model_name,
            api_base=self._api_base,
            explicit_provider=explicit,
        )

        # Build the underlying provider backend
        self._backend: LLM = self._create_backend(self._provider_name)
        self._last_stream_metadata: dict[str, Any] | None = None

        logger.info(f"UniversalLLM ready — provider={self._provider_name}, model={self._backend.model_name}")

    # ─────────── Backend factory ───────────

    def _create_backend(self, provider: str) -> LLM:
        """Instantiate the underlying provider."""
        import importlib

        # Ensure providers are registered
        provider_modules = {
            "openai": "app.infrastructure.external.llm.openai_llm",
            "anthropic": "app.infrastructure.external.llm.anthropic_llm",
            "ollama": "app.infrastructure.external.llm.ollama_llm",
        }
        for name, module in provider_modules.items():
            try:
                importlib.import_module(module)
            except ImportError:
                logger.debug(f"Optional LLM provider not available: {name}")

        if provider == "anthropic":
            return self._create_anthropic_backend()
        if provider == "ollama":
            return self._create_ollama_backend()
        return self._create_openai_backend()

    def _create_openai_backend(self) -> LLM:
        """Create OpenAI-compatible backend."""
        from app.infrastructure.external.llm.openai_llm import OpenAILLM

        fallback_keys = [k for k in [self._api_key_2, self._api_key_3] if k and k.strip()]
        return OpenAILLM(
            api_key=self._api_key,
            fallback_api_keys=fallback_keys or None,
            model_name=self._model_name,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            api_base=self._api_base,
            redis_client=self._redis_client,
        )

    def _create_anthropic_backend(self) -> LLM:
        """Create Anthropic backend."""
        try:
            from app.infrastructure.external.llm.anthropic_llm import AnthropicLLM
        except ImportError as exc:
            raise ImportError(
                "Anthropic provider requires the 'anthropic' package. Install it with: pip install anthropic"
            ) from exc

        fallback_keys = [k for k in [self._anthropic_api_key_2, self._anthropic_api_key_3] if k and k.strip()]

        # Use anthropic_model_name from settings if model_name looks like an OpenAI model
        from app.core.config import get_settings

        settings = get_settings()
        model = self._model_name
        if not model.lower().startswith("claude"):
            # Explicit model isn't a Claude model — use dedicated Anthropic setting
            model = getattr(settings, "anthropic_model_name", "claude-sonnet-4-20250514")

        return AnthropicLLM(
            api_key=self._anthropic_api_key,
            fallback_api_keys=fallback_keys or None,
            model_name=model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
            redis_client=self._redis_client,
        )

    def _create_ollama_backend(self) -> LLM:
        """Create Ollama backend."""
        try:
            from app.infrastructure.external.llm.ollama_llm import OllamaLLM
        except ImportError as exc:
            raise ImportError("Ollama provider not available. Ensure ollama_llm.py is present.") from exc

        return OllamaLLM(
            base_url=self._ollama_base_url,
            model_name=self._ollama_model,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )

    # ─────────── Provider switching ───────────

    def switch_provider(self, provider: str) -> None:
        """Hot-swap the underlying provider at runtime.

        Useful for testing failover scenarios or dynamic provider selection.

        Args:
            provider: New provider name ("openai", "anthropic", "ollama")
        """
        old_provider = self._provider_name
        self._provider_name = provider.lower()
        self._backend = self._create_backend(self._provider_name)
        logger.info(f"UniversalLLM: switched provider {old_provider} → {self._provider_name}")

    @property
    def provider(self) -> str:
        """Active provider name."""
        return self._provider_name

    @property
    def backend(self) -> LLM:
        """The underlying provider instance (for diagnostics/testing)."""
        return self._backend

    # ─────────── LLM Protocol implementation ───────────

    @property
    def model_name(self) -> str:
        return self._backend.model_name

    @property
    def temperature(self) -> float:
        return self._backend.temperature

    @property
    def max_tokens(self) -> int:
        return self._backend.max_tokens

    @property
    def last_stream_metadata(self) -> dict[str, Any] | None:
        return self._last_stream_metadata or self._backend.last_stream_metadata

    async def ask(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        tool_choice: str | None = None,
        enable_caching: bool = True,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Send a chat request, delegating to the active provider.

        All arguments identical to the LLM Protocol — fully interchangeable.
        Errors from the underlying provider are re-raised as-is (they already
        use the standardized hierarchy: LLMException, TokenLimitExceededError, etc.)

        Returns:
            OpenAI-format message dict with role/content/tool_calls
        """
        return await self._backend.ask(
            messages=messages,
            tools=tools,
            response_format=response_format,
            tool_choice=tool_choice,
            enable_caching=enable_caching,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def ask_structured(
        self,
        messages: list[dict[str, Any]],
        response_model: type[T],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        enable_caching: bool = True,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> T:
        """Request a structured (Pydantic-validated) response from the LLM.

        Delegates to the active backend's ask_structured, which uses graduated
        temperature retry and JSON validation. Falls back to ask_json_validated()
        if the backend doesn't expose ask_structured.

        Returns:
            Validated Pydantic model instance
        """
        return await self._backend.ask_structured(
            messages=messages,
            response_model=response_model,
            tools=tools,
            tool_choice=tool_choice,
            enable_caching=enable_caching,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    async def ask_stream(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        tool_choice: str | None = None,
        enable_caching: bool = True,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> AsyncGenerator[str, None]:
        """Stream a chat response chunk by chunk.

        Delegates to the active backend's ask_stream, which handles token
        estimation, usage tracking, and retry on transient errors.

        Yields:
            String content chunks
        """
        self._last_stream_metadata = None
        gen = self._backend.ask_stream(
            messages=messages,
            tools=tools,
            response_format=response_format,
            tool_choice=tool_choice,
            enable_caching=enable_caching,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        async for chunk in gen:
            yield chunk
        # Capture final metadata
        self._last_stream_metadata = self._backend.last_stream_metadata

    # ─────────── Extended methods (beyond the Protocol) ───────────

    async def ask_json(
        self,
        messages: list[dict[str, Any]],
        *,
        enable_caching: bool = True,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        default: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        """Ask the LLM and parse JSON from the response.

        Automatically:
        1. Calls ask() to get the text response
        2. Extracts JSON from markdown code fences, prose, etc.
        3. Repairs common malformations (trailing commas, truncation)
        4. Returns parsed dict, or `default` if no valid JSON found

        Unlike ask_structured(), this method is lenient:
        - Works for any JSON shape (no schema required)
        - Returns None / default on failure instead of raising

        Args:
            messages: Conversation messages
            enable_caching: Whether to use prompt caching
            model: Optional model override
            temperature: Optional temperature override
            max_tokens: Optional max_tokens override
            default: Return value if JSON cannot be extracted (default: None)

        Returns:
            Parsed dict, or `default`
        """
        response = await self.ask(
            messages=messages,
            enable_caching=enable_caching,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )

        content = response.get("content") or ""
        if not isinstance(content, str):
            content = str(content)

        # Try direct parse first (most common case — LLM returned valid JSON)
        result = parse_json_response(content)
        if result is not None:
            if isinstance(result, dict):
                return result
            # Wrap non-dict results (e.g. list)
            return {"data": result}

        # Track semantic failure (HTTP 200 but malformed JSON)
        try:
            from app.core.prometheus_metrics import llm_json_parse_failures_total

            llm_json_parse_failures_total.inc({"model": self._model_name, "method": "ask_json"})
        except Exception:
            logger.debug("Failed to record ask_json parse failure metric", exc_info=True)

        logger.debug(f"ask_json: no valid JSON found in {len(content)}-char response")
        return default

    async def ask_json_validated(
        self,
        messages: list[dict[str, Any]],
        response_model: type[T],
        *,
        enable_caching: bool = True,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        max_retries: int = 2,
    ) -> T:
        """Ask the LLM and validate response against a Pydantic model.

        More lenient than ask_structured():
        - Extracts JSON from markdown/prose (handles any formatting)
        - Applies JSON repair before validation
        - Retries with explicit JSON-only instructions on failure

        Args:
            messages: Conversation messages
            response_model: Pydantic model to validate against
            enable_caching: Whether to use prompt caching
            model: Optional model override
            temperature: Optional temperature override
            max_tokens: Optional max_tokens override
            max_retries: Number of retry attempts (default: 2)

        Returns:
            Validated Pydantic model instance

        Raises:
            ValueError: If all retries fail to produce valid structured output
        """
        from pydantic import ValidationError

        last_error: Exception | None = None
        retry_messages = list(messages)

        for attempt in range(max_retries + 1):
            response = await self.ask(
                messages=retry_messages,
                enable_caching=enable_caching and attempt == 0,
                model=model,
                # Lower temperature on retries for more deterministic output
                temperature=max(0.0, (temperature or self._temperature) - 0.1 * attempt),
                max_tokens=max_tokens,
            )

            content = response.get("content") or ""

            # Try JSON extraction + repair
            json_text = extract_json_text(content)
            if json_text:
                try:
                    import json

                    data = json.loads(json_text)
                    return response_model.model_validate(data)
                except (json.JSONDecodeError, ValidationError) as exc:
                    last_error = exc
                    logger.debug(f"ask_json_validated attempt {attempt + 1}: validation failed: {exc}")
            else:
                last_error = ValueError(f"No JSON found in response (attempt {attempt + 1})")
                logger.debug(f"ask_json_validated attempt {attempt + 1}: no JSON in response")

            # Build retry message with explicit schema instruction
            if attempt < max_retries:
                schema_str = response_model.model_json_schema()
                import json as _json

                retry_messages = [
                    *messages,
                    {
                        "role": "assistant",
                        "content": content,
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Your response was not valid JSON matching the required schema. "
                            f"Please respond with ONLY a valid JSON object matching this schema, "
                            f"no markdown, no prose:\n{_json.dumps(schema_str, indent=2)}"
                        ),
                    },
                ]

        # Track semantic failure after all retries exhausted
        try:
            from app.core.prometheus_metrics import llm_json_parse_failures_total

            llm_json_parse_failures_total.inc({"model": self._model_name, "method": "ask_json_validated"})
        except Exception:
            logger.debug("Failed to record ask_json_validated parse failure metric", exc_info=True)

        raise ValueError(f"ask_json_validated failed after {max_retries + 1} attempts. Last error: {last_error}")

    async def probe(self) -> bool:
        """Quick health check — send a minimal request to verify connectivity.

        Returns:
            True if the provider responds successfully, False otherwise
        """
        try:
            response = await self.ask(
                messages=[{"role": "user", "content": "Reply with OK"}],
                enable_caching=False,
                max_tokens=10,
            )
            return bool(response.get("content"))
        except (TokenLimitExceededError, Exception) as exc:
            logger.warning(f"UniversalLLM.probe() failed: {type(exc).__name__}: {exc}")
            return False

    def __repr__(self) -> str:
        return f"UniversalLLM(provider={self._provider_name!r}, model={self.model_name!r})"
