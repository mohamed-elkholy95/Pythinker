from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):

    # LLM Provider selection
    llm_provider: str = "openai"  # "openai", "anthropic", "ollama"

    # OpenAI-compatible provider configuration (default)
    api_key: str | None = None
    api_base: str = "https://api.deepseek.com/v1"

    # Model configuration
    model_name: str = "deepseek-chat"
    temperature: float = 0.3  # Lower temperature for deterministic JSON responses
    max_tokens: int = 8000  # Increased from 2000 to allow complete responses

    # Anthropic configuration
    anthropic_api_key: str | None = None
    anthropic_model_name: str = "claude-sonnet-4-20250514"

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
    
    # Redis configuration
    redis_host: str = "redis"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str | None = None

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
    
    # Search engine configuration
    search_provider: str | None = "bing"  # "baidu", "google", "bing", "searxng", "whoogle", "duckduckgo", "brave", "tavily"
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

    # Auth configuration
    auth_provider: str = "password"  # "password", "none", "local"
    password_salt: str | None = None
    password_hash_rounds: int = 10
    password_hash_algorithm: str = "pbkdf2_sha256"
    local_auth_email: str = "admin@example.com"
    local_auth_password: str = "admin"
    
    # Email configuration
    email_host: str | None = None  # "smtp.gmail.com"
    email_port: int | None = None  # 587
    email_username: str | None = None
    email_password: str | None = None
    email_from: str | None = None
    
    # JWT configuration
    jwt_secret_key: str = "your-secret-key-here"  # Should be set in production
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 30
    jwt_refresh_token_expire_days: int = 7
    
    # MCP configuration
    mcp_config_path: str = "/etc/mcp.json"

    # Logging configuration
    log_level: str = "INFO"

    # Alerting configuration (optional)
    alert_webhook_url: str | None = None
    alert_webhook_timeout_seconds: float = 3.0
    alert_throttle_seconds: int = 60

    # OpenTelemetry configuration (optional)
    otel_enabled: bool = False
    otel_endpoint: str | None = None  # e.g., "http://localhost:4317"
    otel_service_name: str = "pythinker-agent"
    otel_insecure: bool = True  # Use insecure connection (no TLS)

    # Multi-Agent Orchestration configuration
    enable_multi_agent: bool = False  # Enable specialized agent dispatch per step
    enable_coordinator: bool = False  # Enable full swarm coordinator mode
    multi_agent_max_parallel: int = 3  # Max concurrent agents in swarm mode

    # Parallel Step Execution configuration (Phase 4)
    enable_parallel_execution: bool = False  # Execute independent steps in parallel
    parallel_max_concurrency: int = 3  # Max concurrent step executions

    # LangGraph Flow configuration
    use_langgraph_flow: bool = False  # Use LangGraph-based PlanActFlow instead of custom

    # Autonomy Configuration (Enhancement Phase 1)
    autonomy_level: str = "guided"  # supervised, guided, autonomous, unrestricted
    allow_credential_access: bool = True
    allow_external_requests: bool = True
    allow_file_system_write: bool = True
    allow_file_system_delete: bool = False  # Disabled by default for safety
    allow_shell_execute: bool = True
    allow_browser_navigation: bool = True
    allow_payment_operations: bool = False  # Disabled by default

    # Safety Limits
    max_iterations: int = 50  # Maximum loop iterations per run
    max_tool_calls: int = 100  # Maximum tool invocations per run
    max_execution_time_seconds: int = 1800  # 30 minutes default
    max_tokens_per_run: int = 500000  # Token limit across all LLM calls
    max_cost_usd: float | None = None  # Optional cost limit

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

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        
    def validate(self):
        """Validate configuration settings"""
        if not self.api_key:
            raise ValueError("API key is required")

@lru_cache()
def get_settings() -> Settings:
    """Get application settings"""
    settings = Settings()
    settings.validate()
    return settings 
