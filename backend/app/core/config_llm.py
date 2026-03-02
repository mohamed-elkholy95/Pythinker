"""LLM and embedding settings mixins.

Contains configuration for OpenAI-compatible APIs, Anthropic, Ollama, embeddings,
adaptive model routing, and LLM concurrency control.
"""


class LLMSettingsMixin:
    """LLM provider and model configuration."""

    # LLM Provider selection
    # "auto"      → auto-detect from API keys / model name / base URL (recommended)
    # "openai"    → OpenAI-compatible (OpenAI, OpenRouter, GLM-5, DeepSeek, etc.)
    # "anthropic" → Anthropic native API (Claude models)
    # "ollama"    → Local Ollama server
    # "universal" → alias for "auto"
    llm_provider: str = "auto"

    # OpenAI-compatible provider (default)
    # Works with OpenRouter, Kimi Code, DeepSeek, OpenAI, and other OpenAI-compatible APIs
    api_key: str | None = None
    api_key_2: str | None = None  # Fallback OpenAI/OpenRouter key #1
    api_key_3: str | None = None  # Fallback OpenAI/OpenRouter key #2
    api_base: str = "https://openrouter.ai/api/v1"

    # Model configuration
    # Qwen3-Coder-Next: 80B MoE (3B active), 262k context, $0.12/$0.75 per 1M tokens
    model_name: str = "qwen/qwen3-coder-next"
    temperature: float = 0.3  # Lower temperature for deterministic JSON responses
    max_tokens: int = 16000  # Output token limit per LLM call
    summarization_max_tokens: int = 32000  # Higher limit for report/summary generation

    # Ollama configuration
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Anthropic configuration (when LLM_PROVIDER=anthropic)
    anthropic_api_key: str | None = None
    anthropic_api_key_2: str | None = None  # Fallback Anthropic key #1
    anthropic_api_key_3: str | None = None  # Fallback Anthropic key #2
    anthropic_model_name: str = "claude-sonnet-4-20250514"

    # Instructor-based structured output validation
    # When enabled, uses the `instructor` library for Pydantic-validated JSON responses
    # with automatic retry on validation failure.  Falls back to manual parsing if
    # instructor is not installed.
    use_instructor_structured_output: bool = True

    # Adaptive Model Selection (DeepCode Integration Phase 1)
    # Enables dynamic model routing based on step complexity for cost optimization.
    # Works with any OpenAI-compatible provider (OpenRouter, DeepInfra, etc.).
    #
    # Recommended MoE presets (via OpenRouter):
    #   FAST:     openai/gpt-oss-120b       ($0.04/$0.19/M)  — 5.1B active, Apache 2.0
    #             xiaomi/mimo-v2-flash       ($0.09/$0.29/M)  — 15B active, hybrid-thinking
    #   BALANCED: deepseek/deepseek-chat     ($0.25/$0.38/M)  — 37B active, "thinking in tool-use"
    #             zhipu-ai/glm-4-air         ($0.30/$0.90/M)  — 90.6% tool-calling success
    #   POWERFUL: moonshotai/kimi-k2.5       ($0.60/$3.00/M)  — 32B active, Agent Swarm (100 sub-agents)
    #             deepseek/deepseek-chat-v3-0324-speciale ($0.40/$1.20/M)
    adaptive_model_selection_enabled: bool = False
    fast_model: str = ""  # Fast tier: summaries, simple transforms (empty = use model_name)
    balanced_model: str = ""  # Balanced tier: standard execution (empty = use model_name)
    powerful_model: str = ""  # Powerful tier: complex reasoning, architecture (empty = use model_name)

    # GLM Thinking Mode Control
    # GLM-5/4.7 enable "deep thinking" by default, adding latency.
    # Set to true to send thinking.type=disabled on every GLM API call.
    glm_disable_thinking: bool = True

    # ── LLM Provider Fallback Chain (Phase 3) ───────────────────────────────
    # Comma-separated ordered list of provider names to try when the primary
    # provider fails after exhausting retries.  Empty string = no fallback.
    llm_provider_fallback_chain: str = ""

    # ── Dynamic Context Window (Phase 5) ────────────────────────────────────
    # Override the auto-detected context window size (0 = use registry value).
    llm_context_window_override: int = 0


class EmbeddingSettingsMixin:
    """Embedding model configuration (separate from chat model)."""

    embedding_api_key: str | None = None  # Defaults to api_key if not set
    embedding_api_key_2: str | None = None  # Fallback OpenAI embedding key #1
    embedding_api_key_3: str | None = None  # Fallback OpenAI embedding key #2
    embedding_api_base: str = "https://api.openai.com/v1"  # OpenAI for embeddings
    embedding_model: str = "text-embedding-3-small"  # 1536 dimensions


class LLMTimeoutSettingsMixin:
    """LLM HTTP request timeout configuration."""

    # Total timeout for a single LLM HTTP request (connect + read + write).
    # Keep this bounded to prevent multi-minute step stalls.
    llm_request_timeout: float = 300.0

    # Duration (seconds) after which an LLM call is logged at WARNING instead of
    # INFO.  GLM-5 normal calls take 10-30s, so 45s avoids noisy warnings while
    # still flagging genuinely slow requests.
    llm_slow_request_threshold: float = 45.0

    # Optional hard timeout (seconds) applied to every LLM call via asyncio.wait_for.
    # Set to 0 to disable.
    llm_hard_call_timeout: float = 0.0

    # GLM-specific hard timeout (seconds). Set >0 to cap extreme tail latency on
    # GLM calls and force faster fallback paths; set 0 to disable.
    # Aligned with the GLM HTTP read timeout (90s) so tool-bearing requests
    # have enough headroom for JSON generation.
    llm_glm_hard_call_timeout: float = 90.0

    # Tool-enabled calls usually need concise JSON/function outputs; capping token
    # budget reduces slow turns and limits runaway verbose generations.
    # Set to 0 to disable this cap.
    llm_tool_max_tokens: int = 2048

    # Guardrail timeout for tool-enabled calls. This prevents multi-minute stalls
    # from slow providers during orchestration-heavy sessions.
    # GLM-5 p95 tool-call latency is ~75s under heavy context, so 90s base
    # lets the first attempt succeed most of the time.
    # With exponential backoff (90s → 180s → 300s cap), 3 attempts total
    # worst-case ~570s, safely under the 600s step wall-clock limit.
    # Set to 0 to disable.
    llm_tool_request_timeout: float = 90.0

    # Maximum retry attempts after a tool-call timeout before surfacing an error.
    # 2 retries = 3 total attempts with exponential backoff.
    llm_tool_timeout_max_retries: int = 2


class LLMConcurrencySettingsMixin:
    """LLM concurrency, token management, and semantic cache configuration."""

    # Phase 6: LLM Concurrency Control
    llm_max_concurrent: int = 20  # Maximum concurrent LLM API requests (scaled for multi-user)
    llm_queue_timeout: float = 120.0  # Timeout waiting in LLM queue (seconds)
    llm_concurrency_enabled: bool = True  # Enable LLM concurrency limiting
    token_budget_warn_threshold: float = 0.8  # Warn when budget reaches this utilization (0-1)

    # Token management optimization (Priority 4: reduce aggressive trimming)
    token_safety_margin: int = 2048  # Reduced from hardcoded 4096 - most responses under 2K
    token_early_warning_threshold: float = 0.60  # New early warning threshold
    token_critical_threshold: float = 0.80  # Raised from 0.70 to allow more context

    # ── Retry Budget (Phase 2) ───────────────────────────────────────────────
    # Maximum LLM retries per task (across all middleware layers).
    llm_retry_budget_per_task: int = 15
    # Maximum LLM retries per minute (token-bucket rate limit).
    llm_retry_budget_per_minute: int = 30

    # Semantic Cache configuration (Phase 3 Enhancement)
    semantic_cache_enabled: bool = False
    semantic_cache_threshold: float = 0.92  # Similarity threshold for cache hits
    semantic_cache_ttl_seconds: int = 3600  # 1 hour default TTL

    # LLM Tracing configuration (Phase 1 Enhancement)
    llm_tracing_provider: str = "none"  # "none", "langfuse", "langsmith", "otel"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
