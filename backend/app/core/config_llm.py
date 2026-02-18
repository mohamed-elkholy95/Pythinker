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
    # Works with OpenRouter, DeepSeek, OpenAI, and other OpenAI-compatible APIs
    api_key: str | None = None
    api_key_2: str | None = None  # Fallback OpenAI/OpenRouter key #1
    api_key_3: str | None = None  # Fallback OpenAI/OpenRouter key #2
    api_base: str = "https://openrouter.ai/api/v1"

    # Model configuration
    # NVIDIA Nemotron 3 Nano 30B A3B: 30B MoE (3B active), 262k context, agentic AI optimized
    model_name: str = "nvidia/nemotron-3-nano-30b-a3b"
    temperature: float = 0.3  # Lower temperature for deterministic JSON responses
    max_tokens: int = 16000  # Output token limit per LLM call

    # Ollama configuration
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Anthropic configuration (when LLM_PROVIDER=anthropic)
    anthropic_api_key: str | None = None
    anthropic_api_key_2: str | None = None  # Fallback Anthropic key #1
    anthropic_api_key_3: str | None = None  # Fallback Anthropic key #2
    anthropic_model_name: str = "claude-sonnet-4-20250514"

    # Adaptive Model Selection (DeepCode Integration Phase 1)
    # Enables dynamic model routing based on step complexity for cost optimization
    adaptive_model_selection_enabled: bool = False
    fast_model: str = "claude-haiku-4-5"  # Fast tier: summaries, simple transforms, status checks
    balanced_model: str = ""  # Balanced tier: standard execution (empty = use model_name)
    powerful_model: str = "claude-sonnet-4-5"  # Powerful tier: complex reasoning, architecture


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
    # Generous default (300s / 5 min) because some providers (e.g. glm-4.7 via
    # OpenRouter) can take 60-120s for a single completion.  The connect timeout
    # is hardcoded to 10s inside the client factory so unreachable servers fail
    # fast while slow-but-alive providers get the full budget.
    llm_request_timeout: float = 300.0


class LLMConcurrencySettingsMixin:
    """LLM concurrency, token management, and semantic cache configuration."""

    # Phase 6: LLM Concurrency Control
    llm_max_concurrent: int = 5  # Maximum concurrent LLM API requests
    llm_queue_timeout: float = 120.0  # Timeout waiting in LLM queue (seconds)
    llm_concurrency_enabled: bool = True  # Enable LLM concurrency limiting
    token_budget_warn_threshold: float = 0.8  # Warn when budget reaches this utilization (0-1)

    # Token management optimization (Priority 4: reduce aggressive trimming)
    token_safety_margin: int = 2048  # Reduced from hardcoded 4096 - most responses under 2K
    token_early_warning_threshold: float = 0.60  # New early warning threshold
    token_critical_threshold: float = 0.80  # Raised from 0.70 to allow more context

    # Semantic Cache configuration (Phase 3 Enhancement)
    semantic_cache_enabled: bool = False
    semantic_cache_threshold: float = 0.92  # Similarity threshold for cache hits
    semantic_cache_ttl_seconds: int = 3600  # 1 hour default TTL

    # LLM Tracing configuration (Phase 1 Enhancement)
    llm_tracing_provider: str = "none"  # "none", "langfuse", "langsmith", "otel"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"
