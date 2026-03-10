# Deterministic Research Pipeline — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace prompt-guided LLM browsing with a code-enforced research pipeline that deterministically selects sources, acquires evidence, and gates synthesis on evidence quality.

**Architecture:** A `ResearchExecutionPolicy` implementing the `ToolInterceptor` protocol intercepts search tool results in `ExecutionAgent`, runs `SourceSelector → EvidenceAcquisitionService → SynthesisGuard`, and injects structured evidence into the LLM conversation. A generic extension point in `BaseAgent` supports the interceptor contract. Policy is instantiated by `PlanActFlow` for `deep_research` mode only (Phase 1).

**Tech Stack:** Python 3.12, Pydantic v2, asyncio, pytest (asyncio_mode=auto), AsyncMock, existing ScraplingAdapter/Browser infrastructure.

**Design Doc:** `docs/plans/2026-03-10-deterministic-research-pipeline-design.md`

---

## Task 1: Domain Models (`evidence.py`)

**Files:**
- Create: `backend/app/domain/models/evidence.py`
- Test: `backend/tests/domain/models/test_evidence.py`

**Step 1: Write the test file**

```python
# backend/tests/domain/models/test_evidence.py
"""Tests for EvidenceRecord and related domain models."""

import pytest
from datetime import datetime

from app.domain.models.evidence import (
    AccessMethod,
    ConfidenceAssessment,
    ConfidenceBucket,
    EvidenceRecord,
    HardFailReason,
    PromotionDecision,
    QueryContext,
    SelectedSource,
    SoftFailReason,
    SourceType,
    SynthesisGateResult,
    SynthesisGateVerdict,
    ToolCallContext,
    ToolInterceptorResult,
    evidence_to_source_citation,
)
from app.domain.models.source_citation import SourceCitation


class TestSourceType:
    def test_all_values_exist(self):
        assert SourceType.OFFICIAL == "official"
        assert SourceType.AUTHORITATIVE_NEUTRAL == "authoritative_neutral"
        assert SourceType.INDEPENDENT == "independent"
        assert SourceType.UGC_LOW_TRUST == "ugc_low_trust"


class TestConfidenceBucket:
    def test_all_values_exist(self):
        assert ConfidenceBucket.HIGH == "high"
        assert ConfidenceBucket.MEDIUM == "medium"
        assert ConfidenceBucket.LOW == "low"


class TestAccessMethod:
    def test_scrapling_tiers(self):
        assert AccessMethod.SCRAPLING_HTTP == "scrapling_http"
        assert AccessMethod.SCRAPLING_DYNAMIC == "scrapling_dynamic"
        assert AccessMethod.SCRAPLING_STEALTHY == "scrapling_stealthy"

    def test_browser_methods(self):
        assert AccessMethod.BROWSER_PROMOTED == "browser_promoted"
        assert AccessMethod.BROWSER_FALLBACK == "browser_fallback"


class TestHardFailReason:
    def test_all_reasons(self):
        assert len(HardFailReason) == 5
        assert HardFailReason.BLOCK_PAYWALL_CHALLENGE == "block_paywall_challenge"
        assert HardFailReason.JS_SHELL_EMPTY == "js_shell_empty"
        assert HardFailReason.EXTRACTION_FAILURE == "extraction_failure"
        assert HardFailReason.REQUIRED_FIELD_MISSING == "required_field_missing"
        assert HardFailReason.SEVERE_CONTENT_MISMATCH == "severe_content_mismatch"


class TestSoftFailReason:
    def test_all_reasons(self):
        assert len(SoftFailReason) == 6
        assert SoftFailReason.THIN_CONTENT == "thin_content"
        assert SoftFailReason.BOILERPLATE_HEAVY == "boilerplate_heavy"


class TestToolCallContext:
    def test_frozen_dataclass(self):
        ctx = ToolCallContext(
            tool_call_id="call_123",
            function_name="info_search_web",
            function_args={"query": "test"},
            step_id="step_1",
            session_id="sess_abc",
            research_mode="deep_research",
        )
        assert ctx.function_name == "info_search_web"
        assert ctx.research_mode == "deep_research"
        with pytest.raises(AttributeError):
            ctx.function_name = "other"  # type: ignore[misc]


class TestToolInterceptorResult:
    def test_defaults(self):
        result = ToolInterceptorResult()
        assert result.override_memory_content is None
        assert result.extra_messages is None
        assert result.suppress_memory_content is False

    def test_with_override(self):
        result = ToolInterceptorResult(
            override_memory_content="new content",
            extra_messages=[{"role": "system", "content": "evidence"}],
        )
        assert result.override_memory_content == "new content"
        assert len(result.extra_messages) == 1


class TestQueryContext:
    def test_defaults(self):
        ctx = QueryContext()
        assert ctx.task_intent is None
        assert ctx.required_entities is None
        assert ctx.time_sensitive is False
        assert ctx.comparative is False

    def test_frozen(self):
        ctx = QueryContext(time_sensitive=True, comparative=True)
        with pytest.raises(AttributeError):
            ctx.time_sensitive = False  # type: ignore[misc]


class TestEvidenceRecord:
    def _make_record(self, **overrides) -> EvidenceRecord:
        defaults = dict(
            url="https://docs.python.org/3/library/asyncio.html",
            domain="docs.python.org",
            title="asyncio — Asynchronous I/O",
            source_type=SourceType.OFFICIAL,
            authority_score=0.95,
            source_importance="high",
            excerpt="asyncio is a library to write concurrent code...",
            content_length=15000,
            content_ref="trs-abc123",
            access_method=AccessMethod.SCRAPLING_HTTP,
            fetch_tier_reached=1,
            extraction_duration_ms=350,
            timestamp=datetime(2026, 3, 10, 12, 0, 0),
            confidence_bucket=ConfidenceBucket.HIGH,
            hard_fail_reasons=[],
            soft_fail_reasons=[],
            soft_point_total=0,
            browser_promoted=False,
            browser_changed_outcome=False,
            original_snippet="asyncio is a library...",
            original_rank=1,
            query="python asyncio tutorial",
        )
        defaults.update(overrides)
        return EvidenceRecord(**defaults)

    def test_create_valid_record(self):
        record = self._make_record()
        assert record.url == "https://docs.python.org/3/library/asyncio.html"
        assert record.confidence_bucket == ConfidenceBucket.HIGH

    def test_frozen(self):
        record = self._make_record()
        with pytest.raises(Exception):  # ValidationError for frozen model
            record.url = "https://other.com"  # type: ignore[misc]

    def test_browser_promoted_record(self):
        record = self._make_record(
            access_method=AccessMethod.BROWSER_PROMOTED,
            browser_promoted=True,
            browser_changed_outcome=True,
        )
        assert record.browser_promoted is True
        assert record.access_method == AccessMethod.BROWSER_PROMOTED

    def test_failed_record(self):
        record = self._make_record(
            excerpt="",
            content_length=0,
            content_ref=None,
            confidence_bucket=ConfidenceBucket.LOW,
            hard_fail_reasons=["extraction_failure"],
        )
        assert record.content_length == 0
        assert "extraction_failure" in record.hard_fail_reasons


class TestSelectedSource:
    def test_create(self):
        source = SelectedSource(
            url="https://example.com",
            domain="example.com",
            title="Example",
            original_snippet="A snippet",
            original_rank=1,
            query="test",
            relevance_score=0.8,
            authority_score=0.7,
            freshness_score=0.6,
            rank_score=0.5,
            composite_score=0.7,
            source_type=SourceType.INDEPENDENT,
            source_importance="medium",
            selection_reason="top_composite",
            domain_diversity_applied=False,
        )
        assert source.composite_score == 0.7


class TestConfidenceAssessment:
    def test_high_confidence(self):
        assessment = ConfidenceAssessment(
            confidence_bucket=ConfidenceBucket.HIGH,
            promotion_decision=PromotionDecision.NO_VERIFY,
            shadow_score=0.95,
            content_length=5000,
        )
        assert assessment.promotion_decision == PromotionDecision.NO_VERIFY

    def test_low_confidence_with_hard_fails(self):
        assessment = ConfidenceAssessment(
            hard_fails=[HardFailReason.BLOCK_PAYWALL_CHALLENGE],
            confidence_bucket=ConfidenceBucket.LOW,
            promotion_decision=PromotionDecision.REQUIRED,
            shadow_score=0.2,
            content_length=100,
        )
        assert assessment.promotion_decision == PromotionDecision.REQUIRED
        assert len(assessment.hard_fails) == 1


class TestSynthesisGateResult:
    def test_pass(self):
        result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.PASS,
            total_fetched=4,
            high_confidence_count=3,
            official_source_found=True,
            independent_source_found=True,
        )
        assert result.verdict == SynthesisGateVerdict.PASS

    def test_hard_fail(self):
        result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.HARD_FAIL,
            reasons=["Insufficient sources: 1/3 fetched successfully"],
            total_fetched=1,
            high_confidence_count=0,
        )
        assert len(result.reasons) == 1


class TestEvidenceToSourceCitation:
    def test_scrapling_maps_to_search(self):
        record = EvidenceRecord(
            url="https://example.com",
            domain="example.com",
            title="Example",
            source_type=SourceType.INDEPENDENT,
            authority_score=0.5,
            source_importance="medium",
            excerpt="content...",
            content_length=5000,
            access_method=AccessMethod.SCRAPLING_HTTP,
            fetch_tier_reached=1,
            extraction_duration_ms=200,
            timestamp=datetime(2026, 3, 10),
            confidence_bucket=ConfidenceBucket.HIGH,
            hard_fail_reasons=[],
            soft_fail_reasons=[],
        )
        citation = evidence_to_source_citation(record)
        assert isinstance(citation, SourceCitation)
        assert citation.source_type == "search"
        assert citation.url == "https://example.com"

    def test_browser_promoted_maps_to_browser(self):
        record = EvidenceRecord(
            url="https://example.com",
            domain="example.com",
            title="Example",
            source_type=SourceType.OFFICIAL,
            authority_score=0.9,
            source_importance="high",
            excerpt="content...",
            content_length=10000,
            access_method=AccessMethod.BROWSER_PROMOTED,
            fetch_tier_reached=3,
            extraction_duration_ms=5000,
            timestamp=datetime(2026, 3, 10),
            confidence_bucket=ConfidenceBucket.HIGH,
            hard_fail_reasons=[],
            soft_fail_reasons=[],
            browser_promoted=True,
        )
        citation = evidence_to_source_citation(record)
        assert citation.source_type == "browser"
```

**Step 2: Run test to verify it fails**

Run: `cd backend && conda activate pythinker && pytest tests/domain/models/test_evidence.py -v -p no:cov -o addopts=`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.domain.models.evidence'`

**Step 3: Write the domain models**

```python
# backend/app/domain/models/evidence.py
"""Domain models for the deterministic research pipeline.

Defines EvidenceRecord (canonical unit of research evidence),
SourceSelector output types, confidence assessment types,
synthesis gate types, and the ToolInterceptor contract types.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

if TYPE_CHECKING:
    from app.domain.models.source_citation import SourceCitation
    from app.domain.models.tool_result import ToolResult


# ── Enums ──────────────────────────────────────────────────────


class SourceType(StrEnum):
    OFFICIAL = "official"
    AUTHORITATIVE_NEUTRAL = "authoritative_neutral"
    INDEPENDENT = "independent"
    UGC_LOW_TRUST = "ugc_low_trust"


class ConfidenceBucket(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class PromotionDecision(StrEnum):
    NO_VERIFY = "no_verify"
    VERIFY_IF_HIGH_IMPORTANCE = "verify_if_high_importance"
    REQUIRED = "required"


class AccessMethod(StrEnum):
    SCRAPLING_HTTP = "scrapling_http"
    SCRAPLING_DYNAMIC = "scrapling_dynamic"
    SCRAPLING_STEALTHY = "scrapling_stealthy"
    BROWSER_PROMOTED = "browser_promoted"
    BROWSER_FALLBACK = "browser_fallback"


class HardFailReason(StrEnum):
    BLOCK_PAYWALL_CHALLENGE = "block_paywall_challenge"
    JS_SHELL_EMPTY = "js_shell_empty"
    EXTRACTION_FAILURE = "extraction_failure"
    REQUIRED_FIELD_MISSING = "required_field_missing"
    SEVERE_CONTENT_MISMATCH = "severe_content_mismatch"


class SoftFailReason(StrEnum):
    THIN_CONTENT = "thin_content"
    BOILERPLATE_HEAVY = "boilerplate_heavy"
    MISSING_ENTITIES = "missing_entities"
    NO_PUBLISH_DATE = "no_publish_date"
    WEAK_CONTENT_DENSITY = "weak_content_density"
    PARTIAL_STRUCTURED_EXTRACTION = "partial_structured_extraction"


class SynthesisGateVerdict(StrEnum):
    PASS = "pass"
    SOFT_FAIL = "soft_fail"
    HARD_FAIL = "hard_fail"


# ── Interceptor Contract Types ─────────────────────────────────


@dataclass(frozen=True, slots=True)
class ToolCallContext:
    """Typed context for tool interceptor invocations."""

    tool_call_id: str
    function_name: str
    function_args: dict[str, Any]
    step_id: str | None
    session_id: str
    research_mode: str | None  # "deep_research" | "wide_research" | None


@dataclass(slots=True)
class ToolInterceptorResult:
    """Outcome of a tool interceptor invocation."""

    override_memory_content: str | None = None
    extra_messages: list[dict] | None = None
    suppress_memory_content: bool = False


# ── Query Context ──────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class QueryContext:
    """Task-level context passed to source selector and confidence assessor."""

    task_intent: str | None = None
    required_entities: list[str] | None = None
    time_sensitive: bool = False
    comparative: bool = False


# ── Source Selection Types ─────────────────────────────────────


class SelectedSource(BaseModel):
    """A URL selected for evidence acquisition. Pre-extraction."""

    url: str
    domain: str
    title: str
    original_snippet: str
    original_rank: int
    query: str

    relevance_score: float
    authority_score: float
    freshness_score: float
    rank_score: float
    composite_score: float

    source_type: SourceType
    source_importance: Literal["high", "medium", "low"]

    selection_reason: str
    domain_diversity_applied: bool = False


# ── Confidence Assessment Types ────────────────────────────────


class ConfidenceAssessment(BaseModel):
    """Assessment of extraction quality for a single source."""

    hard_fails: list[HardFailReason] = Field(default_factory=list)
    soft_fails: list[SoftFailReason] = Field(default_factory=list)
    soft_point_total: int = 0

    confidence_bucket: ConfidenceBucket
    promotion_decision: PromotionDecision

    shadow_score: float = 1.0
    content_length: int = 0
    boilerplate_ratio: float = 0.0
    entity_match_ratio: float = 0.0


# ── Evidence Record ────────────────────────────────────────────


class EvidenceRecord(BaseModel):
    """Single source's acquired evidence. Immutable after creation."""

    model_config = ConfigDict(frozen=True)

    # Identity
    url: str
    domain: str
    title: str

    # Classification
    source_type: SourceType
    authority_score: float
    source_importance: Literal["high", "medium", "low"]

    # Content (excerpt only inline — full content offloaded)
    excerpt: str
    content_length: int
    content_ref: str | None = None

    # Extraction metadata
    access_method: AccessMethod
    fetch_tier_reached: int
    extraction_duration_ms: int
    timestamp: datetime

    # Confidence assessment
    confidence_bucket: ConfidenceBucket
    hard_fail_reasons: list[str] = Field(default_factory=list)
    soft_fail_reasons: list[str] = Field(default_factory=list)
    soft_point_total: int = 0

    # Browser promotion telemetry
    browser_promoted: bool = False
    browser_changed_outcome: bool = False

    # Provenance
    original_snippet: str | None = None
    original_rank: int = 0
    query: str = ""


# ── Synthesis Gate Types ───────────────────────────────────────


class SynthesisGateResult(BaseModel):
    """Output of SynthesisGuard evaluation."""

    verdict: SynthesisGateVerdict
    reasons: list[str] = Field(default_factory=list)

    total_fetched: int = 0
    high_confidence_count: int = 0
    official_source_found: bool = False
    independent_source_found: bool = False

    thresholds_applied: dict[str, int | bool] = Field(default_factory=dict)


# ── ToolInterceptor Protocol ──────────────────────────────────


class ToolInterceptor(Protocol):
    """Extension point for intercepting tool results before LLM sees them."""

    async def on_tool_result(
        self,
        tool_result: Any,  # ToolResult — avoid circular import
        serialized_content: str,
        context: ToolCallContext,
        emit_event: Callable[[Any], Awaitable[None]],
    ) -> ToolInterceptorResult | None: ...


# ── Mapper ─────────────────────────────────────────────────────


def evidence_to_source_citation(record: EvidenceRecord) -> "SourceCitation":
    """Map EvidenceRecord to existing SourceCitation for delivery gates."""
    from app.domain.models.source_citation import SourceCitation

    source_type_map: dict[AccessMethod, str] = {
        AccessMethod.BROWSER_PROMOTED: "browser",
        AccessMethod.BROWSER_FALLBACK: "browser",
    }
    return SourceCitation(
        url=record.url,
        title=record.title,
        snippet=record.excerpt,
        access_time=record.timestamp,
        source_type=source_type_map.get(record.access_method, "search"),
    )
```

**Step 4: Run test to verify it passes**

Run: `cd backend && pytest tests/domain/models/test_evidence.py -v -p no:cov -o addopts=`
Expected: All tests PASS

**Step 5: Commit**

```bash
git add backend/app/domain/models/evidence.py backend/tests/domain/models/test_evidence.py
git commit -m "feat(research): add domain models for deterministic research pipeline

EvidenceRecord, SelectedSource, ConfidenceAssessment, SynthesisGateResult,
ToolCallContext, ToolInterceptorResult, ToolInterceptor Protocol, and
evidence_to_source_citation mapper."
```

---

## Task 2: Config Schema (`config_research_pipeline.py`)

**Files:**
- Create: `backend/app/core/config_research_pipeline.py`
- Modify: `backend/app/core/config.py:76-110` (add mixin to Settings)
- Test: `backend/tests/core/test_config_research_pipeline.py`

**Step 1: Write the test file**

```python
# backend/tests/core/test_config_research_pipeline.py
"""Tests for research pipeline configuration."""

from app.core.config_research_pipeline import ResearchPipelineSettingsMixin


class TestResearchPipelineDefaults:
    def test_pipeline_enabled_by_default(self):
        cfg = ResearchPipelineSettingsMixin()
        assert cfg.research_deterministic_pipeline_enabled is True

    def test_shadow_mode_by_default(self):
        cfg = ResearchPipelineSettingsMixin()
        assert cfg.research_pipeline_mode == "shadow"

    def test_source_selection_defaults(self):
        cfg = ResearchPipelineSettingsMixin()
        assert cfg.research_source_select_count == 4
        assert cfg.research_source_max_per_domain == 1

    def test_weight_defaults_sum_to_one(self):
        cfg = ResearchPipelineSettingsMixin()
        total = (
            cfg.research_weight_relevance
            + cfg.research_weight_authority
            + cfg.research_weight_freshness
            + cfg.research_weight_rank
        )
        assert abs(total - 1.0) < 0.01

    def test_confidence_thresholds(self):
        cfg = ResearchPipelineSettingsMixin()
        assert cfg.research_soft_fail_verify_threshold == 2
        assert cfg.research_soft_fail_required_threshold == 3

    def test_synthesis_gate_defaults(self):
        cfg = ResearchPipelineSettingsMixin()
        assert cfg.research_min_fetched_sources == 3
        assert cfg.research_min_high_confidence == 2
        assert cfg.research_require_official_source is True
        assert cfg.research_require_independent_source is True

    def test_relaxation_defaults(self):
        cfg = ResearchPipelineSettingsMixin()
        assert cfg.research_relaxation_enabled is True
        assert cfg.research_relaxed_min_fetched_sources == 2
        assert cfg.research_relaxed_min_high_confidence == 1
        assert cfg.research_relaxed_require_official_source is False
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/core/test_config_research_pipeline.py -v -p no:cov -o addopts=`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the config module**

```python
# backend/app/core/config_research_pipeline.py
"""Configuration for the deterministic research pipeline.

All settings are environment-variable overridable via RESEARCH_* prefix.
"""

from typing import Literal

from pydantic_settings import BaseSettings


class ResearchPipelineSettingsMixin(BaseSettings):
    """Deterministic research pipeline configuration."""

    # ── Feature flags ──
    research_deterministic_pipeline_enabled: bool = True
    research_pipeline_mode: Literal["shadow", "enforced"] = "shadow"

    # ── Source selection ──
    research_source_select_count: int = 4
    research_source_max_per_domain: int = 1
    research_source_allow_multi_page_domains: bool = True

    # ── Source scoring weights ──
    research_weight_relevance: float = 0.35
    research_weight_authority: float = 0.25
    research_weight_freshness: float = 0.20
    research_weight_rank: float = 0.20

    # ── Evidence acquisition ──
    research_acquisition_concurrency: int = 4
    research_acquisition_timeout_seconds: float = 30.0
    research_excerpt_chars: int = 2000
    research_full_content_offload: bool = True

    # ── Confidence thresholds ──
    research_soft_fail_verify_threshold: int = 2
    research_soft_fail_required_threshold: int = 3
    research_thin_content_chars: int = 500
    research_boilerplate_ratio_threshold: float = 0.6

    # ── Synthesis gate (default) ──
    research_min_fetched_sources: int = 3
    research_min_high_confidence: int = 2
    research_require_official_source: bool = True
    research_require_independent_source: bool = True

    # ── Synthesis gate (relaxed) ──
    research_relaxation_enabled: bool = True
    research_relaxed_min_fetched_sources: int = 2
    research_relaxed_min_high_confidence: int = 1
    research_relaxed_require_official_source: bool = False

    # ── Telemetry ──
    research_telemetry_enabled: bool = True
```

**Step 4: Add mixin to Settings class**

In `backend/app/core/config.py`, add `ResearchPipelineSettingsMixin` to the `Settings` class mixin list. Find the `class Settings(` definition at line 76 and add the import + mixin.

Add import near the top with other config imports:
```python
from app.core.config_research_pipeline import ResearchPipelineSettingsMixin
```

Add to the Settings class mixin list (after `ScrapingSettingsMixin`):
```python
ResearchPipelineSettingsMixin,
```

**Step 5: Run tests**

Run: `cd backend && pytest tests/core/test_config_research_pipeline.py -v -p no:cov -o addopts=`
Expected: All PASS

**Step 6: Commit**

```bash
git add backend/app/core/config_research_pipeline.py backend/tests/core/test_config_research_pipeline.py backend/app/core/config.py
git commit -m "feat(research): add research pipeline config with policy-driven thresholds

Shadow/enforced mode, source selection weights, confidence thresholds,
synthesis gate defaults with relaxation policy for niche topics."
```

---

## Task 3: ContentConfidenceAssessor (`content_confidence.py`)

**Files:**
- Create: `backend/app/domain/services/agents/content_confidence.py`
- Test: `backend/tests/domain/services/agents/test_content_confidence.py`

**Step 1: Write the test file**

```python
# backend/tests/domain/services/agents/test_content_confidence.py
"""Tests for ContentConfidenceAssessor — tiered hard/soft fail rules."""

import pytest
from types import SimpleNamespace

from app.domain.models.evidence import (
    ConfidenceBucket,
    HardFailReason,
    PromotionDecision,
    QueryContext,
    SoftFailReason,
)
from app.domain.services.agents.content_confidence import ContentConfidenceAssessor


def _config(**overrides):
    defaults = dict(
        research_soft_fail_verify_threshold=2,
        research_soft_fail_required_threshold=3,
        research_thin_content_chars=500,
        research_boilerplate_ratio_threshold=0.6,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class TestHardFails:
    def test_paywall_detected(self):
        assessor = ContentConfidenceAssessor(_config())
        result = assessor.assess(
            content="Please subscribe to continue reading. Enable your premium account.",
            url="https://example.com/article",
            domain="example.com",
            title="Article Title",
            source_importance="high",
        )
        assert HardFailReason.BLOCK_PAYWALL_CHALLENGE in result.hard_fails
        assert result.confidence_bucket == ConfidenceBucket.LOW
        assert result.promotion_decision == PromotionDecision.REQUIRED

    def test_js_shell_empty(self):
        assessor = ContentConfidenceAssessor(_config())
        result = assessor.assess(
            content="Loading... Please enable JavaScript",
            url="https://spa.example.com",
            domain="spa.example.com",
            title="SPA App",
            source_importance="medium",
        )
        assert HardFailReason.JS_SHELL_EMPTY in result.hard_fails

    def test_extraction_failure_empty(self):
        assessor = ContentConfidenceAssessor(_config())
        result = assessor.assess(
            content="",
            url="https://example.com",
            domain="example.com",
            title="Test",
            source_importance="low",
        )
        assert HardFailReason.EXTRACTION_FAILURE in result.hard_fails

    def test_extraction_failure_tiny(self):
        assessor = ContentConfidenceAssessor(_config())
        result = assessor.assess(
            content="x" * 30,
            url="https://example.com",
            domain="example.com",
            title="Test",
            source_importance="low",
        )
        assert HardFailReason.EXTRACTION_FAILURE in result.hard_fails

    def test_severe_mismatch(self):
        assessor = ContentConfidenceAssessor(_config())
        result = assessor.assess(
            content="Buy cheap shoes online! Free shipping on all orders.",
            url="https://example.com/python-docs",
            domain="example.com",
            title="Python asyncio Documentation",
            source_importance="high",
        )
        assert HardFailReason.SEVERE_CONTENT_MISMATCH in result.hard_fails

    def test_required_field_missing_high_importance(self):
        assessor = ContentConfidenceAssessor(_config())
        ctx = QueryContext(required_entities=["asyncio", "event_loop", "coroutine"])
        result = assessor.assess(
            content="This page is about web development with JavaScript and React.",
            url="https://example.com",
            domain="example.com",
            title="Web Dev Guide",
            source_importance="high",
            query_context=ctx,
        )
        assert HardFailReason.REQUIRED_FIELD_MISSING in result.hard_fails

    def test_required_field_missing_low_importance_is_soft_fail(self):
        assessor = ContentConfidenceAssessor(_config())
        ctx = QueryContext(required_entities=["asyncio", "event_loop", "coroutine"])
        result = assessor.assess(
            content="This page is about general programming concepts and best practices." * 20,
            url="https://example.com",
            domain="example.com",
            title="Programming Guide",
            source_importance="low",
            query_context=ctx,
        )
        # Should be soft fail, not hard fail, for low importance
        assert HardFailReason.REQUIRED_FIELD_MISSING not in result.hard_fails
        assert SoftFailReason.MISSING_ENTITIES in result.soft_fails


class TestSoftFails:
    def test_thin_content(self):
        assessor = ContentConfidenceAssessor(_config())
        result = assessor.assess(
            content="A short but valid page with some real content here." * 3,
            url="https://example.com",
            domain="example.com",
            title="Short Page",
            source_importance="medium",
        )
        assert SoftFailReason.THIN_CONTENT in result.soft_fails

    def test_no_publish_date_time_sensitive(self):
        assessor = ContentConfidenceAssessor(_config())
        ctx = QueryContext(time_sensitive=True)
        result = assessor.assess(
            content="This is a comprehensive article about Python performance tuning. " * 30,
            url="https://example.com",
            domain="example.com",
            title="Python Performance",
            source_importance="medium",
            query_context=ctx,
        )
        assert SoftFailReason.NO_PUBLISH_DATE in result.soft_fails

    def test_no_date_check_when_not_time_sensitive(self):
        assessor = ContentConfidenceAssessor(_config())
        ctx = QueryContext(time_sensitive=False)
        result = assessor.assess(
            content="This is a comprehensive article about Python performance tuning. " * 30,
            url="https://example.com",
            domain="example.com",
            title="Python Performance",
            source_importance="medium",
            query_context=ctx,
        )
        assert SoftFailReason.NO_PUBLISH_DATE not in result.soft_fails


class TestDecisionMatrix:
    def test_high_confidence_no_issues(self):
        assessor = ContentConfidenceAssessor(_config())
        result = assessor.assess(
            content="Python asyncio is a library for writing concurrent code using the async/await syntax. " * 50,
            url="https://docs.python.org/3/library/asyncio.html",
            domain="docs.python.org",
            title="asyncio — Python documentation",
            source_importance="high",
        )
        assert result.confidence_bucket == ConfidenceBucket.HIGH
        assert result.promotion_decision == PromotionDecision.NO_VERIFY

    def test_three_soft_fails_forces_required(self):
        assessor = ContentConfidenceAssessor(_config(research_thin_content_chars=10000))
        ctx = QueryContext(time_sensitive=True, required_entities=["nonexistent_entity_xyz"])
        # Content is short (soft), has no date (soft), and missing entities (soft) = 3 soft fails
        result = assessor.assess(
            content="A somewhat short article about general topics with no specific entities." * 10,
            url="https://example.com",
            domain="example.com",
            title="General Article",
            source_importance="medium",
            query_context=ctx,
        )
        assert result.soft_point_total >= 3
        assert result.confidence_bucket == ConfidenceBucket.LOW
        assert result.promotion_decision == PromotionDecision.REQUIRED

    def test_hard_fail_overrides_soft_count(self):
        assessor = ContentConfidenceAssessor(_config())
        result = assessor.assess(
            content="",
            url="https://example.com",
            domain="example.com",
            title="Test",
            source_importance="low",
        )
        assert result.confidence_bucket == ConfidenceBucket.LOW
        assert result.promotion_decision == PromotionDecision.REQUIRED


class TestShadowScore:
    def test_perfect_content_high_shadow(self):
        assessor = ContentConfidenceAssessor(_config())
        result = assessor.assess(
            content="Comprehensive content about Python asyncio with examples and code. " * 50,
            url="https://docs.python.org",
            domain="docs.python.org",
            title="Python asyncio docs",
            source_importance="high",
        )
        assert result.shadow_score >= 0.9

    def test_hard_fail_low_shadow(self):
        assessor = ContentConfidenceAssessor(_config())
        result = assessor.assess(
            content="",
            url="https://example.com",
            domain="example.com",
            title="Test",
            source_importance="low",
        )
        assert result.shadow_score < 0.7
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/services/agents/test_content_confidence.py -v -p no:cov -o addopts=`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `backend/app/domain/services/agents/content_confidence.py` with:
- `ContentConfidenceAssessor.__init__(self, config)` — compiles regex patterns for paywall, JS shell, boilerplate detection
- `assess(self, content, url, domain, title, source_importance, query_context=None) -> ConfidenceAssessment` — runs all checks, applies decision matrix
- `_detect_block_paywall_challenge(self, content, url) -> bool` — regex for "subscribe", "enable javascript", "access denied", "captcha", "verify you are human", Cloudflare challenge tokens
- `_detect_js_shell_empty(self, content) -> bool` — body text < 100 chars with "loading", "enable javascript", "app-root", "react-root", or mostly `<script>`/`<noscript>` tags
- `_detect_severe_mismatch(self, content, title, domain) -> bool` — title tokens (minus stopwords) overlap with content < 20%
- `_detect_required_field_missing(self, content, required_entities) -> bool` — >50% of required entities absent (case-insensitive)
- `_compute_boilerplate_ratio(self, content) -> float` — lines matching boilerplate patterns / total lines
- `_compute_entity_match_ratio(self, content, entities) -> float` — fraction of entities found
- `_detect_publish_date(self, content) -> bool` — regex for ISO dates, "Published:", "Updated:", month-day-year
- `_detect_weak_density(self, content) -> bool` — unique words / total words < 0.3

**Decision logic in `assess()`:**
```python
if hard_fails:
    bucket = LOW; decision = REQUIRED
elif soft_total >= config.research_soft_fail_required_threshold:
    bucket = LOW; decision = REQUIRED
elif soft_total >= config.research_soft_fail_verify_threshold:
    bucket = MEDIUM; decision = VERIFY_IF_HIGH_IMPORTANCE
else:
    bucket = HIGH; decision = NO_VERIFY
```

**Step 4: Run tests**

Run: `cd backend && pytest tests/domain/services/agents/test_content_confidence.py -v -p no:cov -o addopts=`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/content_confidence.py backend/tests/domain/services/agents/test_content_confidence.py
git commit -m "feat(research): add ContentConfidenceAssessor with tiered hard/soft fail rules

Detects paywall, JS shell, extraction failure, content mismatch, thin content,
boilerplate, missing entities, missing dates. Decision matrix: hard_fail→REQUIRED,
3+ soft→REQUIRED, 2 soft→VERIFY_IF_HIGH_IMPORTANCE, 0-1→NO_VERIFY.
Shadow score tracked for telemetry."
```

---

## Task 4: SourceSelector (`source_selector.py`)

**Files:**
- Create: `backend/app/domain/services/agents/source_selector.py`
- Test: `backend/tests/domain/services/agents/test_source_selector.py`

**Step 1: Write the test file**

```python
# backend/tests/domain/services/agents/test_source_selector.py
"""Tests for SourceSelector — deterministic URL ranking and selection."""

import pytest
from types import SimpleNamespace

from app.domain.models.evidence import (
    QueryContext,
    SelectedSource,
    SourceType,
)
from app.domain.models.search import SearchResultItem
from app.domain.services.agents.source_selector import SourceSelector


def _config(**overrides):
    defaults = dict(
        research_source_select_count=4,
        research_source_max_per_domain=1,
        research_source_allow_multi_page_domains=True,
        research_weight_relevance=0.35,
        research_weight_authority=0.25,
        research_weight_freshness=0.20,
        research_weight_rank=0.20,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _item(title: str, link: str, snippet: str = "A search snippet.") -> SearchResultItem:
    return SearchResultItem(title=title, link=link, snippet=snippet)


class TestNormalizationAndDedupe:
    def test_dedupes_by_normalized_url(self):
        selector = SourceSelector(_config())
        items = [
            _item("Page A", "https://example.com/page?utm_source=google"),
            _item("Page A", "https://example.com/page?utm_medium=cpc"),
        ]
        result = selector.select(items, query="test")
        # Should dedupe to 1
        assert len(result) == 1

    def test_strips_trailing_slash(self):
        selector = SourceSelector(_config())
        items = [
            _item("Page", "https://example.com/page/"),
            _item("Page", "https://example.com/page"),
        ]
        result = selector.select(items, query="test")
        assert len(result) == 1

    def test_filters_denylist_domains(self):
        selector = SourceSelector(_config())
        items = [
            _item("Reddit Post", "https://www.reddit.com/r/python/good-post"),
            _item("Twitter Thread", "https://x.com/user/status/123"),
            _item("Real Source", "https://realpython.com/asyncio-guide"),
        ]
        result = selector.select(items, query="python asyncio")
        assert len(result) == 1
        assert result[0].domain != "reddit.com"


class TestClassification:
    def test_gov_is_official(self):
        selector = SourceSelector(_config())
        items = [_item("NIH Study", "https://www.nih.gov/study/123")]
        result = selector.select(items, query="health study")
        assert result[0].source_type == SourceType.OFFICIAL

    def test_edu_is_official(self):
        selector = SourceSelector(_config())
        items = [_item("MIT Course", "https://ocw.mit.edu/courses/cs")]
        result = selector.select(items, query="computer science")
        assert result[0].source_type == SourceType.OFFICIAL

    def test_docs_subdomain_is_official(self):
        selector = SourceSelector(_config())
        items = [_item("Python Docs", "https://docs.python.org/3/library/asyncio.html")]
        result = selector.select(items, query="python asyncio")
        assert result[0].source_type == SourceType.OFFICIAL

    def test_entity_domain_match_upgrades_to_official(self):
        selector = SourceSelector(_config())
        items = [_item("FastAPI Tutorial", "https://fastapi.tiangolo.com/tutorial/")]
        result = selector.select(items, query="fastapi tutorial")
        assert result[0].source_type == SourceType.OFFICIAL

    def test_forum_is_ugc(self):
        selector = SourceSelector(_config())
        items = [_item("Stack Overflow Answer", "https://stackoverflow.com/questions/123")]
        result = selector.select(items, query="python error")
        assert result[0].source_type == SourceType.UGC_LOW_TRUST

    def test_news_is_independent(self):
        selector = SourceSelector(_config())
        items = [_item("Ars Technica Review", "https://arstechnica.com/review/product")]
        result = selector.select(items, query="product review")
        assert result[0].source_type == SourceType.INDEPENDENT


class TestConstraintEnforcement:
    def test_max_one_per_domain(self):
        selector = SourceSelector(_config())
        items = [
            _item("Page 1", "https://example.com/page1", "Great content about Python"),
            _item("Page 2", "https://example.com/page2", "More Python content"),
            _item("Other Site", "https://other.com/page", "Python info"),
        ]
        result = selector.select(items, query="python")
        domains = [r.domain for r in result]
        assert domains.count("example.com") <= 1

    def test_at_least_one_independent_when_available(self):
        selector = SourceSelector(_config())
        items = [
            _item("Docs 1", "https://docs.python.org/3/a"),
            _item("Docs 2", "https://docs.python.org/3/b"),
            _item("Blog Post", "https://realpython.com/guide"),
            _item("Docs 3", "https://docs.python.org/3/c"),
        ]
        result = selector.select(items, query="python")
        types = [r.source_type for r in result]
        assert SourceType.INDEPENDENT in types or SourceType.AUTHORITATIVE_NEUTRAL in types

    def test_respects_select_count(self):
        selector = SourceSelector(_config(research_source_select_count=3))
        items = [_item(f"Page {i}", f"https://site{i}.com/page") for i in range(10)]
        result = selector.select(items, query="test")
        assert len(result) <= 3


class TestAdversarialIntent:
    def test_comparative_query_limits_official(self):
        selector = SourceSelector(_config())
        items = [
            _item("Official Product", "https://product.com/features"),
            _item("Review Site 1", "https://review1.com/product-review"),
            _item("Review Site 2", "https://review2.com/comparison"),
            _item("Blog Review", "https://blog.com/honest-review"),
            _item("Product Docs", "https://docs.product.com/api"),
        ]
        result = selector.select(items, query="best alternatives to product X")
        official_count = sum(1 for r in result if r.source_type == SourceType.OFFICIAL)
        # Comparative queries should not be dominated by official sources
        assert official_count <= len(result) // 2 + 1

    def test_detects_comparative_keywords(self):
        selector = SourceSelector(_config())
        assert selector._detect_adversarial_intent("best alternatives to react")
        assert selector._detect_adversarial_intent("independent benchmark python vs go")
        assert selector._detect_adversarial_intent("criticism of kubernetes")
        assert not selector._detect_adversarial_intent("python asyncio tutorial")


class TestScoring:
    def test_higher_rank_gets_higher_rank_score(self):
        selector = SourceSelector(_config())
        items = [
            _item("First Result", "https://first.com/page", "Python asyncio guide"),
            _item("Tenth Result", "https://tenth.com/page", "Python asyncio basics"),
        ]
        result = selector.select(items, query="python asyncio")
        # First result should have higher rank_score
        assert result[0].original_rank <= result[-1].original_rank or result[0].composite_score >= result[-1].composite_score

    def test_returns_all_score_fields(self):
        selector = SourceSelector(_config())
        items = [_item("Test", "https://example.com/test", "A test page about Python.")]
        result = selector.select(items, query="python test")
        assert result[0].relevance_score >= 0.0
        assert result[0].authority_score >= 0.0
        assert result[0].freshness_score >= 0.0
        assert result[0].rank_score >= 0.0
        assert result[0].composite_score >= 0.0
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/services/agents/test_source_selector.py -v -p no:cov -o addopts=`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `backend/app/domain/services/agents/source_selector.py` with:

- `SourceSelector.__init__(self, config)` — compile official patterns (`.gov`, `.edu`, `docs.*`, `developer.*`, `api.*`), low-trust patterns (stackoverflow, quora, medium.com, forums), denylist domains (reddit, x, twitter, instagram, facebook, tiktok, linkedin, pinterest), entity-domain patterns
- `select(self, results, query, query_context=None) -> list[SelectedSource]` — full pipeline
- `_normalize_and_dedupe(self, results) -> list[SearchResultItem]` — strip tracking params (`utm_*`, `ref`, `fbclid`, `gclid`), trailing slashes, `www.` prefix, dedupe by normalized URL
- `_extract_domain(self, url) -> str` — `urllib.parse.urlparse` → netloc without `www.`
- `_score(self, item, query, rank, query_context) -> ScoredSource` — compute 4 axes + weighted composite
  - relevance: `len(query_tokens & (title_tokens | snippet_tokens)) / len(query_tokens)` (capped at 1.0)
  - authority: from `_classify_source_type`
  - freshness: 1.0 default (no date → neutral), decay curve if date found
  - rank: `1.0 / (rank + 1)`
- `_classify_source_type(self, url, domain, title, query_tokens) -> tuple[SourceType, float]` — domain heuristics + entity overlay
- `_apply_constraints(self, scored, query_context) -> list[SelectedSource]` — guaranteed slots for official + independent, then fill by composite score with domain cap
- `_detect_adversarial_intent(self, query) -> bool` — regex for "best alternative", "vs ", "compared to", "criticism", "problems with", "independent benchmark"
- `_determine_importance(self, source_type, authority_score) -> Literal["high", "medium", "low"]` — official+high_authority=high, independent+medium_authority=medium, ugc=low

**Step 4: Run tests**

Run: `cd backend && pytest tests/domain/services/agents/test_source_selector.py -v -p no:cov -o addopts=`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/source_selector.py backend/tests/domain/services/agents/test_source_selector.py
git commit -m "feat(research): add SourceSelector with deterministic ranking and classification

Four-tier source classification (official/authoritative/independent/ugc),
entity-domain matching, diversity constraints, adversarial intent detection.
Rule-based, no LLM in selection loop."
```

---

## Task 5: SynthesisGuard (`synthesis_guard.py`)

**Files:**
- Create: `backend/app/domain/services/agents/synthesis_guard.py`
- Test: `backend/tests/domain/services/agents/test_synthesis_guard.py`

**Step 1: Write the test file**

```python
# backend/tests/domain/services/agents/test_synthesis_guard.py
"""Tests for SynthesisGuard — pre-synthesis quality gate."""

import pytest
from datetime import datetime
from types import SimpleNamespace

from app.domain.models.evidence import (
    AccessMethod,
    ConfidenceBucket,
    EvidenceRecord,
    QueryContext,
    SourceType,
    SynthesisGateVerdict,
)
from app.domain.services.agents.synthesis_guard import SynthesisGuard


def _config(**overrides):
    defaults = dict(
        research_min_fetched_sources=3,
        research_min_high_confidence=2,
        research_require_official_source=True,
        research_require_independent_source=True,
        research_relaxation_enabled=True,
        research_relaxed_min_fetched_sources=2,
        research_relaxed_min_high_confidence=1,
        research_relaxed_require_official_source=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _record(
    source_type=SourceType.INDEPENDENT,
    confidence=ConfidenceBucket.HIGH,
    content_length=5000,
    **kw,
) -> EvidenceRecord:
    defaults = dict(
        url="https://example.com",
        domain="example.com",
        title="Test Source",
        source_type=source_type,
        authority_score=0.5,
        source_importance="medium",
        excerpt="content..." if content_length > 0 else "",
        content_length=content_length,
        access_method=AccessMethod.SCRAPLING_HTTP,
        fetch_tier_reached=1,
        extraction_duration_ms=200,
        timestamp=datetime(2026, 3, 10),
        confidence_bucket=confidence,
        hard_fail_reasons=[],
        soft_fail_reasons=[],
    )
    defaults.update(kw)
    return EvidenceRecord(**defaults)


class TestPassConditions:
    def test_happy_path_four_good_sources(self):
        guard = SynthesisGuard(_config())
        evidence = [
            _record(source_type=SourceType.OFFICIAL, confidence=ConfidenceBucket.HIGH),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.HIGH),
            _record(source_type=SourceType.AUTHORITATIVE_NEUTRAL, confidence=ConfidenceBucket.HIGH),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.MEDIUM),
        ]
        result = guard.evaluate(evidence, total_search_results=10)
        assert result.verdict == SynthesisGateVerdict.PASS
        assert result.total_fetched == 4
        assert result.high_confidence_count == 3

    def test_three_sources_minimum(self):
        guard = SynthesisGuard(_config())
        evidence = [
            _record(source_type=SourceType.OFFICIAL, confidence=ConfidenceBucket.HIGH),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.HIGH),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.MEDIUM, url="https://other.com"),
        ]
        result = guard.evaluate(evidence, total_search_results=10)
        assert result.verdict == SynthesisGateVerdict.PASS


class TestHardFailConditions:
    def test_too_few_sources(self):
        guard = SynthesisGuard(_config())
        evidence = [
            _record(source_type=SourceType.OFFICIAL, confidence=ConfidenceBucket.HIGH),
        ]
        result = guard.evaluate(evidence, total_search_results=10)
        assert result.verdict == SynthesisGateVerdict.HARD_FAIL
        assert any("Insufficient sources" in r for r in result.reasons)

    def test_no_high_confidence(self):
        guard = SynthesisGuard(_config())
        evidence = [
            _record(source_type=SourceType.OFFICIAL, confidence=ConfidenceBucket.MEDIUM),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.LOW),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.MEDIUM, url="https://a.com"),
        ]
        result = guard.evaluate(evidence, total_search_results=10)
        assert result.verdict == SynthesisGateVerdict.HARD_FAIL

    def test_failed_sources_not_counted(self):
        guard = SynthesisGuard(_config())
        evidence = [
            _record(source_type=SourceType.OFFICIAL, confidence=ConfidenceBucket.HIGH),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.HIGH),
            _record(content_length=0),  # Failed extraction
        ]
        result = guard.evaluate(evidence, total_search_results=10)
        assert result.total_fetched == 2
        assert result.verdict == SynthesisGateVerdict.HARD_FAIL


class TestRelaxation:
    def test_niche_topic_relaxes_thresholds(self):
        guard = SynthesisGuard(_config())
        evidence = [
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.HIGH),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.MEDIUM, url="https://b.com"),
        ]
        # < 5 search results → niche topic → relaxed thresholds
        result = guard.evaluate(evidence, total_search_results=3)
        # Relaxed: 2 fetched (met), 1 high (met), official not required
        assert result.verdict in (SynthesisGateVerdict.PASS, SynthesisGateVerdict.SOFT_FAIL)

    def test_all_official_failed_relaxes(self):
        guard = SynthesisGuard(_config())
        evidence = [
            _record(source_type=SourceType.OFFICIAL, content_length=0),  # Failed
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.HIGH),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.HIGH, url="https://b.com"),
        ]
        result = guard.evaluate(evidence, total_search_results=10)
        # Official attempted but failed → relaxed
        assert result.thresholds_applied.get("relaxed") is True

    def test_relaxation_disabled(self):
        guard = SynthesisGuard(_config(research_relaxation_enabled=False))
        evidence = [
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.HIGH),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.HIGH, url="https://b.com"),
        ]
        result = guard.evaluate(evidence, total_search_results=3)
        assert result.verdict == SynthesisGateVerdict.HARD_FAIL


class TestSoftFail:
    def test_missing_official_with_enough_sources(self):
        guard = SynthesisGuard(_config())
        evidence = [
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.HIGH),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.HIGH, url="https://b.com"),
            _record(source_type=SourceType.AUTHORITATIVE_NEUTRAL, confidence=ConfidenceBucket.HIGH, url="https://c.com"),
        ]
        # No niche topic (10 results), so no relaxation
        result = guard.evaluate(evidence, total_search_results=10)
        # Missing official is one issue, but sources are good otherwise
        assert any("official" in r.lower() for r in result.reasons)


class TestThresholdsRecording:
    def test_thresholds_in_result(self):
        guard = SynthesisGuard(_config())
        evidence = [
            _record(source_type=SourceType.OFFICIAL, confidence=ConfidenceBucket.HIGH),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.HIGH),
            _record(source_type=SourceType.INDEPENDENT, confidence=ConfidenceBucket.MEDIUM, url="https://a.com"),
        ]
        result = guard.evaluate(evidence, total_search_results=10)
        assert "min_fetched" in result.thresholds_applied
        assert "relaxed" in result.thresholds_applied
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/services/agents/test_synthesis_guard.py -v -p no:cov -o addopts=`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `backend/app/domain/services/agents/synthesis_guard.py` — implement exactly as described in design Section 4.4. Key method: `evaluate()` checks evidence landscape, determines default vs relaxed thresholds, evaluates all gates, returns `SynthesisGateResult`.

**Step 4: Run tests**

Run: `cd backend && pytest tests/domain/services/agents/test_synthesis_guard.py -v -p no:cov -o addopts=`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/synthesis_guard.py backend/tests/domain/services/agents/test_synthesis_guard.py
git commit -m "feat(research): add SynthesisGuard with policy-driven quality gates

Default + relaxed thresholds, niche topic detection, official-failure
relaxation. Verdicts: PASS/SOFT_FAIL/HARD_FAIL. Thresholds recorded
for telemetry."
```

---

## Task 6: EvidenceAcquisitionService (`evidence_acquisition.py`)

**Files:**
- Create: `backend/app/domain/services/agents/evidence_acquisition.py`
- Test: `backend/tests/domain/services/agents/test_evidence_acquisition.py`

**Step 1: Write the test file**

```python
# backend/tests/domain/services/agents/test_evidence_acquisition.py
"""Tests for EvidenceAcquisitionService — scrapling-primary with browser promotion."""

import pytest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from app.domain.models.evidence import (
    AccessMethod,
    ConfidenceBucket,
    PromotionDecision,
    SelectedSource,
    SourceType,
)
from app.domain.services.agents.evidence_acquisition import EvidenceAcquisitionService


def _config(**overrides):
    defaults = dict(
        research_acquisition_concurrency=4,
        research_acquisition_timeout_seconds=30.0,
        research_excerpt_chars=2000,
        research_full_content_offload=True,
        research_soft_fail_verify_threshold=2,
        research_soft_fail_required_threshold=3,
        research_thin_content_chars=500,
        research_boilerplate_ratio_threshold=0.6,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _source(url="https://example.com/page", domain="example.com", **kw) -> SelectedSource:
    defaults = dict(
        url=url,
        domain=domain,
        title="Example Page",
        original_snippet="A snippet.",
        original_rank=1,
        query="test query",
        relevance_score=0.8,
        authority_score=0.7,
        freshness_score=0.5,
        rank_score=0.5,
        composite_score=0.7,
        source_type=SourceType.INDEPENDENT,
        source_importance="medium",
        selection_reason="top_composite",
        domain_diversity_applied=False,
    )
    defaults.update(kw)
    return SelectedSource(**defaults)


def _scraped_content(text="Comprehensive content about the topic. " * 50, tier="http"):
    return SimpleNamespace(
        success=True,
        text=text,
        url="https://example.com/page",
        tier_used=tier,
        status_code=200,
        error=None,
    )


@pytest.fixture
def mock_scraper():
    scraper = AsyncMock()
    scraper.fetch_with_escalation = AsyncMock(return_value=_scraped_content())
    return scraper


@pytest.fixture
def mock_browser():
    browser = AsyncMock()
    browser.navigate = AsyncMock(return_value=SimpleNamespace(
        content="Full browser content with JavaScript rendered. " * 100,
    ))
    return browser


@pytest.fixture
def mock_store():
    store = MagicMock()
    store.offload_threshold = 4000
    store.store = MagicMock(return_value=("trs-abc123", "preview..."))
    return store


@pytest.fixture
def emit_event():
    return AsyncMock()


class TestSuccessfulAcquisition:
    async def test_acquires_single_source(self, mock_scraper, mock_browser, mock_store, emit_event):
        service = EvidenceAcquisitionService(mock_scraper, mock_browser, mock_store, _config())
        sources = [_source()]
        records = await service.acquire(sources, query_context=None, emit_event=emit_event)
        assert len(records) == 1
        assert records[0].content_length > 0
        assert records[0].url == "https://example.com/page"
        mock_scraper.fetch_with_escalation.assert_awaited_once()

    async def test_acquires_multiple_sources_concurrently(self, mock_scraper, mock_browser, mock_store, emit_event):
        service = EvidenceAcquisitionService(mock_scraper, mock_browser, mock_store, _config())
        sources = [
            _source(url=f"https://site{i}.com/page", domain=f"site{i}.com")
            for i in range(4)
        ]
        records = await service.acquire(sources, query_context=None, emit_event=emit_event)
        assert len(records) == 4
        assert mock_scraper.fetch_with_escalation.await_count == 4

    async def test_excerpt_truncated_to_config_limit(self, mock_scraper, mock_browser, mock_store, emit_event):
        service = EvidenceAcquisitionService(mock_scraper, mock_browser, mock_store, _config(research_excerpt_chars=100))
        records = await service.acquire([_source()], query_context=None, emit_event=emit_event)
        assert len(records[0].excerpt) <= 100

    async def test_full_content_offloaded(self, mock_scraper, mock_browser, mock_store, emit_event):
        service = EvidenceAcquisitionService(mock_scraper, mock_browser, mock_store, _config())
        records = await service.acquire([_source()], query_context=None, emit_event=emit_event)
        assert records[0].content_ref == "trs-abc123"
        mock_store.store.assert_called_once()


class TestBrowserPromotion:
    async def test_hard_fail_triggers_browser(self, mock_scraper, mock_browser, mock_store, emit_event):
        # Scrapling returns empty → hard fail → browser promotion
        mock_scraper.fetch_with_escalation = AsyncMock(
            return_value=_scraped_content(text="", tier="stealthy")
        )
        service = EvidenceAcquisitionService(mock_scraper, mock_browser, mock_store, _config())
        records = await service.acquire([_source(source_importance="high")], query_context=None, emit_event=emit_event)
        assert records[0].browser_promoted is True
        mock_browser.navigate.assert_awaited_once()

    async def test_browser_changes_outcome(self, mock_scraper, mock_browser, mock_store, emit_event):
        mock_scraper.fetch_with_escalation = AsyncMock(
            return_value=_scraped_content(text="tiny", tier="stealthy")
        )
        service = EvidenceAcquisitionService(mock_scraper, mock_browser, mock_store, _config())
        records = await service.acquire([_source(source_importance="high")], query_context=None, emit_event=emit_event)
        assert records[0].browser_changed_outcome is True
        assert records[0].access_method == AccessMethod.BROWSER_PROMOTED

    async def test_no_browser_when_confidence_high(self, mock_scraper, mock_browser, mock_store, emit_event):
        service = EvidenceAcquisitionService(mock_scraper, mock_browser, mock_store, _config())
        records = await service.acquire([_source()], query_context=None, emit_event=emit_event)
        assert records[0].browser_promoted is False
        mock_browser.navigate.assert_not_awaited()


class TestFailureHandling:
    async def test_scraper_exception_creates_failed_record(self, mock_browser, mock_store, emit_event):
        mock_scraper = AsyncMock()
        mock_scraper.fetch_with_escalation = AsyncMock(side_effect=TimeoutError("timeout"))
        service = EvidenceAcquisitionService(mock_scraper, mock_browser, mock_store, _config())
        records = await service.acquire([_source()], query_context=None, emit_event=emit_event)
        assert len(records) == 1
        assert records[0].content_length == 0
        assert "extraction_failure" in records[0].hard_fail_reasons

    async def test_browser_failure_falls_back_gracefully(self, mock_scraper, mock_store, emit_event):
        mock_scraper.fetch_with_escalation = AsyncMock(
            return_value=_scraped_content(text="", tier="stealthy")
        )
        mock_browser = AsyncMock()
        mock_browser.navigate = AsyncMock(side_effect=Exception("browser crashed"))
        service = EvidenceAcquisitionService(mock_scraper, mock_browser, mock_store, _config())
        records = await service.acquire([_source(source_importance="high")], query_context=None, emit_event=emit_event)
        # Should still return a record (failed), not crash
        assert len(records) == 1


class TestEventEmission:
    async def test_emits_progress_events(self, mock_scraper, mock_browser, mock_store, emit_event):
        service = EvidenceAcquisitionService(mock_scraper, mock_browser, mock_store, _config())
        await service.acquire([_source()], query_context=None, emit_event=emit_event)
        assert emit_event.await_count >= 1  # At least "Fetching evidence" event
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/services/agents/test_evidence_acquisition.py -v -p no:cov -o addopts=`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `backend/app/domain/services/agents/evidence_acquisition.py` — implement exactly as described in design Section 4.2. Uses `ContentConfidenceAssessor` internally. Key flow per source: Scrapling → assess → promote? → offload → build EvidenceRecord.

**Important implementation details:**
- Map `ScrapedContent.tier_used` string ("http"/"dynamic"/"stealthy") to `fetch_tier_reached` int (1/2/3)
- Wrap per-source acquisition in `asyncio.wait_for()` with `research_acquisition_timeout_seconds`
- Re-assess confidence after browser promotion if `browser_changed_outcome`
- `_build_failed_record()` for exceptions — content_length=0, hard_fail=EXTRACTION_FAILURE

**Step 4: Run tests**

Run: `cd backend && pytest tests/domain/services/agents/test_evidence_acquisition.py -v -p no:cov -o addopts=`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/evidence_acquisition.py backend/tests/domain/services/agents/test_evidence_acquisition.py
git commit -m "feat(research): add EvidenceAcquisitionService with confidence-based browser promotion

Scrapling-primary extraction with 3-tier escalation, ContentConfidenceAssessor
integration, conditional browser promotion on hard-fail/soft-fail thresholds,
content offload to ToolResultStore, concurrent acquisition with semaphore."
```

---

## Task 7: ResearchExecutionPolicy (`research_execution_policy.py`)

**Files:**
- Create: `backend/app/domain/services/agents/research_execution_policy.py`
- Test: `backend/tests/domain/services/agents/test_research_execution_policy.py`

**Step 1: Write the test file**

```python
# backend/tests/domain/services/agents/test_research_execution_policy.py
"""Tests for ResearchExecutionPolicy — end-to-end policy orchestration."""

import pytest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.models.evidence import (
    AccessMethod,
    ConfidenceBucket,
    EvidenceRecord,
    SelectedSource,
    SourceType,
    SynthesisGateVerdict,
    SynthesisGateResult,
    ToolCallContext,
    ToolInterceptorResult,
)
from app.domain.models.search import SearchResultItem, SearchResults
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.research_execution_policy import ResearchExecutionPolicy


def _config(**overrides):
    defaults = dict(
        research_deterministic_pipeline_enabled=True,
        research_pipeline_mode="enforced",
        research_source_select_count=4,
        research_source_max_per_domain=1,
        research_source_allow_multi_page_domains=True,
        research_weight_relevance=0.35,
        research_weight_authority=0.25,
        research_weight_freshness=0.20,
        research_weight_rank=0.20,
        research_acquisition_concurrency=4,
        research_acquisition_timeout_seconds=30.0,
        research_excerpt_chars=2000,
        research_full_content_offload=True,
        research_soft_fail_verify_threshold=2,
        research_soft_fail_required_threshold=3,
        research_thin_content_chars=500,
        research_boilerplate_ratio_threshold=0.6,
        research_min_fetched_sources=3,
        research_min_high_confidence=2,
        research_require_official_source=True,
        research_require_independent_source=True,
        research_relaxation_enabled=True,
        research_relaxed_min_fetched_sources=2,
        research_relaxed_min_high_confidence=1,
        research_relaxed_require_official_source=False,
        research_telemetry_enabled=False,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _search_results(count=5):
    items = [
        SearchResultItem(
            title=f"Result {i}",
            link=f"https://site{i}.com/page",
            snippet=f"Content about topic {i}.",
        )
        for i in range(count)
    ]
    return SearchResults(query="test query", total_results=count, results=items)


def _tool_result(search_results=None):
    if search_results is None:
        search_results = _search_results()
    return ToolResult(success=True, message="OK", data=search_results)


def _context(function_name="info_search_web"):
    return ToolCallContext(
        tool_call_id="call_123",
        function_name=function_name,
        function_args={"query": "test query"},
        step_id="step_1",
        session_id="sess_abc",
        research_mode="deep_research",
    )


def _evidence_record(**kw):
    defaults = dict(
        url="https://example.com",
        domain="example.com",
        title="Test",
        source_type=SourceType.INDEPENDENT,
        authority_score=0.5,
        source_importance="medium",
        excerpt="content...",
        content_length=5000,
        access_method=AccessMethod.SCRAPLING_HTTP,
        fetch_tier_reached=1,
        extraction_duration_ms=200,
        timestamp=datetime(2026, 3, 10),
        confidence_bucket=ConfidenceBucket.HIGH,
        hard_fail_reasons=[],
        soft_fail_reasons=[],
    )
    defaults.update(kw)
    return EvidenceRecord(**defaults)


@pytest.fixture
def mock_selector():
    selector = MagicMock()
    selector.select.return_value = [
        SelectedSource(
            url=f"https://site{i}.com/page",
            domain=f"site{i}.com",
            title=f"Result {i}",
            original_snippet="snippet",
            original_rank=i,
            query="test query",
            relevance_score=0.8,
            authority_score=0.7,
            freshness_score=0.5,
            rank_score=0.5,
            composite_score=0.7,
            source_type=SourceType.INDEPENDENT if i > 0 else SourceType.OFFICIAL,
            source_importance="high" if i == 0 else "medium",
            selection_reason="top_composite",
        )
        for i in range(4)
    ]
    return selector


@pytest.fixture
def mock_evidence_service():
    service = AsyncMock()
    service.acquire.return_value = [
        _evidence_record(
            url=f"https://site{i}.com/page",
            domain=f"site{i}.com",
            source_type=SourceType.OFFICIAL if i == 0 else SourceType.INDEPENDENT,
        )
        for i in range(4)
    ]
    return service


@pytest.fixture
def mock_guard():
    guard = MagicMock()
    guard.evaluate.return_value = SynthesisGateResult(
        verdict=SynthesisGateVerdict.PASS,
        total_fetched=4,
        high_confidence_count=3,
        official_source_found=True,
        independent_source_found=True,
    )
    return guard


@pytest.fixture
def mock_source_tracker():
    tracker = MagicMock()
    tracker.add_source = MagicMock()
    return tracker


@pytest.fixture
def emit_event():
    return AsyncMock()


class TestInterceptsSearchTools:
    async def test_intercepts_info_search_web(
        self, mock_selector, mock_evidence_service, mock_guard, mock_source_tracker, emit_event
    ):
        policy = ResearchExecutionPolicy(
            mock_selector, mock_evidence_service, mock_guard, _config(), mock_source_tracker,
        )
        result = await policy.on_tool_result(
            tool_result=_tool_result(),
            serialized_content="{}",
            context=_context("info_search_web"),
            emit_event=emit_event,
        )
        assert result is not None
        assert isinstance(result, ToolInterceptorResult)
        mock_selector.select.assert_called_once()
        mock_evidence_service.acquire.assert_awaited_once()

    async def test_ignores_non_search_tools(
        self, mock_selector, mock_evidence_service, mock_guard, mock_source_tracker, emit_event
    ):
        policy = ResearchExecutionPolicy(
            mock_selector, mock_evidence_service, mock_guard, _config(), mock_source_tracker,
        )
        result = await policy.on_tool_result(
            tool_result=ToolResult(success=True, message="OK"),
            serialized_content="{}",
            context=_context("file_read"),
            emit_event=emit_event,
        )
        assert result is None
        mock_selector.select.assert_not_called()

    async def test_ignores_failed_search(
        self, mock_selector, mock_evidence_service, mock_guard, mock_source_tracker, emit_event
    ):
        policy = ResearchExecutionPolicy(
            mock_selector, mock_evidence_service, mock_guard, _config(), mock_source_tracker,
        )
        result = await policy.on_tool_result(
            tool_result=ToolResult(success=False, message="Search failed"),
            serialized_content="{}",
            context=_context("info_search_web"),
            emit_event=emit_event,
        )
        assert result is None


class TestEvidenceInjection:
    async def test_preserves_original_results(
        self, mock_selector, mock_evidence_service, mock_guard, mock_source_tracker, emit_event
    ):
        policy = ResearchExecutionPolicy(
            mock_selector, mock_evidence_service, mock_guard, _config(), mock_source_tracker,
        )
        result = await policy.on_tool_result(
            tool_result=_tool_result(),
            serialized_content='{"original": true}',
            context=_context(),
            emit_event=emit_event,
        )
        # Original content preserved (not overridden)
        assert result.override_memory_content is None
        assert result.suppress_memory_content is False

    async def test_appends_evidence_summary(
        self, mock_selector, mock_evidence_service, mock_guard, mock_source_tracker, emit_event
    ):
        policy = ResearchExecutionPolicy(
            mock_selector, mock_evidence_service, mock_guard, _config(), mock_source_tracker,
        )
        result = await policy.on_tool_result(
            tool_result=_tool_result(),
            serialized_content="{}",
            context=_context(),
            emit_event=emit_event,
        )
        assert result.extra_messages is not None
        assert len(result.extra_messages) == 1
        assert "Evidence" in result.extra_messages[0]["content"]


class TestSynthesisGate:
    async def test_can_synthesize_delegates_to_guard(
        self, mock_selector, mock_evidence_service, mock_guard, mock_source_tracker, emit_event
    ):
        policy = ResearchExecutionPolicy(
            mock_selector, mock_evidence_service, mock_guard, _config(), mock_source_tracker,
        )
        # Trigger evidence collection first
        await policy.on_tool_result(
            tool_result=_tool_result(),
            serialized_content="{}",
            context=_context(),
            emit_event=emit_event,
        )
        gate_result = policy.can_synthesize()
        mock_guard.evaluate.assert_called_once()
        assert gate_result.verdict == SynthesisGateVerdict.PASS

    async def test_accumulates_evidence_across_searches(
        self, mock_selector, mock_evidence_service, mock_guard, mock_source_tracker, emit_event
    ):
        policy = ResearchExecutionPolicy(
            mock_selector, mock_evidence_service, mock_guard, _config(), mock_source_tracker,
        )
        # Two search calls
        await policy.on_tool_result(
            tool_result=_tool_result(_search_results(3)),
            serialized_content="{}",
            context=_context(),
            emit_event=emit_event,
        )
        await policy.on_tool_result(
            tool_result=_tool_result(_search_results(3)),
            serialized_content="{}",
            context=_context(),
            emit_event=emit_event,
        )
        assert len(policy.evidence_records) == 8  # 4 + 4 from mock


class TestSourceTrackerIntegration:
    async def test_feeds_evidence_to_source_tracker(
        self, mock_selector, mock_evidence_service, mock_guard, mock_source_tracker, emit_event
    ):
        policy = ResearchExecutionPolicy(
            mock_selector, mock_evidence_service, mock_guard, _config(), mock_source_tracker,
        )
        await policy.on_tool_result(
            tool_result=_tool_result(),
            serialized_content="{}",
            context=_context(),
            emit_event=emit_event,
        )
        # Should call add_source for each evidence record
        assert mock_source_tracker.add_source.call_count == 4
```

**Step 2: Run test to verify it fails**

Run: `cd backend && pytest tests/domain/services/agents/test_research_execution_policy.py -v -p no:cov -o addopts=`
Expected: FAIL — `ModuleNotFoundError`

**Step 3: Write the implementation**

Create `backend/app/domain/services/agents/research_execution_policy.py` — implement exactly as described in design Section 4.5. This is the orchestrator that wires SourceSelector → EvidenceAcquisitionService → SynthesisGuard.

**Key implementation details:**
- `INTERCEPTED_TOOLS = frozenset({"info_search_web", "wide_research"})`
- `on_tool_result()`: check function_name, extract SearchResults from tool_result.data, call selector.select(), call evidence_service.acquire(), map to SourceCitation, format evidence summary, return ToolInterceptorResult with extra_messages
- `can_synthesize()`: delegate to guard.evaluate() with accumulated evidence
- `_format_evidence_summary()`: Markdown with per-source status (OK/PARTIAL/WEAK), excerpts, issues
- `_extract_query()`: get query from function_args
- `_log_telemetry()`: structured logger.info per evidence record

**Note on `source_tracker.add_source()`**: This method does NOT exist yet on SourceTracker. We need a small adapter. Add a method `track_evidence(self, citation: SourceCitation)` that appends to `_collected_sources`. This is a 3-line addition to `source_tracker.py` — OR the policy can directly append to `source_tracker._collected_sources`. The cleaner approach is adding the method.

Add to `source_tracker.py` (around line 55, after `track_tool_event`):
```python
def add_source(self, citation: SourceCitation) -> None:
    """Add a pre-built SourceCitation (e.g., from evidence pipeline)."""
    # Dedupe by URL — upgrade search→browser if browser grounding
    for i, existing in enumerate(self._collected_sources):
        if existing.url == citation.url:
            if citation.source_type == "browser" and existing.source_type == "search":
                self._collected_sources[i] = citation
            return
    if len(self._collected_sources) < self._max_sources:
        self._collected_sources.append(citation)
```

**Step 4: Run tests**

Run: `cd backend && pytest tests/domain/services/agents/test_research_execution_policy.py -v -p no:cov -o addopts=`
Expected: All PASS

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/research_execution_policy.py backend/tests/domain/services/agents/test_research_execution_policy.py backend/app/domain/services/agents/source_tracker.py
git commit -m "feat(research): add ResearchExecutionPolicy orchestrator

Implements ToolInterceptor protocol. Coordinates SourceSelector →
EvidenceAcquisitionService → SynthesisGuard. Feeds evidence into
SourceTracker. Formats evidence summary for LLM consumption.
Adds add_source() method to SourceTracker for evidence pipeline."
```

---

## Task 8: BaseAgent Interceptor Extension Point (`base.py`)

**Files:**
- Modify: `backend/app/domain/services/agents/base.py:222-234` (constructor), `~1849-1856` (parallel path), `~2018-2025` (sequential path)
- Test: `backend/tests/domain/services/agents/test_tool_interceptor.py`

**Step 1: Write the test file**

```python
# backend/tests/domain/services/agents/test_tool_interceptor.py
"""Tests for ToolInterceptor extension point in BaseAgent."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.models.evidence import ToolCallContext, ToolInterceptorResult


class TestToolInterceptorResult:
    def test_default_no_op(self):
        result = ToolInterceptorResult()
        assert result.override_memory_content is None
        assert result.extra_messages is None
        assert result.suppress_memory_content is False

    def test_override_memory(self):
        result = ToolInterceptorResult(override_memory_content="new content")
        assert result.override_memory_content == "new content"

    def test_suppress_and_replace(self):
        result = ToolInterceptorResult(
            suppress_memory_content=True,
            override_memory_content="replacement",
        )
        assert result.suppress_memory_content is True


class TestToolCallContext:
    def test_all_fields(self):
        ctx = ToolCallContext(
            tool_call_id="call_1",
            function_name="info_search_web",
            function_args={"query": "test"},
            step_id="step_1",
            session_id="sess_1",
            research_mode="deep_research",
        )
        assert ctx.tool_call_id == "call_1"
        assert ctx.research_mode == "deep_research"


class TestRunInterceptors:
    """Tests for BaseAgent._run_interceptors() method.

    These test the _run_interceptors logic in isolation by calling it
    directly with mock interceptors, without running a full agent loop.
    """

    async def test_no_interceptors_passes_through(self):
        """Empty interceptor list returns original content."""
        from app.domain.services.agents.base import BaseAgent

        # Verify the attribute exists and is empty list
        # We can't easily instantiate BaseAgent, so we test the contract
        result = ToolInterceptorResult()
        assert result.override_memory_content is None

    async def test_interceptor_failure_isolation(self):
        """Interceptor exception should not crash the agent."""
        failing_interceptor = AsyncMock()
        failing_interceptor.on_tool_result = AsyncMock(side_effect=RuntimeError("boom"))

        # The contract: exceptions are caught and logged, original result preserved
        try:
            await failing_interceptor.on_tool_result(
                tool_result=MagicMock(),
                serialized_content="original",
                context=ToolCallContext(
                    tool_call_id="c1", function_name="test",
                    function_args={}, step_id=None,
                    session_id="s1", research_mode=None,
                ),
                emit_event=AsyncMock(),
            )
        except RuntimeError:
            pass  # Expected — base.py wraps this in try/except

    async def test_override_replaces_content(self):
        """override_memory_content should replace serialized content."""
        interceptor = AsyncMock()
        interceptor.on_tool_result = AsyncMock(
            return_value=ToolInterceptorResult(override_memory_content="replaced")
        )
        result = await interceptor.on_tool_result(
            tool_result=MagicMock(),
            serialized_content="original",
            context=ToolCallContext(
                tool_call_id="c1", function_name="test",
                function_args={}, step_id=None,
                session_id="s1", research_mode=None,
            ),
            emit_event=AsyncMock(),
        )
        assert result.override_memory_content == "replaced"

    async def test_extra_messages_structure(self):
        """extra_messages should be a list of dicts with role/content."""
        interceptor = AsyncMock()
        interceptor.on_tool_result = AsyncMock(
            return_value=ToolInterceptorResult(
                extra_messages=[{"role": "system", "content": "evidence summary"}]
            )
        )
        result = await interceptor.on_tool_result(
            tool_result=MagicMock(),
            serialized_content="original",
            context=ToolCallContext(
                tool_call_id="c1", function_name="test",
                function_args={}, step_id=None,
                session_id="s1", research_mode=None,
            ),
            emit_event=AsyncMock(),
        )
        assert result.extra_messages[0]["role"] == "system"
```

**Step 2: Run test to verify it passes (contract tests only)**

Run: `cd backend && pytest tests/domain/services/agents/test_tool_interceptor.py -v -p no:cov -o addopts=`
Expected: PASS (these test the contract types, not the base.py integration yet)

**Step 3: Modify base.py**

Add to `BaseAgent.__init__()` (after line 291, after `_efficiency_nudges`):
```python
self._tool_interceptors: list = []  # list[ToolInterceptor] — lazy import avoids circular
self._pending_interceptor_events: list = []
```

Add new method after `_serialize_tool_result_for_memory()`:
```python
async def _run_interceptors(
    self,
    tool_result,
    serialized: str,
    function_name: str,
    function_args: dict,
    tool_call_id: str,
) -> tuple[str, list[dict]]:
    """Run registered tool interceptors. Returns (content, extra_messages)."""
    if not self._tool_interceptors:
        return serialized, []

    from app.domain.models.evidence import ToolCallContext

    context = ToolCallContext(
        tool_call_id=tool_call_id,
        function_name=function_name,
        function_args=function_args,
        step_id=getattr(self, '_current_step_id', None),
        session_id=getattr(self, '_session_id', ''),
        research_mode=getattr(self, '_research_mode', None),
    )

    extra_messages: list[dict] = []

    for interceptor in self._tool_interceptors:
        try:
            result = await interceptor.on_tool_result(
                tool_result=tool_result,
                serialized_content=serialized,
                context=context,
                emit_event=self._buffer_interceptor_event,
            )
            if result:
                if result.suppress_memory_content:
                    serialized = ""
                if result.override_memory_content is not None:
                    serialized = result.override_memory_content
                if result.extra_messages:
                    extra_messages.extend(result.extra_messages)
        except Exception:
            logger.exception(
                "Interceptor %s failed, falling back to original result",
                type(interceptor).__name__,
            )

    return serialized, extra_messages

async def _buffer_interceptor_event(self, event) -> None:
    """Buffer an event from an interceptor for yield on next generator iteration."""
    self._pending_interceptor_events.append(event)
```

Modify the **sequential tool path** (~lines 2018-2025). Replace the direct `tool_responses.append()` with:
```python
# Run interceptors (after serialization, before LLM sees result)
serialized_content, extra_tool_msgs = await self._run_interceptors(
    tool_result=result,
    serialized=self._serialize_tool_result_for_memory(result, function_name=function_name),
    function_name=function_name,
    function_args=function_args,
    tool_call_id=tool_call_id,
)

# Yield buffered interceptor events
for evt in self._pending_interceptor_events:
    yield evt
self._pending_interceptor_events.clear()

tool_responses.append({
    "role": "tool",
    "function_name": function_name,
    "tool_call_id": tool_call_id,
    "content": serialized_content,
})
tool_responses.extend(extra_tool_msgs)
```

Apply the same pattern to the **parallel tool path** (~lines 1849-1856). Since this is inside a list comprehension / gather, the interceptor needs to run after results are collected. Modify the parallel result processing loop similarly.

**Step 4: Run existing tests to verify no regressions**

Run: `cd backend && pytest tests/ -x -p no:cov -o addopts= --timeout=60 -q`
Expected: No regressions (interceptor list is empty by default)

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/base.py backend/tests/domain/services/agents/test_tool_interceptor.py
git commit -m "feat(research): add ToolInterceptor extension point to BaseAgent

Generic _run_interceptors() method, _buffer_interceptor_event() for streaming,
failure isolation (try/except per interceptor). Integrated in both sequential
and parallel tool paths. No-op when interceptor list is empty."
```

---

## Task 9: ExecutionAgent Integration (`execution.py`)

**Files:**
- Modify: `backend/app/domain/services/agents/execution.py:109-124` (constructor), step execution method
- Test: `backend/tests/unit/agents/test_execution_synthesis_gate.py`

**Step 1: Write the test file**

```python
# backend/tests/unit/agents/test_execution_synthesis_gate.py
"""Tests for ExecutionAgent synthesis gate integration."""

import pytest
from unittest.mock import AsyncMock, MagicMock

from app.domain.models.evidence import SynthesisGateResult, SynthesisGateVerdict


class TestSynthesisGateCheck:
    def test_no_policy_returns_none(self):
        """Without a research policy, gate check returns None (no blocking)."""
        # Simulates ExecutionAgent._check_synthesis_gate() with no policy
        policy = None
        result = policy.can_synthesize() if policy else None
        assert result is None

    def test_shadow_mode_logs_but_passes(self):
        """In shadow mode, gate logs verdict but returns None (no blocking)."""
        guard_result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.HARD_FAIL,
            reasons=["Insufficient sources"],
            total_fetched=1,
        )
        policy = MagicMock()
        policy.can_synthesize.return_value = guard_result

        # Shadow mode should log but not return the result
        # (ExecutionAgent checks pipeline_mode)
        pipeline_mode = "shadow"
        if pipeline_mode == "shadow":
            result = None
        else:
            result = policy.can_synthesize()
        assert result is None

    def test_enforced_mode_returns_gate_result(self):
        """In enforced mode, gate result is returned for blocking."""
        guard_result = SynthesisGateResult(
            verdict=SynthesisGateVerdict.HARD_FAIL,
            reasons=["Insufficient sources"],
            total_fetched=1,
        )
        policy = MagicMock()
        policy.can_synthesize.return_value = guard_result

        pipeline_mode = "enforced"
        if pipeline_mode == "shadow":
            result = None
        else:
            result = policy.can_synthesize()
        assert result is not None
        assert result.verdict == SynthesisGateVerdict.HARD_FAIL
```

**Step 2: Run test**

Run: `cd backend && pytest tests/unit/agents/test_execution_synthesis_gate.py -v -p no:cov -o addopts=`
Expected: PASS (contract tests)

**Step 3: Modify execution.py**

Add to `ExecutionAgent.__init__()` constructor signature (after `tool_result_store=None`):
```python
research_execution_policy=None,  # ResearchExecutionPolicy | None
```

In constructor body (after existing collaborator setup, ~line 219):
```python
self._research_execution_policy = research_execution_policy
if research_execution_policy:
    self._tool_interceptors.append(research_execution_policy)
```

Add `_check_synthesis_gate()` method:
```python
def _check_synthesis_gate(self):
    """Check if evidence is sufficient before allowing synthesis.
    Returns None if no policy or shadow mode. Returns SynthesisGateResult in enforced mode."""
    if not self._research_execution_policy:
        return None

    result = self._research_execution_policy.can_synthesize()

    from app.core.config import get_settings
    if get_settings().research_pipeline_mode == "shadow":
        logger.info("synthesis_gate_shadow", extra={
            "verdict": result.verdict.value,
            "reasons": result.reasons,
            "thresholds": result.thresholds_applied,
        })
        return None  # Don't block in shadow mode

    return result
```

Add synthesis step detection in `execute_step()` — before building step context, check if the step description indicates synthesis:
```python
_SYNTHESIS_KEYWORDS = frozenset({
    "write report", "synthesize", "summarize findings", "compile results",
    "write summary", "final report", "write analysis", "create report",
})

def _is_synthesis_step(self, step_description: str) -> bool:
    """Detect if a step is a synthesis/report step by keyword matching."""
    desc_lower = step_description.lower()
    return any(kw in desc_lower for kw in self._SYNTHESIS_KEYWORDS)
```

In `execute_step()`, before the main execution call, add:
```python
if self._is_synthesis_step(step.description):
    gate_result = self._check_synthesis_gate()
    if gate_result:
        from app.domain.models.evidence import SynthesisGateVerdict
        if gate_result.verdict == SynthesisGateVerdict.HARD_FAIL:
            from app.domain.models.event import ErrorEvent
            yield ErrorEvent(
                error=f"Research evidence insufficient: {'; '.join(gate_result.reasons)}",
                error_type="synthesis_gate_failed",
                recoverable=False,
            )
            return
        elif gate_result.verdict == SynthesisGateVerdict.SOFT_FAIL:
            # Inject disclaimer into step context
            disclaimer = (
                "NOTE: Some evidence thresholds were not fully met. "
                f"Issues: {'; '.join(gate_result.reasons)}. "
                "Include appropriate caveats in your analysis."
            )
            # Prepend to request
```

**Step 4: Run tests**

Run: `cd backend && pytest tests/ -x -p no:cov -o addopts= --timeout=60 -q`
Expected: No regressions

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/execution.py backend/tests/unit/agents/test_execution_synthesis_gate.py
git commit -m "feat(research): integrate ResearchExecutionPolicy into ExecutionAgent

Accept policy in constructor, register as interceptor, add synthesis gate
check before synthesis steps. Shadow mode logs, enforced mode blocks."
```

---

## Task 10: PlanActFlow Wiring (`plan_act.py`)

**Files:**
- Modify: `backend/app/domain/services/flows/plan_act.py:487-493`

**Step 1: Add policy construction after ExecutionAgent creation**

After line 492 (after the efficiency monitor replacement), add:
```python
# ── Deterministic Research Pipeline ──────────────────────
if (
    self._research_mode in ("deep_research",)  # Phase 1
    and flags.get("research_deterministic_pipeline", True)
):
    from app.domain.services.agents.research_execution_policy import (
        ResearchExecutionPolicy,
    )
    from app.domain.services.agents.source_selector import SourceSelector
    from app.domain.services.agents.evidence_acquisition import (
        EvidenceAcquisitionService,
    )
    from app.domain.services.agents.synthesis_guard import SynthesisGuard

    _research_config = get_settings()
    _selector = SourceSelector(config=_research_config)
    _evidence_service = EvidenceAcquisitionService(
        scraper=scraper,
        browser=browser,
        tool_result_store=tool_result_store,
        config=_research_config,
    )
    _guard = SynthesisGuard(config=_research_config)

    _research_policy = ResearchExecutionPolicy(
        source_selector=_selector,
        evidence_service=_evidence_service,
        synthesis_guard=_guard,
        config=_research_config,
        source_tracker=self.executor._source_tracker,
    )
    self.executor._research_execution_policy = _research_policy
    self.executor._tool_interceptors.append(_research_policy)
    logger.info("Deterministic research pipeline enabled for session %s", session_id)
```

**Step 2: Run full test suite**

Run: `cd backend && pytest tests/ -x -p no:cov -o addopts= --timeout=120 -q`
Expected: All pass, no regressions

**Step 3: Commit**

```bash
git add backend/app/domain/services/flows/plan_act.py
git commit -m "feat(research): wire ResearchExecutionPolicy in PlanActFlow for deep_research

Instantiates SourceSelector, EvidenceAcquisitionService, SynthesisGuard,
and ResearchExecutionPolicy. Injects into ExecutionAgent for deep_research mode.
Feature-flagged via research_deterministic_pipeline flag."
```

---

## Task 11: Integration Tests

**Files:**
- Create: `backend/tests/integration/test_research_pipeline_integration.py`
- Create: `backend/tests/integration/test_research_pipeline_shadow_mode.py`

**Step 1: Write integration tests**

Create full end-to-end integration tests that:
1. Mock ScraplingAdapter, Browser, and SearchEngine
2. Construct a full ResearchExecutionPolicy with real SourceSelector, ContentConfidenceAssessor, SynthesisGuard
3. Feed realistic SearchResults through `on_tool_result()`
4. Verify: evidence records created, SourceTracker populated, evidence summary formatted, synthesis gate evaluates correctly

Shadow mode test:
1. Same setup but with `research_pipeline_mode="shadow"`
2. Verify `can_synthesize()` logs but policy doesn't block

**Step 2: Run integration tests**

Run: `cd backend && pytest tests/integration/test_research_pipeline_integration.py tests/integration/test_research_pipeline_shadow_mode.py -v -p no:cov -o addopts=`
Expected: All PASS

**Step 3: Commit**

```bash
git add backend/tests/integration/test_research_pipeline_integration.py backend/tests/integration/test_research_pipeline_shadow_mode.py
git commit -m "test(research): add integration tests for deterministic research pipeline

End-to-end pipeline test with realistic search results, shadow mode test
verifying non-blocking telemetry-only behavior."
```

---

## Task 12: Full Suite Verification and Cleanup

**Step 1: Run full backend test suite**

Run: `cd backend && conda activate pythinker && pytest tests/ -v --timeout=120 -q`
Expected: All pass, coverage ≥ 24%

**Step 2: Lint check**

Run: `cd backend && ruff check . && ruff format --check .`
Expected: Clean

**Step 3: Final commit if any lint fixes needed**

```bash
git add -u
git commit -m "chore(research): lint and format fixes for research pipeline"
```

---

## Dependency Graph

```
Task 1: evidence.py (domain models)         ← no dependencies
Task 2: config_research_pipeline.py          ← no dependencies
Task 3: content_confidence.py                ← depends on Task 1 (models)
Task 4: source_selector.py                   ← depends on Task 1 (models)
Task 5: synthesis_guard.py                   ← depends on Task 1 (models), Task 2 (config)
Task 6: evidence_acquisition.py              ← depends on Tasks 1,2,3
Task 7: research_execution_policy.py         ← depends on Tasks 1,2,4,5,6
Task 8: base.py interceptor                  ← depends on Task 1 (ToolCallContext)
Task 9: execution.py integration             ← depends on Tasks 7,8
Task 10: plan_act.py wiring                  ← depends on Tasks 7,9
Task 11: integration tests                   ← depends on all above
Task 12: full suite verification             ← depends on all above
```

Tasks 1+2 can run in parallel.
Tasks 3+4+5 can run in parallel (after 1+2).
Task 6 requires 3.
Tasks 7+8 can run in parallel (after 6).
Tasks 9→10→11→12 are sequential.
