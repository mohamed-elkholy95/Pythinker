"""Domain-level configuration protocols.

Provides abstract interfaces for configuration and feature flags
so domain services never import from app.core.config directly.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class DomainFeatureFlags(Protocol):
    """Dict-like read access to feature flags.

    Satisfied by ``dict[str, bool]`` (the return type of
    ``get_feature_flags()`` in core) as well as any mapping-like object.
    """

    def get(self, key: str, default: bool = False) -> bool:
        """Return the flag value, falling back to *default*."""
        ...


@runtime_checkable
class DomainConfig(Protocol):
    """Subset of application settings consumed by the domain layer.

    Every property listed here must exist on ``app.core.config.Settings``
    so the concrete Settings object satisfies the protocol via duck typing.
    """

    # ── Feature toggles ─────────────────────────────────────────────
    @property
    def browser_agent_enabled(self) -> bool: ...

    @property
    def feature_tree_of_thoughts(self) -> bool: ...

    @property
    def feature_self_consistency(self) -> bool: ...

    @property
    def feature_structured_outputs(self) -> bool: ...

    @property
    def feature_parallel_memory(self) -> bool: ...

    @property
    def feature_taskgroup_enabled(self) -> bool: ...

    @property
    def search_prefer_browser(self) -> bool: ...

    # ── Sandbox / lifecycle ──────────────────────────────────────────
    @property
    def sandbox_lifecycle_mode(self) -> str: ...

    @property
    def sandbox_pool_enabled(self) -> bool: ...

    @property
    def sandbox_framework_enabled(self) -> bool: ...

    @property
    def sandbox_framework_required(self) -> bool: ...

    @property
    def uses_static_sandbox_addresses(self) -> bool: ...

    @property
    def qdrant_enabled(self) -> bool: ...

    @property
    def sandbox_address(self) -> str: ...

    # ── Execution limits ─────────────────────────────────────────────
    @property
    def enable_plan_verification(self) -> bool: ...

    @property
    def enable_multi_agent(self) -> bool: ...

    @property
    def enable_parallel_execution(self) -> bool: ...

    @property
    def parallel_max_concurrency(self) -> int: ...

    # ── Browser ──────────────────────────────────────────────────────
    @property
    def browser_init_timeout(self) -> float: ...

    @property
    def browser_stealth_enabled(self) -> bool: ...

    @property
    def browser_recaptcha_solver(self) -> str: ...

    # ── Embedding / memory ───────────────────────────────────────────
    @property
    def embedding_model(self) -> str: ...

    @property
    def embedding_api_key(self) -> str: ...

    @property
    def embedding_api_base(self) -> str: ...

    @property
    def api_key(self) -> str: ...

    # ── Model selection ──────────────────────────────────────────────
    @property
    def fast_model(self) -> str: ...

    @property
    def powerful_model(self) -> str: ...

    @property
    def max_tokens(self) -> int: ...

    @property
    def temperature(self) -> float: ...

    @property
    def effective_balanced_model(self) -> str: ...

    @property
    def adaptive_model_selection_enabled(self) -> bool: ...

    @property
    def summarization_max_tokens(self) -> int: ...

    # ── Feature toggles (extended) ────────────────────────────────────
    @property
    def scraping_tool_enabled(self) -> bool: ...

    @property
    def feature_workflow_checkpointing(self) -> bool: ...

    @property
    def security_critic_allow_medium_risk(self) -> bool: ...

    @property
    def enable_search_fidelity_guardrail(self) -> bool: ...

    @property
    def skill_ui_events_enabled(self) -> bool: ...

    # ── Typo correction ───────────────────────────────────────────────
    @property
    def typo_correction_rapidfuzz_enabled(self) -> bool: ...

    @property
    def typo_correction_symspell_enabled(self) -> bool: ...

    # ── Research / search ─────────────────────────────────────────────
    @property
    def deal_scraper_enabled(self) -> bool: ...

    # ── Skills ─────────────────────────────────────────────────────────
    @property
    def skills_system_enabled(self) -> bool: ...

    @property
    def skills_workspace_dir(self) -> str: ...

    @property
    def max_enabled_skills(self) -> int: ...

    # ── Charts ─────────────────────────────────────────────────────────
    @property
    def feature_plotly_charts_enabled(self) -> bool: ...

    @property
    def plotly_enabled(self) -> bool: ...

    # ── Cron ───────────────────────────────────────────────────────────
    @property
    def cron_service_enabled(self) -> bool: ...

    # ── Misc ─────────────────────────────────────────────────────────
    @property
    def default_language(self) -> str: ...

    @property
    def screenshot_capture_enabled(self) -> bool: ...

    @property
    def skill_auto_trigger_enabled(self) -> bool: ...

    @property
    def workspace_auto_init(self) -> bool: ...

    @property
    def workspace_lazy_init(self) -> bool: ...

    @property
    def workspace_default_project_name(self) -> str: ...

    @property
    def workspace_default_template(self) -> str: ...

    @property
    def mongodb_database(self) -> str: ...

    @property
    def llm_max_concurrent(self) -> int: ...

    @property
    def llm_queue_timeout(self) -> float: ...
