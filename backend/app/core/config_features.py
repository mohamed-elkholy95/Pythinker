"""Feature flags, agent behavior, observability, and research settings mixins.

Contains configuration for agent feature flags, safety limits, autonomy controls,
multi-agent orchestration, observability (logging, OTel, alerting), search providers,
research quality settings, and typo correction.
"""

from app.core.search_provider_policy import DEFAULT_SEARCH_PROVIDER_CHAIN


class SearchSettingsMixin:
    """Search engine API keys and provider configuration."""

    search_provider: str | None = "duckduckgo"  # "google", "bing", "duckduckgo", "brave", "tavily", "serper", "exa"
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

    # Search key pool recovery
    serper_quota_cooldown_seconds: int = 1800  # Cooldown after quota exhaustion (default 30min)

    # Search API budget limits (per agent task)
    max_search_api_calls_per_task: int = 30  # Hard cap on API calls per task
    max_wide_research_queries: int = 5  # Max queries in a single wide_research call
    max_wide_research_calls_per_task: int = 3  # Max wide_research invocations per task
    search_cache_ttl: int = 3600  # Cache TTL in seconds (default 1h)
    search_dedup_skip_existing: bool = True  # Skip API call if TaskStateManager says already searched


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
    max_tokens_per_run: int = 500000  # Token limit across all LLM calls
    max_cost_usd: float | None = None  # Optional cost limit

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
    feature_cove_verification: bool = False  # Chain-of-Verification for reports (deprecated — use lettuce)
    feature_lettuce_verification: bool = (
        True  # LettuceDetect encoder-based hallucination detection (enabled by default for factual verification gate)
    )
    lettuce_model_path: str = "KRLabsOrg/tinylettuce-ettin-17m-en"  # HF model path (CPU-friendly, 17M params)
    lettuce_confidence_threshold: float = 0.8  # Min hallucination score to flag a span (raised from 0.5 to reduce false positives on LLM-synthesized content)
    lettuce_min_response_length: int = 200  # Skip verification for short responses
    feature_semantic_citation_validation: bool = True  # Semantic matching for citations
    feature_strict_numeric_verification: bool = True  # Reject unverified numeric claims
    feature_reject_ungrounded_reports: bool = False  # Start permissive, can enable later
    feature_delivery_integrity_gate: bool = True  # Enforce truncation/completeness gate

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
    feature_live_shell_streaming: bool = False  # Poll sandbox for real-time shell output
    live_shell_poll_interval_ms: int = 500  # Polling interval in milliseconds
    live_shell_max_polls: int = 600  # Max polls before stopping (300s at 500ms)
    feature_live_file_streaming: bool = False  # Emit incremental ToolStreamEvents for file_write

    # Wall-clock limit per step (seconds). 0 = disabled. Env: MAX_STEP_WALL_CLOCK_SECONDS
    # Default 600s (10 min) catches runaway steps where slow LLM calls + high iteration
    # cap combine to span hours, while being generous for legitimate complex steps.
    max_step_wall_clock_seconds: float = 600.0

    # Architecture Enhancement Plan — Phase 2: Token Budget Manager & Context Handler
    feature_token_budget_manager: bool = False  # Proactive phase-level token budgeting

    # Repetitive same-tool loop detection (2026-03-01 session reliability fixes)
    feature_repetitive_tool_detection_enabled: bool = True

    # Hallucination rate escalation (2026-03-01 session reliability fixes)
    feature_hallucination_escalation_enabled: bool = True
    hallucination_escalation_threshold: float = 0.15  # 15% hallucination rate triggers escalation
    hallucination_escalation_min_samples: int = 10  # Min tool calls before rate is meaningful

    # Compression context preservation — inject failure lessons during token budget compression
    feature_compression_context_preservation_enabled: bool = True

    # DOM cursor injection — disable to use Konva overlay cursor instead
    feature_dom_cursor_injection: bool = False

    # URL Failure Guard — 3-tier auto-correction for LLM URL hallucination (2026-03-02)
    feature_url_failure_guard_enabled: bool = True

    # ── LLM Middleware Pipeline (Enhancement Plan 2026-02) ──────────────────
    # Phase 1: Middleware pipeline — compose cross-cutting concerns as chainable
    # middlewares instead of inline retry/error code in each provider.
    # Zero behaviour change when False.
    feature_llm_middleware_pipeline: bool = True

    # Phase 2: Retry budget — cap total retries across all middleware layers
    # per task to prevent cascading quota exhaustion.
    feature_llm_retry_budget: bool = True

    # Phase 3: Provider fallback — on primary exhaustion, try next provider in
    # llm_provider_fallback_chain before raising.
    feature_llm_provider_fallback: bool = False

    # Phase 3: Health scoring — weight provider selection by sliding-window
    # latency + error rate (shadow mode: compute + log only, no routing).
    feature_llm_health_scoring: bool = True

    # Phase 5: Dynamic context windows — derive token budget from model's
    # actual max_context_window via the capabilities registry.
    feature_llm_dynamic_context: bool = False

    # NOTE: Phase 1 (ToolName enum) and Phase 3 (God Class Decomposition) are
    # permanently enabled — no rollback flags needed. ToolName, StepExecutor,
    # ResponseGenerator, OutputVerifier, SourceTracker, PhaseRouter,
    # FlowStepExecutor, ErrorRecoveryHandler, FileSyncManager are unconditionally
    # active and have fully replaced the inline implementations.


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
