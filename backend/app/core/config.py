import logging
import secrets
import warnings
from functools import lru_cache

from pydantic_settings import BaseSettings

logger = logging.getLogger(__name__)


class Settings(BaseSettings):
    # Environment configuration
    environment: str = "development"  # "development", "staging", "production"
    debug: bool = False

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
    max_tokens: int = 8000  # Increased from 2000 to allow complete responses

    # Ollama configuration
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Embedding configuration (separate from chat model)
    embedding_api_key: str | None = None  # Defaults to api_key if not set
    embedding_api_base: str = "https://api.openai.com/v1"  # OpenAI for embeddings
    embedding_model: str = "text-embedding-3-small"  # 1536 dimensions

    # MongoDB configuration
    mongodb_uri: str = "mongodb://mongodb:27017"
    mongodb_database: str = "manus"
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

    # Qdrant Vector Database configuration
    qdrant_url: str = "http://qdrant:6333"
    qdrant_grpc_port: int = 6334
    qdrant_prefer_grpc: bool = True  # 2x faster than REST
    qdrant_collection: str = "agent_memories"
    qdrant_api_key: str | None = None

    # Sandbox configuration
    sandbox_address: str | None = None
    sandbox_image: str | None = None
    sandbox_name_prefix: str | None = None
    sandbox_ttl_minutes: int | None = 30
    sandbox_network: str | None = None  # Docker network bridge name
    sandbox_chrome_args: str | None = ""
    sandbox_https_proxy: str | None = None
    sandbox_http_proxy: str | None = None
    sandbox_no_proxy: str | None = None
    sandbox_seccomp_profile: str | None = None
    sandbox_shm_size: str | None = "2g"
    sandbox_mem_limit: str | None = "4g"
    sandbox_cpu_limit: float | None = 2.0
    sandbox_pids_limit: int | None = 500
    sandbox_framework_port: int = 8082
    sandbox_framework_enabled: bool = True
    sandbox_framework_required: bool = False

    # Session initialization optimization (Phase 1-5)
    sandbox_cdp_initial_delay: float = 0.5  # Initial delay for CDP retry backoff
    sandbox_cdp_max_delay: float = 2.0  # Maximum delay for CDP retry backoff
    sandbox_cdp_retries: int = 10  # Number of CDP connection retries
    sandbox_eager_init: bool = True  # Start sandbox creation on session create
    workspace_lazy_init: bool = True  # Defer workspace init until needed

    # Sandbox Pool Pre-warming (Phase 3)
    sandbox_pool_enabled: bool = True  # Enable sandbox pool for instant allocation (20-32s → 2-5s cold start)
    sandbox_pool_min_size: int = 2  # Minimum sandboxes to maintain in pool
    sandbox_pool_max_size: int = 4  # Maximum sandboxes in pool (reduced to limit resource usage)
    sandbox_pool_warmup_interval: int = 30  # Seconds between pool maintenance checks

    # Lazy initialization (Phase 5)
    mcp_lazy_init: bool = True  # Defer MCP initialization until first use

    # Search engine configuration
    search_provider: str | None = "bing"  #  "google", "bing", "searxng", "whoogle", "duckduckgo", "brave", "tavily"
    search_prefer_browser: bool = (
        True  # Use browser for search (visible in sandbox) instead of API (faster but invisible)
    )
    google_search_api_key: str | None = None
    google_search_engine_id: str | None = None
    searxng_url: str | None = "http://searxng:8080"  # SearXNG instance URL
    whoogle_url: str | None = "http://whoogle:5000"  # Whoogle instance URL
    brave_search_api_key: str | None = None  # Brave Search API key
    tavily_api_key: str | None = None  # Tavily AI Search API key

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

    # Browser Hardening Configuration
    browser_skip_video_urls: bool = True  # Skip video sites (YouTube, Vimeo, etc.)
    browser_auto_dismiss_dialogs: bool = True  # Auto-dismiss popups, alerts, confirms
    browser_show_cursor: bool = True  # Show visual cursor indicator for agent actions

    # Browser HTTP Fetch Configuration (P3.1: faster failure detection)
    browser_fetch_timeout: float = 15.0  # Total timeout for HTTP fetch (reduced from 30s)
    browser_fetch_connect_timeout: float = 5.0  # Connection timeout (reduced from 10s)

    # Browser Connection Pool Configuration (Phase 3: connection reuse)
    browser_pool_enabled: bool = True  # Enable browser connection pooling
    browser_pool_max_per_url: int = 8  # Max connections per CDP URL (increased to prevent exhaustion)
    browser_pool_timeout: float = 30.0  # Timeout waiting for available connection
    browser_pool_max_idle: float = 300.0  # Max idle time before cleanup (5 min)
    browser_pool_health_interval: float = 60.0  # Health check interval (1 min)

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
    enable_coordinator: bool = False  # Enable full swarm coordinator mode
    multi_agent_max_parallel: int = 3  # Max concurrent agents in swarm mode

    # Parallel Step Execution configuration (Phase 4)
    enable_parallel_execution: bool = False  # Execute independent steps in parallel
    parallel_max_concurrency: int = 3  # Max concurrent step executions

    # Plan Verification configuration (Performance optimization)
    enable_plan_verification: bool = False  # Skip verification phase for faster execution

    # LangGraph Flow configuration
    use_langgraph_flow: bool = False  # Use LangGraph-based PlanActFlow instead of custom

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
    # Phase 2: LangGraph + Browser-use Node Integration
    feature_browser_node: bool = False  # Browser-use as first-class LangGraph node
    # Phase 3: SSE Streaming v2
    feature_sse_v2: bool = False  # LangGraph astream_events v2 API
    # Phase 4: Zero-Hallucination Defense
    feature_structured_outputs: bool = False  # Pydantic structured LLM outputs with validation
    # Phase 5: Parallel Memory Architecture
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

    # OpenReplay Session Recording Configuration
    openreplay_enabled: bool = True  # Enable OpenReplay integration
    openreplay_project_key: str = "pythinker-dev"  # OpenReplay project key
    openreplay_ingest_url: str = "http://localhost:9001"  # OpenReplay ingestion endpoint
    openreplay_api_url: str = "http://localhost:8090"  # OpenReplay API endpoint

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

    @property
    def is_production(self) -> bool:
        """Check if running in production environment"""
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        """Check if running in development environment"""
        return self.environment.lower() == "development"

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
            if self.llm_provider == "anthropic" and not self.anthropic_api_key:
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
            logger.warning(f"[SECURITY] {warning}")
            warnings.warn(warning, UserWarning, stacklevel=2)

        # === RAISE ERRORS ===
        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            logger.error(error_msg)
            raise ValueError(error_msg)

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
            "plan_validation_v2": False,
            "reflection_advanced": False,
            "context_optimization": False,
            "tool_tracing": False,
            "reward_hacking_detection": False,
            "failure_prediction": False,
            "circuit_breaker_adaptive": False,
            "workflow_checkpointing": False,
            "shadow_mode": True,
            # Hallucination Prevention (Phase 1-6)
            "url_verification": True,
            "claim_provenance": True,
            "enhanced_grounding": True,
            "cove_verification": True,
            "semantic_citation_validation": True,
            "strict_numeric_verification": True,
            "reject_ungrounded_reports": False,
        }
    return {
        "plan_validation_v2": settings.feature_plan_validation_v2,
        "reflection_advanced": settings.feature_reflection_advanced,
        "context_optimization": settings.feature_context_optimization,
        "tool_tracing": settings.feature_tool_tracing,
        "reward_hacking_detection": settings.feature_reward_hacking_detection,
        "failure_prediction": settings.feature_failure_prediction,
        "circuit_breaker_adaptive": settings.feature_circuit_breaker_adaptive,
        "workflow_checkpointing": settings.feature_workflow_checkpointing,
        "shadow_mode": settings.feature_shadow_mode,
        # Hallucination Prevention (Phase 1-6)
        "url_verification": settings.feature_url_verification,
        "claim_provenance": settings.feature_claim_provenance,
        "enhanced_grounding": settings.feature_enhanced_grounding,
        "cove_verification": settings.feature_cove_verification,
        "semantic_citation_validation": settings.feature_semantic_citation_validation,
        "strict_numeric_verification": settings.feature_strict_numeric_verification,
        "reject_ungrounded_reports": settings.feature_reject_ungrounded_reports,
    }
