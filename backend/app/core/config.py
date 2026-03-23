"""Application settings.

The Settings class composes domain-specific mixin groups via multiple inheritance.
All field names and environment variable names are unchanged — this refactoring is
purely organizational and introduces no breaking changes.

Domain-specific settings are defined in:
- config_database.py  — MongoDB, Redis, MinIO, Qdrant
- config_llm.py       — LLM providers, embeddings, concurrency
- config_sandbox.py   — Sandbox lifecycle, pool, browser, screenshots
- config_auth.py      — Auth, JWT, CORS, rate limiting, metrics
- config_features.py  — Feature flags, search, observability, research
- config_enums.py     — Shared enums (StreamingMode, FlowMode)
"""

import logging
import secrets
import threading
import warnings
from functools import lru_cache
from typing import ClassVar

from pydantic import computed_field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.core.config_auth import (
    AuthSettingsMixin,
    CORSSettingsMixin,
    EmailSettingsMixin,
    JWTSettingsMixin,
    MetricsAuthSettingsMixin,
)
from app.core.config_channels import ChannelSettingsMixin
from app.core.config_database import (
    DatabaseSettingsMixin,
    QdrantSettingsMixin,
    RedisSettingsMixin,
    SLOSettingsMixin,
    StorageSettingsMixin,
)
from app.core.config_deals import DealScraperSettingsMixin
from app.core.config_enums import FlowMode, StreamingMode
from app.core.config_features import (
    AgentSafetySettingsMixin,
    FeatureFlagsSettingsMixin,
    KeyPoolSettingsMixin,
    MultiAgentSettingsMixin,
    ObservabilitySettingsMixin,
    PromptOptimizationSettingsMixin,
    ResearchSettingsMixin,
    SearchSettingsMixin,
    TimelineSettingsMixin,
    TypoCorrectionSettingsMixin,
)
from app.core.config_knowledge import KnowledgeBaseSettingsMixin
from app.core.config_llm import (
    EmbeddingSettingsMixin,
    LLMConcurrencySettingsMixin,
    LLMSettingsMixin,
    LLMTimeoutSettingsMixin,
)
from app.core.config_sandbox import (
    BrowserSettingsMixin,
    SandboxPoolSettingsMixin,
    SandboxSettingsMixin,
    ScreenshotSettingsMixin,
)
from app.core.config_scraping import ScrapingSettingsMixin
from app.core.config_stealth import StealthSettingsMixin

# Re-export enums for backward compatibility (existing code imports from config)
__all__ = ["FlowMode", "Settings", "StreamingMode", "get_feature_flags", "get_settings"]

logger = logging.getLogger(__name__)


class Settings(
    # Database layer
    DatabaseSettingsMixin,
    RedisSettingsMixin,
    StorageSettingsMixin,
    QdrantSettingsMixin,
    # LLM layer
    LLMSettingsMixin,
    EmbeddingSettingsMixin,
    LLMConcurrencySettingsMixin,
    LLMTimeoutSettingsMixin,
    # Sandbox / Browser layer
    SandboxSettingsMixin,
    SandboxPoolSettingsMixin,
    BrowserSettingsMixin,
    ScreenshotSettingsMixin,
    # Auth / Security layer
    AuthSettingsMixin,
    EmailSettingsMixin,
    JWTSettingsMixin,
    CORSSettingsMixin,
    MetricsAuthSettingsMixin,
    # Features / Observability layer
    SearchSettingsMixin,
    AgentSafetySettingsMixin,
    MultiAgentSettingsMixin,
    ObservabilitySettingsMixin,
    TimelineSettingsMixin,
    FeatureFlagsSettingsMixin,
    KeyPoolSettingsMixin,
    ResearchSettingsMixin,
    TypoCorrectionSettingsMixin,
    PromptOptimizationSettingsMixin,
    KnowledgeBaseSettingsMixin,
    ScrapingSettingsMixin,
    StealthSettingsMixin,
    DealScraperSettingsMixin,
    SLOSettingsMixin,
    # Channel gateway / cron / skills / subagent layer
    ChannelSettingsMixin,
    # BaseSettings must come last
    BaseSettings,
):
    """Application settings loaded from environment variables and .env file.

    This class inherits from domain-specific mixin groups for organization.
    All field names match their corresponding environment variables directly.
    """

    _emitted_security_warnings: ClassVar[set[str]] = set()
    _startup_banner_emitted: ClassVar[bool] = False

    # Core environment settings
    environment: str = "development"  # "development", "staging", "production"
    debug: bool = False

    # Language configuration
    default_language: str = "English"  # Default language for agent responses

    # Unified flow engine selection (replaces legacy booleans)
    flow_mode: FlowMode = FlowMode.PLAN_ACT

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        use_enum_values=True,
    )

    # --- Computed fields ---

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

    @computed_field
    @property
    def is_production(self) -> bool:
        """Check if running in production environment."""
        return self.environment.lower() == "production"

    @computed_field
    @property
    def is_development(self) -> bool:
        """Check if running in development environment."""
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
        """Get CORS origins as a list."""
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

    @computed_field
    @property
    def effective_balanced_model(self) -> str:
        """Get the effective balanced model.

        Returns balanced_model if set, otherwise falls back to model_name.
        Context7 validated: Pydantic v2 @computed_field pattern for derived settings.
        """
        return self.balanced_model or self.model_name

    @computed_field
    @property
    def effective_workflow_idle_timeout(self) -> int:
        """Idle timeout enforced in the event-streaming loop (seconds).

        Guarantees that the configured value is always large enough for an LLM
        call to complete a full attempt *plus one retry* before the watchdog fires:

            min_required = 2 x llm_request_timeout + 60s margin

        If ``workflow_idle_timeout_seconds`` is already >= min_required the
        configured value is returned unchanged.  When it is smaller (e.g. left at
        a legacy 300s default while llm_request_timeout is also 300s) the floor is
        applied and a warning is emitted at startup so operators can correct their
        config.
        """
        # +60s = safety buffer covering: first-retry delay (1s base_delay in openai_llm.py)
        # plus network jitter and queue overhead. Default of 660s satisfies this exactly.
        min_required = int(self.llm_request_timeout * 2) + 60
        configured = self.workflow_idle_timeout_seconds
        if configured < min_required:
            logger.warning(
                "workflow_idle_timeout_seconds=%d is less than the LLM retry budget "
                "(%ds = 2x llm_request_timeout %.0fs + 60s margin); "
                "auto-flooring to %d to prevent idle-timeout races with slow providers.",
                configured,
                min_required,
                self.llm_request_timeout,
                min_required,
            )
            return min_required
        return configured

    @computed_field
    @property
    def browser_blocked_types_set(self) -> set[str]:
        """Parse browser_blocked_resource_types into a set."""
        if not self.browser_blocked_resource_types:
            return set()
        return {t.strip() for t in self.browser_blocked_resource_types.split(",") if t.strip()}

    # --- Secret generation helpers ---

    def _generate_jwt_secret(self) -> str:
        """Generate a secure JWT secret for development."""
        return secrets.token_urlsafe(32)

    def _generate_password_salt(self) -> str:
        """Generate a secure password salt."""
        return secrets.token_urlsafe(16)

    # --- Pydantic model validators ---

    @model_validator(mode="after")
    def validate_jwt_secret_for_auth(self) -> "Settings":
        """Refuse to start if auth is enabled but JWT secret is missing."""
        if self.auth_provider != "none" and not self.jwt_secret_key:
            raise ValueError(
                "jwt_secret_key is required when auth_provider is not 'none'. Set JWT_SECRET_KEY environment variable."
            )
        return self

    # --- Validation ---

    def validate(self) -> None:
        """Validate configuration settings with comprehensive security checks."""
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
        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            errors.append("ANTHROPIC_API_KEY is required for anthropic provider")
        elif self.llm_provider == "openai" and not self.api_key:
            errors.append("API_KEY is required for OpenAI provider")

        # Credential encryption key
        if self.allow_credential_access and not self.credential_encryption_key and self.is_production:
            security_warnings.append(
                "CREDENTIAL_ENCRYPTION_KEY not set but credential access is enabled. "
                "Credentials will be stored without encryption."
            )

        # === WARNINGS ===

        # Auth provider "none" — block in production, warn in development
        if self.auth_provider == "none":
            if self.is_production:
                raise ValueError(
                    "AUTH_PROVIDER='none' is forbidden in production. "
                    "Set AUTH_PROVIDER to 'password' or 'local' and configure credentials."
                )
            security_warnings.append(
                "AUTH_PROVIDER is set to 'none' - authentication is disabled. "
                "This should only be used for development/testing."
            )

        # Debug mode warning
        if self.debug and self.is_production:
            security_warnings.append("DEBUG mode is enabled in production - this may expose sensitive information")

        # Metrics auth validation — warn loudly in production
        if not self.metrics_password and self.is_production:
            security_warnings.append(
                "[SECURITY] METRICS_PASSWORD not set in production — /metrics endpoint "
                "is unauthenticated. Set METRICS_PASSWORD in .env to enforce HTTP Basic Auth."
            )
        elif self.metrics_password in ["changeme", "password", "admin"]:
            security_warnings.append("METRICS_PASSWORD is using an insecure default value")

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
            if self.is_production:
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


_get_settings_init_lock = threading.Lock()


@lru_cache
def get_settings() -> Settings:
    """Get application settings."""
    with _get_settings_init_lock:
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
            "hitl_enabled": False,
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
            "hallucination_verification": True,
            "semantic_citation_validation": True,
            "strict_numeric_verification": True,
            "reject_ungrounded_reports": False,
            "delivery_integrity_gate": True,
            "delivery_scope_isolation": False,
            "adaptive_verbosity_shadow": False,
            "pre_planning_search": False,
            "confirmation_summary_enabled": False,
            "url_failure_guard": True,
            # Tiered External Memory
            "tool_result_store": True,
            "graduated_compaction": True,
            "scratchpad": False,
            "structured_compaction": False,
            # Live shell streaming
            "live_shell_streaming": False,
            "live_shell_poll_interval_ms": 500,
            "live_shell_max_polls": 600,
            # Architecture Enhancement Plan — Phase 2
            "token_budget_manager": False,
            # Live file streaming (future)
            "live_file_streaming": False,
            # LeadAgentRuntime (DeerFlow convergence)
            "feature_lead_agent_runtime": False,
            "feature_runtime_workspace_contracts": True,
            "feature_runtime_clarification_gate": True,
            "feature_runtime_dangling_recovery": True,
            "feature_runtime_quality_gates": True,
            "feature_runtime_insight_promotion": True,
            "feature_runtime_capability_manifest": True,
            "feature_runtime_skill_discovery": True,
            "feature_runtime_research_trace": True,
            "feature_runtime_delegate_tool": True,
            "feature_runtime_channel_overlay": True,
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
        "hitl_enabled": settings.feature_hitl_enabled,
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
        "hallucination_verification": settings.feature_hallucination_verification,
        "semantic_citation_validation": settings.feature_semantic_citation_validation,
        "strict_numeric_verification": settings.feature_strict_numeric_verification,
        "reject_ungrounded_reports": settings.feature_reject_ungrounded_reports,
        "delivery_integrity_gate": settings.feature_delivery_integrity_gate,
        "delivery_scope_isolation": settings.feature_delivery_scope_isolation,
        "adaptive_verbosity_shadow": settings.feature_adaptive_verbosity_shadow,
        "pre_planning_search": settings.feature_pre_planning_search,
        "confirmation_summary_enabled": settings.confirmation_summary_enabled,
        "url_failure_guard": settings.feature_url_failure_guard_enabled,
        # Tiered External Memory
        "tool_result_store": settings.feature_tool_result_store_enabled,
        "graduated_compaction": settings.feature_graduated_compaction_enabled,
        "scratchpad": settings.feature_scratchpad_enabled,
        "structured_compaction": settings.feature_structured_compaction_enabled,
        # Live shell streaming — terminal_live_streaming_enabled (UX v2, default=True) subsumes
        # the legacy feature_live_shell_streaming flag (default=False, deprecated).
        "live_shell_streaming": settings.feature_live_shell_streaming or settings.terminal_live_streaming_enabled,
        "live_shell_poll_interval_ms": settings.live_shell_poll_interval_ms,
        "live_shell_max_polls": settings.live_shell_max_polls,
        # Architecture Enhancement Plan — Phase 2
        "token_budget_manager": settings.feature_token_budget_manager,
        # Live file streaming (future)
        "live_file_streaming": settings.feature_live_file_streaming,
        # LeadAgentRuntime (DeerFlow convergence)
        "feature_lead_agent_runtime": settings.feature_lead_agent_runtime,
        "feature_runtime_workspace_contracts": settings.feature_runtime_workspace_contracts,
        "feature_runtime_clarification_gate": settings.feature_runtime_clarification_gate,
        "feature_runtime_dangling_recovery": settings.feature_runtime_dangling_recovery,
        "feature_runtime_quality_gates": settings.feature_runtime_quality_gates,
        "feature_runtime_insight_promotion": settings.feature_runtime_insight_promotion,
        "feature_runtime_capability_manifest": settings.feature_runtime_capability_manifest,
        "feature_runtime_skill_discovery": settings.feature_runtime_skill_discovery,
        "feature_runtime_research_trace": settings.feature_runtime_research_trace,
        "feature_runtime_delegate_tool": settings.feature_runtime_delegate_tool,
        "feature_runtime_channel_overlay": settings.feature_runtime_channel_overlay,
    }
