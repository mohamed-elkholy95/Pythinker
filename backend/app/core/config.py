import logging
import secrets
import warnings
from enum import Enum
from functools import lru_cache
from typing import ClassVar

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class FlowMode(str, Enum):
    """Unified flow engine selection.

    Controls which execution flow is used for agent tasks.
    Replaces the legacy enable_coordinator boolean.
    """

    PLAN_ACT = "plan_act"  # Default: custom PlanActFlow
    COORDINATOR = "coordinator"  # Swarm coordinator mode


logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    _emitted_security_warnings: ClassVar[set[str]] = set()
    _startup_banner_emitted: ClassVar[bool] = False

    # Environment configuration
    environment: str = "development"  # "development", "staging", "production"
    debug: bool = False

    # Language configuration
    default_language: str = "English"  # Default language for agent responses

    # LLM Provider selection
    llm_provider: str = "openai"  # "openai", "ollama"

    # OpenAI-compatible provider configuration (default)
    # Works with OpenRouter, DeepSeek, OpenAI, and other OpenAI-compatible APIs
    api_key: str | None = None
    api_base: str = "https://openrouter.ai/api/v1"

    # Model configuration
    # NVIDIA Nemotron 3 Nano 30B A3B: 30B MoE (3B active), 262k context, agentic AI optimized
    model_name: str = "nvidia/nemotron-3-nano-30b-a3b"
    temperature: float = 0.3  # Lower temperature for deterministic JSON responses
    max_tokens: int = 16000  # Output token limit per LLM call (needs to be high enough for research synthesis)

    # Ollama configuration
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Anthropic configuration (when LLM_PROVIDER=anthropic)
    anthropic_api_key: str | None = None
    anthropic_model_name: str = "claude-sonnet-4-20250514"

    # Embedding configuration (separate from chat model)
    embedding_api_key: str | None = None  # Defaults to api_key if not set
    embedding_api_base: str = "https://api.openai.com/v1"  # OpenAI for embeddings
    embedding_model: str = "text-embedding-3-small"  # 1536 dimensions

    # MongoDB configuration
    mongodb_uri: str = "mongodb://mongodb:27017"
    mongodb_database: str = "pythinker"
    mongodb_username: str | None = None
    mongodb_password: str | None = None
    # MongoDB connection pooling and timeouts
    mongodb_max_pool_size: int = 100  # Max connections in pool
    mongodb_min_pool_size: int = 10  # Min connections to maintain
    mongodb_max_idle_time_ms: int = 30000  # 30s idle timeout
    mongodb_connect_timeout_ms: int = 10000  # 10s connection timeout
    mongodb_server_selection_timeout_ms: int = 30000  # 30s server selection timeout
    mongodb_socket_timeout_ms: int = 20000  # 20s socket timeout

    # Redis configuration
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None
    # Redis connection pooling and timeouts
    redis_max_connections: int = 50  # Max connections in pool
    redis_socket_timeout: float = 30.0  # 30s socket timeout for long-running operations like xread
    redis_socket_connect_timeout: float = 5.0  # 5s connection timeout
    redis_health_check_interval: int = 30  # 30s health check interval
    redis_retry_on_timeout: bool = True  # Retry on timeout

    # MinIO S3 Object Storage configuration
    # Credentials MUST be provided via environment variables (no hardcoded secrets)
    minio_endpoint: str = "minio:9000"
    minio_access_key: str  # Required: set MINIO_ACCESS_KEY in .env
    minio_secret_key: str  # Required: set MINIO_SECRET_KEY in .env
    minio_bucket_name: str = "pythinker"
    minio_use_ssl: bool = False
    minio_region: str = "us-east-1"
    minio_presigned_expiry_seconds: int = 3600  # 1 hour default
    file_storage_backend: str = "minio"  # "minio" | "gridfs"

    # Qdrant Vector Database configuration
    qdrant_url: str = "http://qdrant:6333"
    qdrant_grpc_port: int = 6334
    qdrant_prefer_grpc: bool = True  # 2x faster than REST
    qdrant_collection: str = "agent_memories"  # Legacy collection (deprecated, use user_knowledge)
    qdrant_api_key: str | None = None

    # Multi-collection configuration (Phase 1: Named vectors with dense + sparse hybrid search)
    qdrant_user_knowledge_collection: str = "user_knowledge"  # Primary memory collection
    qdrant_task_artifacts_collection: str = "task_artifacts"
    qdrant_tool_logs_collection: str = "tool_logs"

    # Phase 1: Hybrid search feature flags
    qdrant_use_hybrid_search: bool = True  # Enable dense+sparse hybrid retrieval (RRF fusion)
    qdrant_sparse_vector_enabled: bool = True  # Generate BM25 sparse vectors

    # Sandbox configuration
    sandbox_lifecycle_mode: str = "static"  # "static" | "ephemeral"
    sandbox_address: str | None = None
    sandbox_image: str | None = None
    sandbox_name_prefix: str | None = None
    sandbox_ttl_minutes: int | None = 60  # Extended session: 60 min for long-running tasks
    sandbox_network: str | None = None  # Docker network bridge name
    sandbox_chrome_args: str | None = ""
    sandbox_https_proxy: str | None = None
    sandbox_http_proxy: str | None = None
    sandbox_no_proxy: str | None = None
    sandbox_seccomp_profile: str | None = None
    sandbox_seccomp_profile_mode: str = "compat"  # compat | hardened; default compat (Phase A)
    security_critic_allow_medium_risk: bool = False  # Allow MEDIUM risk in dev; default block
    sandbox_shm_size: str | None = "2g"  # Playwright/Selenium: 2GB prevents Chrome /dev/shm OOM (Context7)
    sandbox_mem_limit: str | None = "4g"  # Increased from 3g to reduce OOM kills (Priority 3)
    sandbox_cpu_limit: float | None = 1.5  # 2 containers x 1.5 CPU = 3 cores, leaves room for services
    sandbox_pids_limit: int | None = 300  # Sufficient for Chrome + Node + Python + supervisor
    sandbox_framework_port: int = 8082
    sandbox_framework_enabled: bool = True
    sandbox_framework_required: bool = False

    # Phase 3: HTTP/2 Configuration
    sandbox_http2_enabled: bool = False  # Enable HTTP/2 for sandbox API communication (requires httpx[http2])

    # Session initialization optimization (Phase 1-5)
    sandbox_cdp_initial_delay: float = 0.5  # Initial delay for CDP retry backoff
    sandbox_cdp_max_delay: float = 2.0  # Maximum delay for CDP retry backoff
    sandbox_cdp_retries: int = 10  # Number of CDP connection retries
    sandbox_eager_init: bool = True  # Start sandbox creation on session create
    workspace_lazy_init: bool = True  # Defer workspace init until needed

    # Sandbox warmup race condition fix (Phase 6)
    sandbox_warmup_grace_period: float = 3.0  # Wait before first health check to avoid race condition
    sandbox_warmup_initial_retry_delay: float = 1.0  # Initial delay between retries
    sandbox_warmup_max_retry_delay: float = 3.0  # Maximum delay between retries
    sandbox_warmup_backoff_multiplier: float = 1.5  # Exponential backoff multiplier
    sandbox_warmup_connection_failure_threshold: int = 12  # Max connection failures before giving up

    # Sandbox Pool Pre-warming (Phase 3)
    sandbox_pool_enabled: bool = True  # Enable sandbox pool for instant allocation (20-32s → 2-5s cold start)
    sandbox_pool_min_size: int = 1  # Pre-warm 1 sandbox, create 2nd on demand (saves ~3GB idle RAM)
    sandbox_pool_max_size: int = 2  # Cap at 2 for 2-concurrent-task target
    sandbox_pool_warmup_interval: int = 30  # Seconds between pool maintenance checks

    # Sandbox idle management (optimized for 2 concurrent tasks)
    sandbox_pool_idle_ttl_seconds: int = 300  # Evict pooled sandbox after 5 min idle
    sandbox_pool_pause_idle: bool = True  # Docker pause idle pooled sandboxes to reclaim CPU
    sandbox_pool_host_memory_threshold: float = 0.80  # Stop pre-warming at 80% host RAM

    # Sandbox lifecycle optimization
    sandbox_pool_reaper_interval: int = 60  # Orphan reaper check interval (seconds)
    sandbox_pool_reaper_grace_period: int = 120  # Don't reap containers younger than this (seconds)

    # Sandbox health monitoring (Priority 3: proactive crash detection)
    sandbox_health_check_interval: int = 30  # Continuous health check interval (seconds)
    sandbox_oom_monitor_enabled: bool = True  # Monitor Docker events for OOM kills
    sandbox_runtime_crash_recovery: bool = True  # Automatically replace crashed sandboxes

    # Lazy initialization (Phase 5)
    mcp_lazy_init: bool = True  # Defer MCP initialization until first use

    # Search engine configuration
    search_provider: str | None = "duckduckgo"  #  "google", "bing", "duckduckgo", "brave", "tavily", "serper"
    search_prefer_browser: bool = (
        False  # API search is faster and more reliable; browser search only useful for sandbox VNC visibility
    )
    google_search_api_key: str | None = None
    google_search_engine_id: str | None = None
    brave_search_api_key: str | None = None  # Brave Search API key
    tavily_api_key: str | None = None  # Tavily AI Search API key (https://tavily.com)
    tavily_api_key_2: str | None = None  # Fallback Tavily key (auto-rotates on quota/billing errors)
    tavily_api_key_3: str | None = None  # Third fallback Tavily key
    tavily_api_key_4: str | None = None  # Fourth fallback Tavily key
    tavily_api_key_5: str | None = None  # Fifth fallback Tavily key
    tavily_api_key_6: str | None = None  # Sixth fallback Tavily key
    tavily_api_key_7: str | None = None  # Seventh fallback Tavily key
    tavily_api_key_8: str | None = None  # Eighth fallback Tavily key
    tavily_api_key_9: str | None = None  # Ninth fallback Tavily key
    serper_api_key: str | None = None  # Serper.dev Google Search API key (free tier: 2500 queries/mo)
    serper_api_key_2: str | None = None  # Fallback Serper key (auto-rotates on quota/billing errors)
    serper_api_key_3: str | None = None  # Third fallback Serper key

    # Browser Agent configuration
    browser_agent_enabled: bool = True
    browser_agent_max_steps: int = 25
    browser_agent_timeout: int = 300
    browser_agent_use_vision: bool = True
    browser_agent_max_failures: int = 5  # Max retries for failed steps
    browser_agent_llm_timeout: int = 90  # Timeout for LLM calls in seconds
    browser_agent_step_timeout: int = 120  # Timeout per step in seconds
    browser_agent_flash_mode: bool = False  # Fast mode skips thinking (less reliable)

    # Anti-Bot / Stealth Configuration (Enhancement Phase 2.4)
    browser_stealth_enabled: bool = True  # Enable stealth mode for navigation
    browser_stealth_mode: str = "basic"  # "basic", "advanced"
    browser_human_delays: bool = True  # Add random human-like delays
    browser_cloudflare_bypass: bool = False  # Enable Cloudflare challenge bypass
    browser_recaptcha_solver: str | None = None  # "anticaptcha", "2captcha"
    browser_recaptcha_api_key: str | None = None  # API key for CAPTCHA solving service
    browser_proxy_url: str | None = None  # HTTP/SOCKS proxy for browser connections
    browser_ignore_https_errors: bool | None = None  # None = auto (True in dev, False in prod)
    browser_allow_dangerous_js: bool = False  # Allow dangerous JavaScript execution (SECURITY RISK)

    # Chrome for Testing (sandbox uses 128.0.6613.137 on Ubuntu 22.04)
    browser_chrome_executable_path: str | None = (
        None  # Override path (default: /opt/chrome-for-testing/chrome in sandbox)
    )
    browser_chrome_version: str = "128.0.6613.137"  # Matches Chrome for Testing in sandbox Dockerfile

    # Browser Hardening Configuration
    browser_skip_video_urls: bool = True  # Skip video sites (YouTube, Vimeo, etc.)
    browser_auto_dismiss_dialogs: bool = True  # Auto-dismiss popups, alerts, confirms
    browser_show_cursor: bool = True  # Show visual cursor indicator for agent actions

    # Browser HTTP Fetch Configuration (P3.1: faster failure detection)
    browser_fetch_timeout: float = 15.0  # Total timeout for HTTP fetch (reduced from 30s)
    browser_fetch_connect_timeout: float = 5.0  # Connection timeout (reduced from 10s)

    # Browser Connection Pool Configuration (Phase 3: connection reuse)
    browser_pool_enabled: bool = True  # Enable browser connection pooling
    browser_pool_max_per_url: int = 16  # Max connections per CDP URL (sessions hold long-lived connections)
    browser_pool_timeout: float = 30.0  # Timeout waiting for available connection
    browser_pool_max_idle: float = 300.0  # Max idle time before cleanup (5 min)
    browser_pool_health_interval: float = 60.0  # Health check interval (1 min)
    browser_init_timeout: float = 60.0  # Overall timeout for browser initialization (seconds)

    # Browser element extraction configuration (Phase 6: fix timeouts)
    browser_element_extraction_timeout: float = (
        5.0  # Timeout for interactive element extraction (seconds) - reduced from 7.0 to match JS timeout
    )
    browser_element_extraction_retries: int = 2  # Number of retries for element extraction
    browser_element_extraction_retry_delay: float = 1.0  # Delay between retries (seconds)
    browser_element_extraction_cache_ttl: float = (
        15.0  # Cache TTL for extracted elements (seconds) - increased from 10.0
    )

    # Browser crash prevention (Priority 1: fix Wikipedia crashes)
    browser_graceful_degradation: bool = True  # Return partial results instead of failing on browser crash
    browser_memory_auto_restart: bool = True  # Proactively restart browser on memory pressure
    browser_memory_critical_threshold_mb: int = 800  # Restart trigger threshold
    browser_memory_high_threshold_mb: int = 500  # Warning level threshold
    browser_wikipedia_lightweight_mode: bool = True  # Special handling for Wikipedia pages

    # Heavy page detection (Priority 1: proactive detection before expensive operations)
    browser_heavy_page_html_size_threshold: int = 5_000_000  # 5MB HTML size triggers lightweight mode
    browser_heavy_page_dom_threshold: int = 3000  # DOM element count triggers lightweight mode
    browser_heavy_page_skip_scroll: bool = True  # Skip smart scroll on heavy pages

    # Fast acknowledgment refiner configuration (Phase 6: fix timeouts)
    fast_ack_refiner_timeout: float = 2.5  # LLM timeout for fast acknowledgment generation (seconds)
    fast_ack_refiner_traceback_sample_rate: float = 0.05  # Sample rate for error traceback logging

    # Screenshot capture configuration (session replay)
    screenshot_capture_enabled: bool = True
    screenshot_periodic_interval: float = 10.0  # seconds between periodic captures
    screenshot_quality: int = 75  # JPEG quality for full-res (1-100)
    screenshot_scale: float = 0.5  # Scale factor for full-res
    screenshot_thumbnail_quality: int = 40  # JPEG quality for thumbnails
    screenshot_thumbnail_scale: float = 0.25  # Scale factor for thumbnails

    # MinIO screenshot-specific buckets (uses shared MinIO config from above)
    minio_screenshots_bucket: str = "screenshots"
    minio_thumbnails_bucket: str = "thumbnails"

    # Screenshot deduplication
    screenshot_dedup_enabled: bool = True
    screenshot_dedup_threshold: int = 5  # Hamming distance (0=exact match, 64=all different)

    # WebP thumbnails
    screenshot_thumbnail_webp_enabled: bool = True
    screenshot_thumbnail_webp_quality: int = 75

    # Screenshot resilience (Priority 2: prevent HTTP pool exhaustion)
    screenshot_circuit_breaker_enabled: bool = True  # Enable circuit breaker
    screenshot_max_consecutive_failures: int = 5  # Open circuit after N failures
    screenshot_circuit_recovery_seconds: int = 60  # Time before retry
    screenshot_http_max_connections: int = 50  # Dedicated pool size (increased from default)
    screenshot_http_pool_timeout: float = 30.0  # Pool wait timeout
    screenshot_http_retry_attempts: int = 3  # Retry on failure
    screenshot_http_retry_delay: float = 2.0  # Initial retry delay (exponential backoff)

    # Stuck Detection Configuration (P3.2/P3.3: faster loop detection)
    stuck_detection_window: int = 5  # Response window size (reduced from 10)
    stuck_detection_threshold: int = 3  # Threshold for stuck detection (reduced from 5)
    browser_loop_detection_count: int = 2  # Same-URL navigations before flagging (reduced from 3)

    # Auth configuration
    auth_provider: str = "password"  # "password", "none", "local"
    password_salt: str | None = None
    password_hash_rounds: int = 600000  # OWASP recommendation for PBKDF2-SHA256
    password_hash_algorithm: str = "pbkdf2_sha256"
    password_min_length: int = 12  # Minimum password length
    password_require_uppercase: bool = True
    password_require_lowercase: bool = True
    password_require_digit: bool = True
    password_require_special: bool = False  # Optional special character
    local_auth_email: str | None = None  # Must be set via environment
    local_auth_password: str | None = None  # Must be set via environment

    # Account lockout configuration
    account_lockout_enabled: bool = True
    account_lockout_threshold: int = 5  # Failed attempts before lockout
    account_lockout_duration_minutes: int = 15  # Lockout duration
    account_lockout_reset_minutes: int = 60  # Reset failed attempts counter after

    # Email configuration
    email_host: str | None = None  # "smtp.gmail.com"
    email_port: int | None = None  # 587
    email_username: str | None = None
    email_password: str | None = None
    email_from: str | None = None
    rating_notification_email: str | None = None

    # JWT configuration
    jwt_secret_key: str | None = None  # REQUIRED - must be set via environment
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    jwt_token_blacklist_enabled: bool = True  # Enable token revocation

    # CORS configuration
    cors_origins: str = (
        ""  # Comma-separated list of allowed origins (e.g., "http://localhost:5173,https://app.example.com")
    )
    cors_allow_credentials: bool = True
    cors_allow_methods: str = "GET,POST,PUT,DELETE,OPTIONS,PATCH"
    cors_allow_headers: str = "Authorization,Content-Type,X-Request-ID"

    # Rate limiting configuration
    rate_limit_enabled: bool = True
    rate_limit_requests_per_minute: int = 300  # Increased for SSE polling (temporary)
    rate_limit_auth_requests_per_minute: int = 10  # Rate limit for auth endpoints (login, register)
    rate_limit_burst: int = 10  # Allow burst of requests

    # MCP configuration
    mcp_config_path: str = "/etc/mcp.json"

    # Logging configuration
    log_level: str = "INFO"
    log_redaction_enabled: bool = True
    # Comma-separated list of keys to redact in logs (case-insensitive)
    log_redaction_keys: str = (
        "api_key,apikey,access_token,refresh_token,token,password,secret,authorization,cookie,set-cookie"
    )
    log_redaction_max_depth: int = 6

    # Alerting configuration (optional)
    alert_webhook_url: str | None = None
    alert_webhook_timeout_seconds: float = 3.0
    alert_throttle_seconds: int = 60

    # OpenTelemetry configuration (optional)
    otel_enabled: bool = False
    otel_endpoint: str | None = None  # e.g., "http://localhost:4317"
    otel_service_name: str = "pythinker-agent"
    otel_insecure: bool = True  # Use insecure connection (no TLS)

    # LLM Tracing configuration (Phase 1 Enhancement)
    llm_tracing_provider: str = "none"  # "none", "langfuse", "langsmith", "otel"
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str = "https://cloud.langfuse.com"

    # Semantic Cache configuration (Phase 3 Enhancement)
    semantic_cache_enabled: bool = False
    semantic_cache_threshold: float = 0.92  # Similarity threshold for cache hits
    semantic_cache_ttl_seconds: int = 3600  # 1 hour default TTL

    # Multi-Agent Orchestration configuration
    enable_multi_agent: bool = True  # Enable specialized agent dispatch per step
    enable_coordinator: bool = False  # Deprecated: use flow_mode instead
    multi_agent_max_parallel: int = 3  # Max concurrent agents in swarm mode

    # Parallel Step Execution configuration (Phase 4)
    enable_parallel_execution: bool = False  # Execute independent steps in parallel
    parallel_max_concurrency: int = 3  # Max concurrent step executions

    # Plan Verification configuration (Performance optimization)
    enable_plan_verification: bool = True  # Verify plan feasibility before execution

    # Advanced reasoning features (disabled by default, enable per-use-case)
    feature_tree_of_thoughts: bool = False  # Use ToT exploration for complex planning
    feature_self_consistency: bool = False  # Use self-consistency checks during verification

    # Skill activation policy
    skill_auto_trigger_enabled: bool = False  # Default OFF: explicit activation only (chat selection or /command)

    # Unified flow engine selection (replaces legacy booleans)
    flow_mode: FlowMode = FlowMode.PLAN_ACT

    @computed_field
    @property
    def resolved_flow_mode(self) -> FlowMode:
        """Resolve flow mode from new field or legacy booleans.

        Priority: flow_mode (if explicitly set) > enable_coordinator > PLAN_ACT.
        """
        if self.flow_mode != FlowMode.PLAN_ACT:
            return self.flow_mode
        if self.enable_coordinator:
            return FlowMode.COORDINATOR
        return FlowMode.PLAN_ACT

    @computed_field
    @property
    def uses_static_sandbox_addresses(self) -> bool:
        """Whether sandboxes are configured as pre-existing static addresses."""
        if self.sandbox_lifecycle_mode == "ephemeral":
            return False
        return bool(self.sandbox_address and self.sandbox_address.strip())

    # Agent Enhancement Feature Flags (Phase 0+)
    feature_plan_validation_v2: bool = False
    feature_reflection_advanced: bool = False
    feature_context_optimization: bool = False
    feature_tool_tracing: bool = False
    feature_reward_hacking_detection: bool = False
    feature_failure_prediction: bool = False
    feature_circuit_breaker_adaptive: bool = False
    feature_workflow_checkpointing: bool = False
    feature_shadow_mode: bool = True

    # Hallucination Prevention Feature Flags (Phase 1-6)
    feature_url_verification: bool = True  # Verify cited URLs exist and were visited
    feature_claim_provenance: bool = True  # Track claim-to-source linkage
    feature_enhanced_grounding: bool = True  # Numeric/entity verification in sources
    feature_cove_verification: bool = True  # Chain-of-Verification for reports
    feature_semantic_citation_validation: bool = True  # Semantic matching for citations
    feature_strict_numeric_verification: bool = True  # Reject unverified numeric claims
    feature_reject_ungrounded_reports: bool = False  # Start permissive, can enable later
    feature_delivery_integrity_gate: bool = True  # Enforce truncation/completeness gate before delivery

    # Adaptive Verbosity + Clarification (2026-02-09 plan)
    # When True: run policy engine, log proposed mode/clarification, but skip clarification gate and use standard output
    feature_adaptive_verbosity_shadow: bool = False

    # Chart Generation (Plotly Migration Phase 4)
    feature_plotly_charts_enabled: bool = True  # Use Plotly charts instead of SVG (Phase 4)

    # Autonomy Configuration (Enhancement Phase 1)
    autonomy_level: str = "guided"  # supervised, guided, autonomous, unrestricted
    allow_credential_access: bool = True
    allow_external_requests: bool = True
    allow_file_system_write: bool = True
    allow_file_system_delete: bool = False  # Disabled by default for safety
    allow_shell_execute: bool = True
    allow_browser_navigation: bool = True
    allow_payment_operations: bool = False  # Disabled by default

    # Agent Enhancement Feature Flags (Phases 1-5)
    # Phase 1: Python 3.11+ TaskGroup Migration
    feature_taskgroup_enabled: bool = False  # Use TaskGroup instead of asyncio.gather
    # Phase 2: SSE Streaming v2
    feature_sse_v2: bool = False  # Enhanced streaming API with structured events
    # Phase 3: Zero-Hallucination Defense
    feature_structured_outputs: bool = False  # Pydantic structured LLM outputs with validation
    # Phase 4: Parallel Memory Architecture
    feature_parallel_memory: bool = False  # Parallel MongoDB/Qdrant memory writes

    # Safety Limits
    max_iterations: int = 400  # Maximum loop iterations per run (doubled for complex tasks)
    max_tool_calls: int = 500  # Maximum tool invocations per run (increased for codebase analysis)
    max_execution_time_seconds: int = 3600  # 60 minutes for complex tasks
    max_tokens_per_run: int = 500000  # Token limit across all LLM calls
    max_cost_usd: float | None = None  # Optional cost limit

    # Phase 6: LLM Concurrency Control
    llm_max_concurrent: int = 5  # Maximum concurrent LLM API requests
    llm_queue_timeout: float = 120.0  # Timeout waiting in LLM queue (seconds)
    llm_concurrency_enabled: bool = True  # Enable LLM concurrency limiting
    token_budget_warn_threshold: float = 0.8  # Warn when budget reaches this utilization (0-1)

    # Token management optimization (Priority 4: reduce aggressive trimming)
    token_safety_margin: int = 2048  # Reduced from hardcoded 4096 - most responses under 2K
    token_early_warning_threshold: float = 0.60  # New early warning threshold
    token_critical_threshold: float = 0.80  # Raised from 0.70 to allow more context

    # Self-Healing Configuration (Enhancement Phase 1)
    max_recovery_attempts: int = 3  # Max recovery attempts per error
    reflection_interval: int = 5  # Iterations between self-reflection cycles
    enable_self_healing: bool = True  # Enable self-healing agent loop

    # Credential Manager Configuration (Enhancement Phase 2)
    credential_encryption_key: str | None = None  # AES-256 master key (32 bytes base64)
    credential_ttl_hours: int = 24  # Default credential TTL in Redis

    # Timeline Replay Configuration
    enable_timeline_recording: bool = True  # Enable timeline action recording
    timeline_snapshot_interval: int = 50  # Actions between periodic snapshots
    timeline_retention_days: int = 30  # Days to retain detailed timeline data
    timeline_max_snapshots_per_session: int = 1000  # Max snapshots per session
    timeline_compress_snapshots: bool = True  # Compress snapshot data

    # Workspace Auto-Initialization Configuration
    workspace_auto_init: bool = True  # Auto-initialize workspace on first message
    workspace_default_template: str = "python"  # Default template: none, python, nodejs, web, fullstack
    workspace_default_project_name: str = "project"  # Default project name

    # Canvas / Image Generation configuration
    fal_api_key: str | None = None  # fal.ai API key for FLUX image generation
    image_generation_provider: str = "fal"  # "fal" (only supported provider)
    image_generation_max_size: int = 2048  # Max width/height in pixels
    canvas_max_elements: int = 500  # Max elements per page
    canvas_max_versions: int = 100  # Max version snapshots per project

    # Research Enhancement Configuration (Phase 6)
    # Source filtering
    research_source_min_reliability: float = 0.4  # Minimum reliability score for sources
    research_source_min_relevance: float = 0.5  # Minimum relevance score for sources
    research_source_max_age_days: int = 730  # Max age of sources in days (2 years)
    research_source_require_https: bool = True  # Require HTTPS for sources
    research_source_allow_paywalled: bool = False  # Allow paywalled sources

    # Citation discipline
    research_citation_requirement: str = "moderate"  # "strict", "moderate", "relaxed"
    research_citation_min_coverage: float = 0.7  # Min citation coverage score
    research_citation_min_quality: float = 0.5  # Min citation quality score
    research_citation_auto_caveats: bool = True  # Auto-add caveats to uncited claims

    # Benchmark extraction
    research_benchmark_enabled: bool = True  # Enable benchmark extraction
    research_benchmark_min_confidence: float = 0.5  # Min confidence for extracted benchmarks

    # Report generation
    research_report_max_retries: int = 3  # Max retries for report generation
    research_report_max_sources: int = 10  # Max sources per research query

    # Feature flag
    feature_enhanced_research: bool = False  # Enable enhanced research flow
    feature_phased_research: bool = False  # Enable phased research workflow for deep research

    # Typo correction configuration (PromptQuickValidator enhancements)
    typo_correction_enabled: bool = True
    typo_correction_log_events: bool = True
    typo_correction_confidence_threshold: float = 0.90
    typo_correction_max_suggestions: int = 1
    typo_correction_rapidfuzz_enabled: bool = False
    typo_correction_rapidfuzz_score_cutoff: float = 90.0
    typo_correction_symspell_enabled: bool = False
    typo_correction_symspell_dictionary_path: str = "data/frequency_dictionary_en_82_765.txt"
    typo_correction_symspell_bigram_path: str = "data/frequency_bigramdictionary_en_243_342.txt"
    typo_correction_symspell_max_edit_distance: int = 2
    typo_correction_symspell_prefix_length: int = 7
    typo_correction_feedback_store_path: str = "data/typo_correction_feedback.json"
    typo_correction_feedback_min_occurrences: int = 3

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @computed_field
    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment.lower() == "production"

    @computed_field
    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.environment.lower() == "development"

    @computed_field
    @property
    def should_ignore_https_errors(self) -> bool:
        """Determine if browser should ignore HTTPS errors.

        Security: Defaults to False in production to prevent MITM attacks.
        In development, defaults to True for convenience with self-signed certs.
        """
        if self.browser_ignore_https_errors is not None:
            return self.browser_ignore_https_errors
        # Auto-detect: True in development, False in production
        return self.is_development

    @computed_field
    @property
    def cors_origins_list(self) -> list[str]:
        """Get CORS origins as a list"""
        if not self.cors_origins:
            if self.is_development:
                # Allow common frontend dev server ports in development
                return [
                    "http://localhost:5173",  # Vite default
                    "http://localhost:5174",  # Pythinker frontend
                    "http://localhost:3000",  # Common React/Next.js
                    "http://127.0.0.1:5173",
                    "http://127.0.0.1:5174",
                ]
            return []
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def _generate_jwt_secret(self) -> str:
        """Generate a secure JWT secret for development"""
        return secrets.token_urlsafe(32)

    def _generate_password_salt(self) -> str:
        """Generate a secure password salt"""
        return secrets.token_urlsafe(16)

    def validate(self) -> None:
        """Validate configuration settings with comprehensive security checks"""
        errors: list[str] = []
        security_warnings: list[str] = []

        # === CRITICAL SECURITY CHECKS ===

        # JWT Secret validation
        if not self.jwt_secret_key:
            if self.is_production:
                errors.append(
                    "JWT_SECRET_KEY is required in production. "
                    'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(32))"'
                )
            else:
                # Auto-generate for development (will be different each restart)
                object.__setattr__(self, "jwt_secret_key", self._generate_jwt_secret())
                security_warnings.append(
                    "JWT_SECRET_KEY not set - using auto-generated key. "
                    "Sessions will be invalidated on restart. Set JWT_SECRET_KEY for persistence."
                )
        elif self.jwt_secret_key in ["your-secret-key-here", "changeme", "secret"]:
            if self.is_production:
                errors.append("JWT_SECRET_KEY must not use default/insecure values in production")
            else:
                security_warnings.append("JWT_SECRET_KEY is using an insecure default value")

        # Password salt validation
        if not self.password_salt:
            if self.is_production and self.auth_provider == "password":
                errors.append(
                    "PASSWORD_SALT is required for password authentication in production. "
                    'Generate one with: python -c "import secrets; print(secrets.token_urlsafe(16))"'
                )
            else:
                object.__setattr__(self, "password_salt", self._generate_password_salt())
                if self.auth_provider == "password":
                    security_warnings.append(
                        "PASSWORD_SALT not set - using auto-generated salt. "
                        "Existing password hashes will be invalid on restart."
                    )

        # CORS validation
        if not self.cors_origins and self.is_production:
            errors.append(
                "CORS_ORIGINS must be configured in production. "
                "Set to your frontend domain(s), e.g., CORS_ORIGINS=https://app.example.com"
            )

        # Local auth credentials validation
        if self.auth_provider == "local":
            if not self.local_auth_email or not self.local_auth_password:
                errors.append("LOCAL_AUTH_EMAIL and LOCAL_AUTH_PASSWORD are required when auth_provider is 'local'")
            elif self.is_production:
                if self.local_auth_email == "admin@example.com":
                    errors.append("LOCAL_AUTH_EMAIL must not use default value in production")
                if self.local_auth_password == "admin":
                    errors.append("LOCAL_AUTH_PASSWORD must not use default value in production")
                if self.local_auth_password and len(self.local_auth_password) < 12:
                    security_warnings.append("LOCAL_AUTH_PASSWORD should be at least 12 characters")

        # === HIGH PRIORITY CHECKS ===

        # Password hash rounds validation
        if self.password_hash_rounds < 100000 and self.is_production:
            security_warnings.append(
                f"PASSWORD_HASH_ROUNDS ({self.password_hash_rounds}) is below recommended minimum (600000). "
                "This weakens password security."
            )

        # API key validation
        if self.llm_provider in ["openai", "anthropic"] and not self.api_key:
            if self.llm_provider == "anthropic" and not self.api_key:
                errors.append(f"API key is required for {self.llm_provider} provider")
            elif self.llm_provider == "openai":
                errors.append("API_KEY is required for OpenAI provider")

        # Credential encryption key
        if self.allow_credential_access and not self.credential_encryption_key and self.is_production:
            security_warnings.append(
                "CREDENTIAL_ENCRYPTION_KEY not set but credential access is enabled. "
                "Credentials will be stored without encryption."
            )

        # === WARNINGS ===

        # Auth provider "none" warning
        if self.auth_provider == "none":
            security_warnings.append(
                "AUTH_PROVIDER is set to 'none' - authentication is disabled. "
                "This should only be used for development/testing."
            )

        # Debug mode warning
        if self.debug and self.is_production:
            security_warnings.append("DEBUG mode is enabled in production - this may expose sensitive information")

        # Rate limiting warning
        if not self.rate_limit_enabled and self.is_production:
            security_warnings.append("Rate limiting is disabled in production - vulnerable to brute force attacks")

        # Account lockout warning
        if not self.account_lockout_enabled and self.is_production:
            security_warnings.append("Account lockout is disabled in production - vulnerable to brute force attacks")

        # === LOG WARNINGS ===
        for warning in security_warnings:
            if warning in self._emitted_security_warnings:
                logger.debug(f"[SECURITY] Duplicate warning suppressed: {warning}")
                continue

            self._emitted_security_warnings.add(warning)
            logger.warning(f"[SECURITY] {warning}")
            warnings.warn(warning, UserWarning, stacklevel=2)

        # === RAISE ERRORS ===
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)

        if not self._startup_banner_emitted:
            logger.info(
                "Configuration banner: environment=%s auth_provider=%s llm_provider=%s",
                self.environment,
                self.auth_provider,
                self.llm_provider,
            )
            type(self)._startup_banner_emitted = True

        logger.info(f"Configuration validated successfully (environment: {self.environment})")


@lru_cache
def get_settings() -> Settings:
    """Get application settings"""
    settings = Settings()
    settings.validate()
    return settings


def get_feature_flags() -> dict[str, bool]:
    """Get feature flag settings for agent enhancements."""
    try:
        settings = get_settings()
    except Exception:
        # Fail-open with safe defaults if settings validation fails
        return {
            "tree_of_thoughts": False,
            "self_consistency": False,
            "plan_validation_v2": False,
            "reflection_advanced": False,
            "context_optimization": False,
            "tool_tracing": False,
            "reward_hacking_detection": False,
            "failure_prediction": False,
            "circuit_breaker_adaptive": False,
            "workflow_checkpointing": False,
            "taskgroup_enabled": False,
            "sse_v2": False,
            "structured_outputs": False,
            "parallel_memory": False,
            "enhanced_research": False,
            "phased_research": False,
            "shadow_mode": True,
            # Hallucination Prevention (Phase 1-6)
            "url_verification": True,
            "claim_provenance": True,
            "enhanced_grounding": True,
            "cove_verification": True,
            "chain_of_verification": True,
            "semantic_citation_validation": True,
            "strict_numeric_verification": True,
            "reject_ungrounded_reports": False,
            "delivery_integrity_gate": True,
            "adaptive_verbosity_shadow": False,
        }
    return {
        "tree_of_thoughts": settings.feature_tree_of_thoughts,
        "self_consistency": settings.feature_self_consistency,
        "plan_validation_v2": settings.feature_plan_validation_v2,
        "reflection_advanced": settings.feature_reflection_advanced,
        "context_optimization": settings.feature_context_optimization,
        "tool_tracing": settings.feature_tool_tracing,
        "reward_hacking_detection": settings.feature_reward_hacking_detection,
        "failure_prediction": settings.feature_failure_prediction,
        "circuit_breaker_adaptive": settings.feature_circuit_breaker_adaptive,
        "workflow_checkpointing": settings.feature_workflow_checkpointing,
        "taskgroup_enabled": settings.feature_taskgroup_enabled,
        "sse_v2": settings.feature_sse_v2,
        "structured_outputs": settings.feature_structured_outputs,
        "parallel_memory": settings.feature_parallel_memory,
        "enhanced_research": settings.feature_enhanced_research,
        "phased_research": settings.feature_phased_research,
        "shadow_mode": settings.feature_shadow_mode,
        # Hallucination Prevention (Phase 1-6)
        "url_verification": settings.feature_url_verification,
        "claim_provenance": settings.feature_claim_provenance,
        "enhanced_grounding": settings.feature_enhanced_grounding,
        "cove_verification": settings.feature_cove_verification,
        "chain_of_verification": settings.feature_cove_verification,
        "semantic_citation_validation": settings.feature_semantic_citation_validation,
        "strict_numeric_verification": settings.feature_strict_numeric_verification,
        "reject_ungrounded_reports": settings.feature_reject_ungrounded_reports,
        "delivery_integrity_gate": settings.feature_delivery_integrity_gate,
        "adaptive_verbosity_shadow": settings.feature_adaptive_verbosity_shadow,
    }
