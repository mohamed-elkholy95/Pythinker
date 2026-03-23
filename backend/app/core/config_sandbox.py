"""Sandbox and browser settings mixins.

Contains configuration for Docker sandbox lifecycle, pool management, browser agent,
anti-bot stealth, connection pooling, crash detection, screenshots, and stuck detection.

# ---------------------------------------------------------------------------
# Sandbox Operating Modes (set via environment variables)
# ---------------------------------------------------------------------------
#
# COST mode (default for development — single static sandbox, no pool):
#   SANDBOX_LIFECYCLE_MODE=static
#   SANDBOX_POOL_ENABLED=false
#   SANDBOX_MEM_LIMIT=4G        (docker-compose.yml default)
#   SANDBOX_CPU_LIMIT=1.5       (docker-compose.yml default)
#   SANDBOX_SHM_SIZE=256m       (docker-compose.yml default)
#   ENABLE_VNC=0
#   One static sandbox, no pre-warmed pool; lowest host resource footprint.
#
# PERFORMANCE mode (for production with concurrent users):
#   SANDBOX_LIFECYCLE_MODE=pool
#   SANDBOX_POOL_ENABLED=true
#   SANDBOX_POOL_MIN_SIZE=2
#   SANDBOX_POOL_MAX_SIZE=10
#   SANDBOX_MEM_LIMIT=2G        (docker-compose-deploy.yml default)
#   SANDBOX_CPU_LIMIT=1         (docker-compose-deploy.yml default)
#   SANDBOX_SHM_SIZE=256m
#   Pre-warmed pool reduces cold-start from ~30 s to 2-5 s; each sandbox
#   uses up to 2 GB RAM, so size pool_max to available host memory.
# ---------------------------------------------------------------------------
"""

from pydantic import Field, field_validator

from app.core.config_enums import SandboxLifecycleMode, StreamingMode


class SandboxSettingsMixin:
    """Core sandbox lifecycle and pool configuration."""

    sandbox_lifecycle_mode: SandboxLifecycleMode = SandboxLifecycleMode.STATIC

    @field_validator("sandbox_lifecycle_mode", mode="before")
    @classmethod
    def _coerce_sandbox_lifecycle_mode(cls, v: object) -> SandboxLifecycleMode:
        """Coerce plain string values (e.g. from .env) to the SandboxLifecycleMode enum."""
        if isinstance(v, SandboxLifecycleMode):
            return v
        if isinstance(v, str):
            lowered = v.strip().lower()
            try:
                return SandboxLifecycleMode(lowered)
            except ValueError:
                allowed = ", ".join(m.value for m in SandboxLifecycleMode)
                msg = f"Invalid sandbox_lifecycle_mode '{v}'. Allowed values: {allowed}"
                raise ValueError(msg) from None
        msg = f"sandbox_lifecycle_mode must be a string, got {type(v).__name__}"
        raise TypeError(msg)

    sandbox_streaming_mode: StreamingMode = StreamingMode.CDP_ONLY
    # State snapshot retention (MongoDB SnapshotDocument, NOT sandbox container tarballs)
    sandbox_snapshot_ttl_days: int = 7  # State snapshot retention period
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
    sandbox_shm_size: str | None = "2g"  # Playwright/Selenium: 2GB prevents Chrome /dev/shm OOM
    sandbox_mem_limit: str | None = "4g"  # Increased from 3g to reduce OOM kills
    sandbox_cpu_limit: float | None = 1.5  # 2 containers x 1.5 CPU = 3 cores
    sandbox_pids_limit: int | None = 300  # Sufficient for Chrome + Node + Python + supervisor
    sandbox_framework_port: int = 8082
    sandbox_framework_enabled: bool = True
    sandbox_framework_required: bool = False
    sandbox_api_secret: str | None = None  # Shared secret for sandbox API auth

    # Cloud tokens for sandbox
    sandbox_gh_token: str | None = None
    sandbox_google_drive_token: str | None = None
    sandbox_google_workspace_token: str | None = None

    # Sandbox callback
    sandbox_callback_enabled: bool = False
    sandbox_callback_token: str | None = None

    # LLM Proxy (OpenAI-compatible endpoint for sandbox)
    sandbox_llm_proxy_enabled: bool = False
    sandbox_llm_proxy_key: str | None = None
    sandbox_llm_proxy_max_tokens: int = 4096
    sandbox_llm_proxy_rate_limit: int = 30  # requests per minute
    sandbox_llm_proxy_allowed_models: list[str] = Field(default_factory=list)  # empty = all models

    # Phase 3: HTTP/2 Configuration
    sandbox_http2_enabled: bool = False  # Enable HTTP/2 for sandbox API communication

    # Session initialization optimization (Phase 1-5)
    sandbox_cdp_initial_delay: float = 0.5  # Initial delay for CDP retry backoff
    sandbox_cdp_max_delay: float = 2.0  # Maximum delay for CDP retry backoff
    sandbox_cdp_retries: int = 10  # Number of CDP connection retries
    sandbox_eager_init: bool = True  # Start sandbox creation on session create
    workspace_lazy_init: bool = True  # Defer workspace init until needed

    # Sandbox warmup race condition fix (Phase 6)
    sandbox_warmup_grace_period: float = 3.0  # Wait before first health check
    sandbox_warmup_initial_retry_delay: float = 1.0  # Initial delay between retries
    sandbox_warmup_max_retry_delay: float = 3.0  # Maximum delay between retries
    sandbox_warmup_backoff_multiplier: float = 1.5  # Exponential backoff multiplier
    sandbox_warmup_connection_failure_threshold: int = 12  # Max connection failures before giving up
    # Hard wall-clock budget for the full ensure_sandbox warmup flow (IMPORTANT-6).
    # 0 = disabled (retry-count is the only bound, matching legacy behaviour).
    sandbox_warmup_wall_clock_timeout: float = 180.0  # Max total seconds before aborting warmup


class SandboxPoolSettingsMixin:
    """Sandbox pool pre-warming, idle management, and lifecycle optimization."""

    # Sandbox Pool Pre-warming (Phase 3)
    sandbox_pool_enabled: bool = True  # Enable sandbox pool (20-32s → 2-5s cold start)
    sandbox_pool_min_size: int = 2  # Pre-warm 2 sandboxes for faster cold start
    sandbox_pool_max_size: int = 10  # Scale: ~2GB RAM per sandbox, adjust to host capacity
    max_concurrent_agents: int = 8  # In-process concurrency guard; scale with pool_max_size
    max_concurrent_executions: int = 12  # LLM execution concurrency (higher than agents since LLM calls are I/O-bound)
    sandbox_pool_warmup_interval: int = 30  # Seconds between pool maintenance checks

    # Sandbox idle management
    sandbox_pool_idle_ttl_seconds: int = 300  # Evict pooled sandbox after 5 min idle
    sandbox_pool_pause_idle: bool = True  # Docker pause idle pooled sandboxes to reclaim CPU
    sandbox_pool_host_memory_threshold: float = 0.80  # Stop pre-warming at 80% host RAM

    # Sandbox lifecycle optimization
    sandbox_pool_reaper_interval: int = 60  # Orphan reaper check interval (seconds)
    sandbox_pool_reaper_grace_period: int = 120  # Don't reap containers younger than this

    # Session runtime cleanup worker
    stale_session_cleanup_interval_seconds: int = 300  # Periodic stale-session cleanup interval
    storage_cleanup_interval_seconds: int = 86400  # Storage TTL cleanup interval (daily)
    stale_session_threshold_minutes: int = 30  # Runtime state older than this is stale
    stale_session_startup_threshold_minutes: int = 5  # Aggressive cleanup window during startup

    # Sandbox health monitoring (Priority 3: proactive crash detection)
    sandbox_health_check_interval: int = 30  # Continuous health check interval (seconds)
    sandbox_oom_monitor_enabled: bool = True  # Monitor Docker events for OOM kills
    sandbox_runtime_crash_recovery: bool = True  # Automatically replace crashed sandboxes

    # Lazy initialization (Phase 5)
    mcp_lazy_init: bool = True  # Defer MCP initialization until first use


class BrowserSettingsMixin:
    """Browser agent, stealth, and connection configuration."""

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

    # Playwright Chromium (version-pinned by playwright install)
    browser_chrome_executable_path: str | None = None  # Override path (default: /usr/local/bin/chromium in sandbox)
    browser_chrome_version: str = "128.0.6613.137"  # Matches Playwright Chromium in sandbox

    # Browser Hardening Configuration
    browser_skip_video_urls: bool = True  # Skip video sites (YouTube, Vimeo, etc.)
    browser_auto_dismiss_dialogs: bool = True  # Auto-dismiss popups, alerts, confirms
    browser_show_cursor: bool = True  # Show visual cursor indicator for agent actions

    # Browser HTTP Fetch Configuration (P3.1: faster failure detection)
    browser_fetch_timeout: float = 15.0  # Total timeout for HTTP fetch (reduced from 30s)
    browser_fetch_connect_timeout: float = 5.0  # Connection timeout (reduced from 10s)

    # Browser Connection Pool Configuration (Phase 3: connection reuse)
    browser_pool_enabled: bool = True  # Enable browser connection pooling
    browser_pool_max_per_url: int = 16  # Max connections per CDP URL
    browser_pool_timeout: float = 30.0  # Timeout waiting for available connection
    browser_pool_max_idle: float = 300.0  # Max idle time before cleanup (5 min)
    browser_pool_health_interval: float = 60.0  # Health check interval (1 min)
    browser_init_timeout: float = 20.0  # Overall timeout for browser initialization (seconds)

    # Browser crash detection and circuit breaker (Phase 1: hardening)
    browser_crash_circuit_breaker_enabled: bool = True  # Enable circuit breaker for repeated crashes
    browser_crash_window_seconds: float = 300.0  # 5 min window for crash tracking
    browser_crash_threshold: int = 3  # Max crashes in window before circuit opens
    browser_crash_cooldown_seconds: float = 60.0  # Circuit open duration (1 min)
    browser_quick_health_check_enabled: bool = True  # Enable fast health check before operations
    browser_quick_health_check_timeout: float = 3.0  # Fast health check timeout (3s)

    # CDP keepalive (prevents idle WebSocket disconnects)
    browser_cdp_keepalive_enabled: bool = True  # Enable periodic JS eval to keep CDP alive
    browser_cdp_keepalive_interval: float = 45.0  # Seconds between keepalive probes

    # Browser element extraction configuration (Phase 6: fix timeouts)
    browser_element_extraction_timeout: float = 5.0  # Timeout for interactive element extraction (seconds)
    browser_element_extraction_retries: int = 2  # Number of retries for element extraction
    browser_element_extraction_retry_delay: float = 1.0  # Delay between retries (seconds)
    browser_element_extraction_cache_ttl: float = 15.0  # Cache TTL for extracted elements (seconds)

    # Browser crash prevention (Priority 1: fix Wikipedia crashes)
    browser_graceful_degradation: bool = True  # Return partial results instead of failing
    browser_memory_auto_restart: bool = True  # Proactively restart browser on memory pressure
    browser_memory_critical_threshold_mb: int = 800  # Restart trigger threshold
    browser_memory_high_threshold_mb: int = 500  # Warning level threshold
    browser_wikipedia_lightweight_mode: bool = True  # Special handling for Wikipedia pages

    # Heavy page detection (Priority 1: proactive detection before expensive operations)
    browser_heavy_page_html_size_threshold: int = 5_000_000  # 5MB HTML size triggers lightweight mode
    browser_heavy_page_dom_threshold: int = 3000  # DOM element count triggers lightweight mode
    browser_heavy_page_skip_scroll: bool = True  # Skip smart scroll on heavy pages

    # Browser resource blocking — agent extracts text, not visual content.
    # Blocking images/fonts/media reduces page load by 40-60% and cuts memory usage.
    # Context7-validated: Playwright page.route() with route.abort() for resource_type.
    browser_block_resources_default: bool = True  # Enable resource blocking by default
    browser_blocked_resource_types: str = "image,media,font"  # Comma-separated resource types

    # Chrome on-demand lifecycle (sandbox-side feature)
    # When enabled, backend calls /api/v1/browser/ensure before browser operations
    chrome_on_demand: bool = True
    chrome_ensure_timeout: float = 35.0  # Timeout for ensure call (slightly > CHROME_READY_TIMEOUT)

    # Fast acknowledgment refiner configuration (Phase 6: fix timeouts)
    # Raised from 5.0→8.0 to accommodate high-latency providers (Z.AI GLM).
    # Benchmark showed 43% timeout rate at 5.0s.  Override: FAST_ACK_REFINER_TIMEOUT=<seconds>
    fast_ack_refiner_timeout: float = 8.0  # LLM timeout for fast acknowledgment generation
    fast_ack_refiner_traceback_sample_rate: float = 0.05  # Sample rate for error traceback logging


class ScreenshotSettingsMixin:
    """Screenshot capture, deduplication, and resilience configuration."""

    screenshot_capture_enabled: bool = True
    screenshot_periodic_interval: float = 10.0  # seconds between periodic captures
    screenshot_quality: int = 75  # JPEG quality for full-res (1-100)
    screenshot_scale: float = 0.5  # Scale factor for full-res
    screenshot_thumbnail_quality: int = 40  # JPEG quality for thumbnails
    screenshot_thumbnail_scale: float = 0.25  # Scale factor for thumbnails

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
    screenshot_http_max_connections: int = 50  # Dedicated pool size
    screenshot_http_pool_timeout: float = 30.0  # Pool wait timeout
    screenshot_http_retry_attempts: int = 3  # Retry on failure
    screenshot_http_retry_delay: float = 2.0  # Initial retry delay (exponential backoff)

    # Startup readiness gate (prevents ConnectError when sandbox screenshot handler
    # hasn't fully initialized after ensure_sandbox() returns)
    screenshot_startup_grace_seconds: float = 2.0  # Grace period before first probe
    screenshot_startup_max_probes: int = 5  # Max probe attempts before giving up
    screenshot_startup_probe_timeout: float = 30.0  # Hard timeout for the full probe sequence

    # Screenshot TTL cleanup
    screenshot_ttl_days: int = 30  # Delete screenshots older than 30 days

    # Stuck Detection Configuration (P3.2/P3.3: faster loop detection)
    stuck_detection_window: int = 5  # Response window size (reduced from 10)
    stuck_detection_threshold: int = 3  # Threshold for stuck detection (reduced from 5)
    browser_loop_detection_count: int = 2  # Same-URL navigations before flagging (reduced from 3)
