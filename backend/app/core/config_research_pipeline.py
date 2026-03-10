"""Deterministic research pipeline settings mixin.

Controls source selection, evidence acquisition, confidence thresholds,
synthesis gate policy (default + relaxed), and telemetry for the
deterministic research pipeline introduced in the 2026-03-10 sprint.

Pipeline modes
--------------
shadow   — pipeline runs alongside the existing flow; its decisions are
           logged but never enforced.  Safe to deploy without changing UX.
enforced — pipeline gates synthesis and can block report generation when
           quality thresholds are not met.

All fields are environment-variable overridable via pydantic-settings
automatic uppercase mapping (e.g. RESEARCH_SOURCE_SELECT_COUNT=6).
"""

from typing import Literal


class ResearchPipelineSettingsMixin:
    """Policy-driven research pipeline configuration."""

    # ── Feature flags ──────────────────────────────────────────────────────
    research_deterministic_pipeline_enabled: bool = True
    research_pipeline_mode: Literal["shadow", "enforced"] = "shadow"

    # ── Source selection ───────────────────────────────────────────────────
    research_source_select_count: int = 4  # Top-N sources passed to acquisition
    research_source_max_per_domain: int = 1  # Anti-monopoly: max URLs per domain
    research_source_allow_multi_page_domains: bool = True  # Allow >1 URL from same domain when overridden

    # ── Source scoring weights (must sum to ~1.0) ──────────────────────────
    research_weight_relevance: float = 0.35
    research_weight_authority: float = 0.25
    research_weight_freshness: float = 0.20
    research_weight_rank: float = 0.20

    # ── Evidence acquisition ───────────────────────────────────────────────
    research_acquisition_concurrency: int = 4  # Parallel fetch workers
    research_acquisition_timeout_seconds: float = 30.0  # Per-source fetch timeout
    research_excerpt_chars: int = 2000  # Max chars extracted per source
    research_full_content_offload: bool = True  # Store full content to disk/cache

    # ── Confidence thresholds ──────────────────────────────────────────────
    research_soft_fail_verify_threshold: int = 2  # Sources needed to reach VERIFY confidence
    research_soft_fail_required_threshold: int = 3  # Sources needed to reach REQUIRED confidence
    research_thin_content_chars: int = 500  # Below this → LOW confidence regardless
    research_boilerplate_ratio_threshold: float = 0.6  # Ratio above which content is boilerplate

    # ── Synthesis gate — default policy ───────────────────────────────────
    research_min_fetched_sources: int = 3  # Minimum successfully fetched sources
    research_min_high_confidence: int = 2  # Minimum HIGH/REQUIRED confidence sources
    research_require_official_source: bool = True  # At least one .gov/.edu/official domain
    research_require_independent_source: bool = True  # At least one non-Wikipedia/non-AI source

    # ── Synthesis gate — relaxed policy (niche topics) ────────────────────
    research_relaxation_enabled: bool = True  # Allow gate relaxation when default fails
    research_relaxed_min_fetched_sources: int = 2
    research_relaxed_min_high_confidence: int = 1
    research_relaxed_require_official_source: bool = False

    # ── Telemetry ──────────────────────────────────────────────────────────
    research_telemetry_enabled: bool = True  # Emit pipeline metrics/spans
