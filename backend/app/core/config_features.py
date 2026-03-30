"""Feature flags, agent behavior, observability, and research settings mixins.

Contains configuration for agent feature flags, safety limits, autonomy controls,
multi-agent orchestration, observability (logging, OTel, alerting), search providers,
research quality settings, and typo correction.
"""

from app.core.search_provider_policy import DEFAULT_SEARCH_PROVIDER_CHAIN


class SearchSettingsMixin:
    """Search engine API keys and provider configuration."""

    search_provider: str | None = (
        "duckduckgo"  # "google", "bing", "duckduckgo", "brave", "tavily", "serper", "exa", "jina"
    )
    search_provider_chain: str | list[str] | None = ",".join(DEFAULT_SEARCH_PROVIDER_CHAIN)
    # Explicit fallback policy chain. Supports JSON list strings or comma-separated strings.
    search_prefer_browser: bool = (
        False  # API search is faster; browser search is only useful for live preview visibility
    )
    google_search_api_key: str | None = None
    google_search_engine_id: str | None = None
    brave_search_api_key: str | None = None  # Brave Search API key
    brave_search_api_key_2: str | None = None  # Fallback Brave key #1
    brave_search_api_key_3: str | None = None  # Fallback Brave key #2
    tavily_api_key: str | None = None  # Tavily AI Search API key
    tavily_api_key_2: str | None = None  # Fallback Tavily key (auto-rotates on quota/billing errors)
    tavily_api_key_3: str | None = None  # Third fallback Tavily key
    tavily_api_key_4: str | None = None  # Fourth fallback Tavily key
    tavily_api_key_5: str | None = None  # Fifth fallback Tavily key
    tavily_api_key_6: str | None = None  # Sixth fallback Tavily key
    tavily_api_key_7: str | None = None  # Seventh fallback Tavily key
    tavily_api_key_8: str | None = None  # Eighth fallback Tavily key
    tavily_api_key_9: str | None = None  # Ninth fallback Tavily key
    serper_api_key: str | None = None  # Serper.dev Google Search API key (free tier: 2500 queries/mo)
    serper_api_key_2: str | None = None  # Fallback Serper key
    serper_api_key_3: str | None = None  # Third fallback Serper key
    serper_api_key_4: str | None = None  # Fourth fallback Serper key
    serper_api_key_5: str | None = None  # Fifth fallback Serper key
    serper_api_key_6: str | None = None  # Sixth fallback Serper key
    serper_api_key_7: str | None = None  # Seventh fallback Serper key
    serper_api_key_8: str | None = None  # Eighth fallback Serper key
    serper_api_key_9: str | None = None  # Ninth fallback Serper key
    exa_api_key: str | None = None  # Exa AI Search API key (neural/semantic search)
    exa_api_key_2: str | None = None  # Fallback Exa key #2
    exa_api_key_3: str | None = None  # Fallback Exa key #3
    exa_api_key_4: str | None = None  # Fallback Exa key #4
    exa_api_key_5: str | None = None  # Fallback Exa key #5
    jina_api_key: str | None = None  # Jina AI Search/Reader API key
    jina_api_key_2: str | None = None  # Fallback Jina key #2
    jina_api_key_3: str | None = None  # Fallback Jina key #3
    jina_api_key_4: str | None = None  # Fallback Jina key #4
    jina_api_key_5: str | None = None  # Fallback Jina key #5

    # Search key pool recovery
    serper_quota_cooldown_seconds: int = 1800  # Cooldown after quota exhaustion (default 30min)

    # Search API budget limits (per agent task)
    max_search_api_calls_per_task: int = 15  # Hard cap on API calls per task
    max_search_api_calls_deep_research: int = 25  # Higher budget for deep_research flows
    max_wide_research_queries: int = 3  # Max queries in a single wide_research call (default for simple/medium)
    max_wide_research_queries_complex: int = 5  # Max queries for very_complex tasks (complexity >= 0.8)
    max_wide_research_calls_per_task: int = 2  # Max wide_research invocations per task
    search_cache_ttl: int = 7200  # Cache TTL in seconds (default 2h)
    search_dedup_skip_existing: bool = True  # Skip API call if TaskStateManager says already searched
    search_use_jina_rerank: bool = False  # Optional post-search reranking via Jina /v1/rerank
    search_jina_rerank_top_n: int = 8  # Number of top results to rerank when enabled
    search_jina_rerank_model: str = "jina-reranker-v2-base-multilingual"

    # Search provider profile controls (replaces hardcoded values in adapters)
    search_max_results: int = 8  # Max results per provider call (was hardcoded 20)
    search_max_results_wide: int = 20  # Max results for wide_research calls
    tavily_search_depth: str = "basic"  # "basic" (1 credit) or "advanced" (2 credits)
    exa_search_type: str = "auto"  # "auto" | "keyword" | "neural"

    # Rate governor controls (Redis token bucket per provider+IP)
    search_rate_governor_enabled: bool = False
    search_rate_governor_rps_serper: float = 5.0
    search_rate_governor_rps_tavily: float = 3.0
    search_rate_governor_rps_brave: float = 1.0
    search_rate_governor_rps_exa: float = 3.0
    search_rate_governor_burst: float = 5.0

    # Bulkhead concurrency cap per provider
    search_max_concurrent_per_provider: int = 3

    # Timeout stratification
    search_connect_timeout: float = 5.0  # Short: fail-fast for API search
    search_read_timeout: float = 15.0  # Short: provider APIs respond fast
    search_total_timeout: float = 20.0  # Absolute deadline
    page_fetch_connect_timeout: float = 10.0
    page_fetch_read_timeout: float = 60.0
    page_fetch_total_timeout: float = 90.0

    # Proxy support (feature-flagged)
    search_proxy_enabled: bool = False
    search_http_proxy: str = ""
    search_socks5_proxy: str = ""

    # --- Quota Management (Smart Meter) ---
    search_quota_tavily: int = 1000
    search_quota_serper: int = 2500
    search_quota_brave: int = 2000
    search_quota_exa: int = 1000
    search_quota_jina: int = 500

    # --- Credit Optimization ---
    search_default_depth: str = "basic"
    search_upgrade_depth_threshold: float = 0.7  # Quota remaining ratio above which STANDARD→advanced
    search_quality_early_stop: int = 5  # If provider returns 5+ results, don't try fallback
    search_prefer_free_scrapers_for_quick: bool = True  # QUICK intent → DuckDuckGo/Bing first

    # --- Enhanced Dedup ---
    search_enhanced_dedup_enabled: bool = True
    search_dedup_jaccard_threshold: float = 0.6  # Word-overlap threshold for fuzzy dedup

    # --- Budget Auto-Degrade Thresholds ---
    search_budget_degrade_deep_threshold: float = 0.2  # <20% remaining → DEEP→STANDARD
    search_budget_degrade_standard_threshold: float = 0.1  # <10% remaining → STANDARD→QUICK
    search_budget_degrade_scraper_threshold: float = 0.05  # <5% remaining → free scrapers only

    # --- Feature Flag ---
    search_quota_manager_enabled: bool = False  # Opt-in, zero behavior change until enabled

    # --- Mode-Aware Compaction (deep-research overrides) ---
    # When complexity_score >= 0.8 (deep_research), these higher limits replace
    # the standard-mode defaults.  Standard-mode behaviour is unchanged.
    search_compaction_max_results_deep: int = 15  # wide_research result cap (standard: 10)
    search_compaction_max_summaries_deep: int = 12  # summary entries in LLM message (standard: 8)
    search_compaction_summary_snippet_chars_deep: int = 250  # chars per summary snippet (standard: 150)
    search_auto_enrich_top_k_deep: int = 8  # URLs to enrich (standard: 5)
    search_auto_enrich_snippet_chars_deep: int = 3000  # max chars per enriched snippet (standard: 2000)
    search_preview_count_deep: int = 8  # background preview URLs (standard: 5)


class AgentSafetySettingsMixin:
    """Safety limits, autonomy controls, and agent execution configuration."""

    # Safety Limits
    max_iterations: int = 400  # Maximum loop iterations per run (doubled for complex tasks)
    max_tool_calls: int = 500  # Maximum tool invocations per run (increased for codebase analysis)
    max_execution_time_seconds: int = 3600  # 60 minutes wall-clock ceiling
    # Idle timeout: resets on every yielded event. Must exceed llm_request_timeout x 2 + retry
    # overhead so a slow provider can complete one full attempt + one retry before the watchdog
    # fires. Settings.effective_workflow_idle_timeout auto-floors this when it is too small.
    # Formula: 2 x LLM_REQUEST_TIMEOUT (300s) + 60s margin = 660s.
    workflow_idle_timeout_seconds: int = 660  # 11 min — survives full LLM attempt + one retry
    cancellation_grace_period_seconds: int = 5  # Grace before cancelling during tool execution
    max_tokens_per_run: int = 500000  # Token limit across all LLM calls
    max_cost_usd: float | None = None  # Optional cost limit

    # Absolute wall-clock limit for the entire agent session (base.execute()).
    # Acts as a hard outer guard independent of per-step limits and idle timeouts.
    # Default 1 hour; set to 0 to disable.
    max_session_wall_clock_seconds: int = 3600

    # Agent execution tuning (consumed by BaseAgent, PlannerAgent, PlanActFlow)
    agent_max_retries: int = 3  # LLM call retries per step
    agent_max_step_iterations: int = 50  # Max iterations within a single step
    agent_checkpoint_interval: int = 5  # Write checkpoint every N completed steps
    planner_max_steps: int = 4  # Default max plan steps (overridden by complexity)
    planner_research_step_cap: int = 10  # Max steps for research-heavy tasks

    # Hard context cap: last-resort safety valve against 60-80s LLM calls.
    # When total conversation chars exceed this, BaseAgent applies graduated truncation
    # to tool messages (older = shorter) — see BaseAgent.ask_with_messages.
    hard_context_char_cap: int = 50_000  # Default cap for standard tasks
    hard_context_char_cap_deep_research: int = 130_000  # Research modes (deep/wide/fast_search via _is_deep_research)
    # Browser navigation budget per execution step (prevents infinite browsing loops)
    max_browser_navigations_per_step: int = 6

    # Self-Healing Configuration (Enhancement Phase 1)
    max_recovery_attempts: int = 3  # Max recovery attempts per error
    reflection_interval: int = 5  # Iterations between self-reflection cycles
    enable_self_healing: bool = True  # Enable self-healing agent loop

    # Autonomy Configuration (Enhancement Phase 1)
    autonomy_level: str = "guided"  # supervised, guided, autonomous, unrestricted
    allow_credential_access: bool = True
    allow_external_requests: bool = True
    allow_file_system_write: bool = True
    allow_file_system_delete: bool = False  # Disabled by default for safety
    allow_shell_execute: bool = True
    allow_browser_navigation: bool = True
    allow_payment_operations: bool = False  # Disabled by default


class MultiAgentSettingsMixin:
    """Multi-agent orchestration and parallel execution configuration."""

    # Multi-Agent Orchestration configuration
    enable_multi_agent: bool = True  # Enable specialized agent dispatch per step
    enable_coordinator: bool = False  # Deprecated: use flow_mode instead
    multi_agent_max_parallel: int = 3  # Max concurrent agents in swarm mode

    # Parallel Step Execution configuration (Phase 4)
    enable_parallel_execution: bool = True  # Execute independent steps in parallel
    parallel_max_concurrency: int = 3  # Max concurrent step executions

    # Plan Verification configuration (Performance optimization)
    enable_plan_verification: bool = True  # Verify plan feasibility before execution


class ObservabilitySettingsMixin:
    """Logging, OpenTelemetry, alerting, and MCP configuration."""

    # MCP configuration
    mcp_config_path: str = "/etc/mcp.json"
    mcp_tool_output_limit: int = 12000  # Max chars for MCP tool observation output
    mcp_health_check_interval: float = 300.0  # Seconds between health checks (5 min)
    mcp_recovery_interval: float = 60.0  # Seconds between recovery attempts (1 min)

    # Logging configuration
    log_level: str = "INFO"
    log_format: str = "auto"  # "auto" (dev=console, prod=json), "json", "plain" (no ANSI)
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

    # When True, authenticated users may fetch recent Docker log tails (backend + sandbox)
    # via GET /api/v1/diagnostics/container-logs. Requires Docker socket on the host.
    container_log_preview_enabled: bool = False


class TimelineSettingsMixin:
    """Timeline recording and workspace configuration."""

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


class FeatureFlagsSettingsMixin:
    """Agent enhancement feature flags, hallucination prevention, and research settings."""

    # Skills configuration
    max_enabled_skills: int = 5  # Maximum concurrent enabled skills per user

    # Agent Enhancement Feature Flags (Phase 0+)
    feature_plan_validation_v2: bool = False
    feature_reflection_advanced: bool = False
    feature_context_optimization: bool = False
    feature_tool_tracing: bool = True
    feature_reward_hacking_detection: bool = False
    feature_failure_prediction: bool = False
    feature_circuit_breaker_adaptive: bool = False
    feature_workflow_checkpointing: bool = True
    feature_shadow_mode: bool = True

    # Hallucination Prevention Feature Flags (Phase 1-6)
    feature_url_verification: bool = True  # Verify cited URLs exist and were visited
    feature_claim_provenance: bool = True  # Track claim-to-source linkage
    feature_enhanced_grounding: bool = True  # Numeric/entity verification in sources
    feature_hallucination_verification: bool = (
        True  # LLM-as-Judge grounding verification (enabled by default for factual verification gate)
    )
    feature_semantic_citation_validation: bool = True  # Semantic matching for citations
    feature_strict_numeric_verification: bool = True  # Reject unverified numeric claims
    feature_reject_ungrounded_reports: bool = False  # Start permissive, can enable later
    feature_delivery_integrity_gate: bool = True  # Enforce truncation/completeness gate
    feature_delivery_scope_isolation: bool = False  # Isolate deliverables per run in reused sessions

    # Adaptive Verbosity + Clarification (2026-02-09 plan)
    feature_adaptive_verbosity_shadow: bool = False

    # Agent Robustness Feature Flags (2026-02-13 plan)
    # Phase 0: Wire OutputGuardrails into PlanActFlow SUMMARIZING
    enable_output_guardrails_in_flow: bool = True
    # Phase 1: Extract RequestContract at ingress
    enable_request_contract: bool = True
    # Phase 2: Use structured Step fields instead of free-form
    enable_structured_step_model: bool = False
    # Phase 3: Entity/relevance fidelity in delivery gate
    enable_delivery_fidelity_v2: bool = False
    delivery_fidelity_mode: str = "shadow"  # "shadow" | "warn" | "enforce"
    # Phase 4: Entity fidelity in search queries
    enable_search_fidelity_guardrail: bool = False
    # Phase 5: Contradictory prompt detection
    enable_contradiction_clarification: bool = False
    # Research Report: brief confirmation MessageEvent after ReportEvent delivery
    confirmation_summary_enabled: bool = False

    # Pre-Planning Search: inject real-time web results into planning prompts
    feature_pre_planning_search: bool = False

    # Fast draft planning — uses FAST_MODEL for research tasks, skips verification
    # When enabled for research_mode tasks: planner uses FAST_MODEL, verification skipped
    # if plan has <= fast_draft_plan_max_steps steps
    feature_fast_draft_plan: bool = True
    fast_draft_plan_max_steps: int = 5

    # Chart Generation (Plotly Migration Phase 4)
    feature_plotly_charts_enabled: bool = True  # Use Plotly charts instead of SVG

    # Skill activation policy
    skill_auto_trigger_enabled: bool = False  # Default OFF: explicit activation only

    # Agent Enhancement Feature Flags (Phases 1-5)
    # Phase 1: Python 3.11+ TaskGroup Migration
    # Default flipped to True (2026-02): gather_compat() + sandbox_manager +
    # parallel_executor + memory_service are all TaskGroup-ready. Python 3.11+
    # confirmed in project.  Set FEATURE_TASKGROUP_ENABLED=false to revert.
    feature_taskgroup_enabled: bool = True  # Use TaskGroup instead of asyncio.gather
    # Phase 2: SSE Streaming v2
    feature_sse_v2: bool = False  # Enhanced streaming API with structured events
    # SSE reconnection: grace period before cancelling a non-terminal stream exhaustion.
    # When the SSE stream exhausts but the agent is still running, defer cancellation
    # by this many seconds to allow the frontend to reconnect seamlessly.
    sse_disconnect_non_terminal_grace_seconds: float = 120.0
    # SSE operational parameters
    sse_session_poll_interval_seconds: int = 10  # Polling interval for session SSE streams
    sse_ws_ping_interval_seconds: int = 20  # WebSocket ping interval for sandbox proxying
    sse_ws_ping_timeout_seconds: int = 10  # WebSocket ping timeout for sandbox proxying
    # Phase 3: Zero-Hallucination Defense
    feature_structured_outputs: bool = False  # Pydantic structured LLM outputs with validation
    # Phase 4: Parallel Memory Architecture
    feature_parallel_memory: bool = False  # Parallel MongoDB/Qdrant memory writes

    # Continuous Conversational Context Storage (real-time Qdrant vectorization)
    feature_conversation_context_enabled: bool = True  # Master toggle (enabled for real-time context retrieval)
    conversation_context_buffer_size: int = 5  # Turns before batch flush to Qdrant
    conversation_context_flush_interval_seconds: float = 10.0  # Max seconds between flushes
    conversation_context_sliding_window: int = 5  # Recent turns always included (no embedding needed)
    conversation_context_semantic_top_k: int = 5  # Semantic results from current session
    conversation_context_cross_session_top_k: int = 0  # Cross-session results (0 = disabled, prevents context leakage)
    conversation_context_min_content_length: int = 20  # Skip trivial turns
    conversation_context_cross_session_min_score: float = 0.75  # Strict threshold to prevent cross-session topic drift
    conversation_context_retrieval_timeout_seconds: float = 2.0  # Retrieval timeout (returns empty)
    bm25_corpus_max_documents: int = 200  # Sliding window cap for BM25 corpus growth (0 = unlimited)

    # Incremental memory extraction during sessions (Phase 5)
    incremental_memory_enabled: bool = True  # Extract memories mid-session (every N turns)
    incremental_memory_interval: int = 5  # Extract every N conversation turns

    # Advanced reasoning features (disabled by default, enable per-use-case)
    feature_tree_of_thoughts: bool = False  # Use ToT exploration for complex planning
    feature_self_consistency: bool = False  # Use self-consistency checks during verification

    # GPT-5.3 Plan: Eval, Meta-Cognition, HITL gates (shadow mode by default)
    enable_eval_gates: bool = True  # WP-3: Ragas eval gate at summarization
    feature_meta_cognition_enabled: bool = True  # Phase 3: Gap-aware planning prompt injection
    feature_hitl_enabled: bool = True  # Phase 4: HITL interrupt for high-risk tool calls

    # File sweep deduplication (only targets artifact patterns: report*, analysis*, etc.)
    feature_sweep_dedup_enabled: bool = True  # Disable to sync all discovered files without dedup

    # Live Shell & File Streaming (real-time terminal output + file creation visibility)
    feature_live_shell_streaming: bool = False  # DEPRECATED: use terminal_live_streaming_enabled instead (UX v2)
    live_shell_poll_interval_ms: int = 500  # Polling interval in milliseconds
    live_shell_max_polls: int = 600  # Max polls before stopping (300s at 500ms)
    feature_live_file_streaming: bool = False  # Emit incremental ToolStreamEvents for file_write

    # Verification timeout — auto-pass if verification exceeds this (seconds). 0 = disabled.
    verification_timeout_seconds: float = 8.0

    # Wall-clock limit per step (seconds). 0 = disabled. Env: MAX_STEP_WALL_CLOCK_SECONDS
    # 900s (15 min) accommodates research steps with 8-10 slow LLM calls (~60s each on
    # GLM-5) plus browser/search tool overhead, preventing premature force-failure.
    max_step_wall_clock_seconds: float = 900.0

    # Graduated step wall-clock pressure (design 2A)
    # Per-depth budgets override max_step_wall_clock_seconds when research_depth is known
    step_budget_quick_seconds: float = 300.0  # QUICK research: 5 min
    step_budget_standard_seconds: float = 600.0  # STANDARD research: 10 min
    step_budget_deep_seconds: float = 900.0  # DEEP research: 15 min

    # Architecture Enhancement Plan — Phase 2: Token Budget Manager & Context Handler
    feature_token_budget_manager: bool = True  # Proactive phase-level token budgeting

    # Hard cap: planning phase may never exceed this fraction of total budget,
    # regardless of research mode profile. Prevents runaway planning.
    token_budget_planning_cap: float = 0.30

    # Repetitive same-tool loop detection (2026-03-01 session reliability fixes)
    feature_repetitive_tool_detection_enabled: bool = True

    # Tool efficiency monitor settings (design 2C)
    tool_efficiency_read_threshold: int = 5
    tool_efficiency_strong_threshold: int = 6
    tool_efficiency_same_tool_threshold: int = 4
    tool_efficiency_same_tool_strong_threshold: int = 6

    # Hallucination rate escalation (2026-03-01 session reliability fixes)
    feature_hallucination_escalation_enabled: bool = True
    hallucination_escalation_threshold: float = 0.15  # 15% hallucination rate triggers escalation
    hallucination_escalation_min_samples: int = 10  # Min tool calls before rate is meaningful

    # Hallucination mitigation thresholds (design 4B)
    # LLM-as-Judge verification uses claim-level binary verdicts instead of
    # token-level probabilities.  Coarser but more interpretable, avoids the
    # false-positive problem where LettuceDetect flagged stylistic paraphrasing.
    # Industry standard: LLM Guard uses 0.30.  We use graduated response:
    # warn at 15% with disclaimer, block at 50% and re-summarize.
    # Raised block from 0.40 to 0.50 after benchmark showed claim-level verifiers
    # have 20-30% false-positive rates on paraphrased content.
    # Env override: HALLUCINATION_WARN_THRESHOLD, HALLUCINATION_BLOCK_THRESHOLD
    hallucination_warn_threshold: float = 0.15  # 15% -> reliability notice appended
    hallucination_block_threshold: float = 0.60  # 60% -> block delivery, re-summarize
    # Raised from 0.50 to 0.60: claim-level verifiers have 20-30% false-positive rates
    # on paraphrased research statistics, and the 16-32K char grounding context is often
    # too narrow to contain the source passage for a cited statistic. E2E testing showed
    # all 4 research tasks hitting 65-68% unsupported despite correct citations.
    hallucination_annotate_spans: bool = False  # Annotate flagged claims in output
    hallucination_grounding_context_size: int = (
        24000  # Chars of source context for grounding verifier (raised from 16K)
    )
    hallucination_grounding_context_deep: int = 48000  # Expanded context for DEEP research (raised from 32K)
    hallucination_verifier_model: str | None = None  # Override model for verification (default: FAST_MODEL)
    hallucination_verifier_timeout: float = 60.0  # Must exceed degraded-mode timeout margin; 30s caused silent skips
    hallucination_max_claims: int = 25  # Cap extracted claims (raised from 20 for more thorough checking)
    reranker_provider: str = "jina"  # "jina" (API) or "none" (skip reranking)

    # Context compression thresholds
    # Trigger compression earlier (80%) to give headroom instead of near-exhaustion (96%+)
    context_compression_trigger_pct: float = 0.80
    # Target after compression: compress down to 65% to leave room for more turns
    context_compression_target_pct: float = 0.65

    # Compression context preservation — inject failure lessons during token budget compression
    feature_compression_context_preservation_enabled: bool = True

    # URL Failure Guard — 3-tier auto-correction for LLM URL hallucination (2026-03-02)
    feature_url_failure_guard_enabled: bool = True

    # ── Tiered External Memory Architecture (2026-03) ─────────────────
    # C1: Offload large tool results (>4K chars) to LRU cache, keep preview in conversation
    feature_tool_result_store_enabled: bool = True
    # C2: Replace destructive smart_compact() with 3-tier graduated decay
    feature_graduated_compaction_enabled: bool = True
    # C3: Persistent scratchpad for agent working notes (survives all compaction)
    feature_scratchpad_enabled: bool = False
    # C4: Emergency LLM-powered structured compaction at >80% budget
    feature_structured_compaction_enabled: bool = False

    # ── LLM Middleware Pipeline (Enhancement Plan 2026-02) ──────────────────
    # Phase 1: Middleware pipeline — compose cross-cutting concerns as chainable
    # middlewares instead of inline retry/error code in each provider.
    # Wired into LLM providers: enables 7-layer retry/circuit-breaker chain.
    feature_llm_middleware_pipeline: bool = True

    # Phase 2: Retry budget — cap total retries across all middleware layers
    # per task to prevent cascading quota exhaustion.
    # NOT YET WIRED: requires middleware pipeline (Phase 1) to be active.
    feature_llm_retry_budget: bool = False

    # Phase 3: Provider fallback — on primary exhaustion, try next provider in
    # llm_provider_fallback_chain before raising.
    feature_llm_provider_fallback: bool = False

    # Phase 3: Health scoring — weight provider selection by sliding-window
    # latency + error rate (shadow mode: compute + log only, no routing).
    # NOT YET WIRED: requires middleware pipeline (Phase 1) to be active.
    feature_llm_health_scoring: bool = False

    # Phase 5: Dynamic context windows — derive token budget from model's
    # actual max_context_window via the capabilities registry.
    feature_llm_dynamic_context: bool = False

    # NOTE: Phase 1 (ToolName enum) and Phase 3 (God Class Decomposition) are
    # permanently enabled — no rollback flags needed. ToolName, StepExecutor,
    # ResponseGenerator, OutputVerifier, SourceTracker, PhaseRouter,
    # FlowStepExecutor, ErrorRecoveryHandler, FileSyncManager are unconditionally
    # active and have fully replaced the inline implementations.


class KeyPoolSettingsMixin:
    """API key pool circuit breaker configuration (design 5A)."""

    key_pool_cb_threshold: int = 5  # Consecutive failures to trip breaker
    key_pool_cb_reset_timeout_5xx: int = 300  # Seconds before 5xx breaker resets
    key_pool_cb_reset_timeout_429: int = 45  # Seconds before 429 breaker resets
    key_pool_exhaustion_recovery_ttl: int = 1800  # Seconds before exhausted pool re-checks


class ResearchSettingsMixin:
    """Research quality, citation, and benchmark configuration."""

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

    # Feature flags
    feature_enhanced_research: bool = False  # Enable enhanced research flow
    feature_phased_research: bool = False  # Enable phased research workflow for deep research


class PromptOptimizationSettingsMixin:
    """DSPy/GEPA prompt optimization feature flags and runtime policy.

    All flags default to safe values (no behavioral change in production).
    """

    # Master pipeline flag: allows running offline optimization jobs.
    feature_prompt_optimization_pipeline: bool = False

    # Runtime flag: allows applying optimized profile patches to prompts.
    # When False, optimization runs offline but patches are never applied.
    feature_prompt_profile_runtime: bool = True

    # Shadow mode flag: compute optimization deltas without applying patches.
    # Emits pythinker_prompt_shadow_delta metrics for monitoring.
    feature_prompt_profile_shadow: bool = True

    # Canary rollout: fraction (0-100) of sessions to receive profile patches.
    # 0 = apply to all sessions when runtime is enabled.
    prompt_profile_canary_percent: int = 0

    # Explicit active profile ID (overrides DB-active flag when set).
    prompt_profile_active_id: str | None = None

    # Minimum cases required before optimization is allowed to run.
    prompt_optimization_min_cases: int = 100

    # DSPy performance tuning
    # Number of parallel threads for dspy.Evaluate and MIPROv2 search.
    # Higher values reduce wall-clock time proportionally (I/O-bound LLM calls).
    dspy_num_threads: int = 4
    # Few-shot bootstrapped demos generated from successful teacher traces.
    dspy_max_bootstrapped_demos: int = 4
    # Labeled examples from the trainset used as in-context demonstrations.
    dspy_max_labeled_demos: int = 4
    # Minibatch size for MIPROv2 candidate scoring (smaller = faster iteration).
    dspy_minibatch_size: int = 25
    # Persistent disk cache directory for DSPy/LiteLLM LLM call results.
    # Prevents re-spending tokens on identical evaluation calls across runs.
    dspy_cache_dir: str = "/app/data/dspy_cache"

    # ── LeadAgentRuntime (DeerFlow convergence) ─────────────────────────
    # Master switch: when False, AgentTaskRunner skips runtime construction entirely.
    feature_lead_agent_runtime: bool = False
    # Individual middleware toggles (only effective when master switch is on):
    feature_runtime_workspace_contracts: bool = True
    feature_runtime_clarification_gate: bool = True
    feature_runtime_dangling_recovery: bool = True
    feature_runtime_quality_gates: bool = True
    feature_runtime_insight_promotion: bool = True
    feature_runtime_capability_manifest: bool = True
    feature_runtime_skill_discovery: bool = True
    feature_runtime_research_trace: bool = True
    feature_runtime_delegate_tool: bool = True
    feature_runtime_channel_overlay: bool = True

    # ── Agent UX v2 Feature Flags ─────────────────────────────────────────
    # Browser Choreography (human-like timing in browser actions)
    browser_choreography_enabled: bool = True
    browser_choreography_profile: str = "professional"  # fast/professional/cinematic
    browser_screencast_include_chrome_ui: bool = (
        True  # sandbox-side only: configure via SCREENCAST_INCLUDE_CHROME_UI env on sandbox container
    )

    # Background preview browsing (after search results)
    # How many top URLs to visit in background after wide_research/info_search_web
    browser_background_preview_count: int = 5
    # Dwell time (seconds) on each page during background preview (user watches in screencast)
    browser_background_preview_dwell: float = 7.0
    # Auto-scroll during background preview so user sees page content
    browser_background_preview_scroll: bool = True

    # Terminal Enhancement (live streaming, mastery prompts)
    terminal_live_streaming_enabled: bool = True
    terminal_mastery_prompt_enabled: bool = True
    terminal_proactive_preference_enabled: bool = True

    # Skill-Driven Architecture (auto-detection of relevant skills)
    skill_auto_detection_enabled: bool = True
    skill_auto_detection_threshold: float = 0.6
    # skill_first_planning_enabled removed — was declared but never read by any code path
    skill_ui_events_enabled: bool = True

    # Proactive skill task analysis (multi-signal semantic matching beyond regex)
    skill_task_analysis_enabled: bool = True
    skill_task_analysis_threshold: float = 0.5
    skill_task_analysis_max_results: int = 2

    # Enterprise-grade skill enforcement (Phase 2: Hardened Skill System)
    skill_force_first_invocation: bool = True  # Force skill_invoke on first turn when skills detected
    skill_enforcement_prompt_enabled: bool = True  # Hardened system prompt with mandatory protocol
    skill_enforcement_nudge_enabled: bool = True  # Nudge after N iterations without skill invocation
    skill_enforcement_nudge_after_iterations: int = 3  # Iterations before nudge fires
    skill_strict_schema_enabled: bool = True  # Enum constraints on skill_name in tool schema


class TypoCorrectionSettingsMixin:
    """Typo correction (PromptQuickValidator) configuration."""

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
