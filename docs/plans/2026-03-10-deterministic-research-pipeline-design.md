# Deterministic Research Pipeline — Design Document

**Date**: 2026-03-10
**Status**: Approved
**Scope**: Phase 1 — `deep_research` mode; Phase 2+ metrics-driven expansion

## Problem

The current research pipeline trusts the LLM to browse after searching. It doesn't. Reports get built on 2000-char auto-enriched snippets instead of real page content.

**Root cause**: The "Browser-First Deep Research" prompt is injected into the planner system prompt only (`plan_act.py:2704-2787`), never the execution agent. Browsing only happens if the planner encodes it into step descriptions AND the executor LLM obeys. The SYSTEM NOTE in search tool results (`search.py:1393-1408`) tries to guide the LLM to browse, but enriched 2000-char snippets often satisfy the LLM enough that it skips browsing entirely.

**Fix**: Move research evidence acquisition from prompt-guided LLM behavior to a code-enforced policy that intercepts search results, selects sources deterministically, acquires full content, and blocks synthesis until evidence thresholds are met.

## Design Principles

1. **Runtime policy, not prompt guidance** — enforcement lives in the execution layer, not in planner prompts
2. **Scrapling-primary with confidence-based browser verification** — one canonical extraction path, browser as safety net
3. **Evidence records as single source of truth** — synthesis reads from normalized evidence, not raw snippets
4. **Two-axis assessment** — `content_confidence` and `source_importance` are separate, never mixed
5. **Tiered rules for decisions, shadow score for telemetry** — deterministic now, tunable later
6. **Policy-driven thresholds** — relaxable for niche topics, never hardcoded absolutes
7. **Shadow mode ships first** — observe before enforcing

## Architecture

### Component Diagram

```
PlanActFlow (plan_act.py)
  → Instantiates ResearchExecutionPolicy for research modes
  → Injects policy into ExecutionAgent

ExecutionAgent (execution.py)
  → Owns ResearchExecutionPolicy instance
  → Calls policy via ToolInterceptor contract after search tools return
  → Calls policy.can_synthesize() before allowing report steps

BaseAgent (base.py)
  → Generic ToolInterceptor extension point
  → Runs interceptors after tool result serialization, before LLM sees result
  → Supports streaming event emission during interception

ResearchExecutionPolicy
  ├── SourceSelector         → Deterministic URL ranking and selection
  ├── EvidenceAcquisitionService → Scrapling extraction + confidence + browser promotion
  │   └── ContentConfidenceAssessor → Tiered hard-fail/soft-fail assessment
  └── SynthesisGuard         → Pre-synthesis quality gate
```

### Execution Flow

```
Search tool returns ToolResult(data=SearchResults)
    │
    ▼
BaseAgent._run_interceptors()
    │
    ▼ (research mode active?)
ResearchExecutionPolicy.on_tool_result()
    │
    ├── 1. SourceSelector.select(results, query_context)
    │     Normalize → Score → Classify → Constrain → Top 3-4
    │
    ├── 2. EvidenceAcquisitionService.acquire(selected_sources)
    │     For each source (concurrent, semaphore=4):
    │       Scrapling fetch_with_escalation (HTTP → Dynamic → Stealthy)
    │       ContentConfidenceAssessor.assess()
    │       If promotion required: Browser.navigate() for full extraction
    │       Build immutable EvidenceRecord
    │       Offload full content to ToolResultStore, keep 2000-char excerpt
    │
    ├── 3. Feed EvidenceRecords → SourceTracker (existing grounding path)
    │
    └── 4. Return ToolInterceptorResult:
          - Preserve original search results (for debugging/replay)
          - Append evidence summary as extra system message
          - LLM synthesizes from evidence, not snippets

─── Before synthesis step ───

ExecutionAgent._check_synthesis_gate()
    │
    ▼
SynthesisGuard.evaluate(evidence_records)
    ├── PASS → allow synthesis
    ├── SOFT_FAIL → allow with disclaimer
    └── HARD_FAIL → block, emit ErrorEvent
```

## Interceptor Contract

### ToolCallContext (typed, not dict)

```python
@dataclass(frozen=True, slots=True)
class ToolCallContext:
    tool_call_id: str
    function_name: str
    function_args: dict[str, Any]
    step_id: str | None
    session_id: str
    research_mode: str | None  # "deep_research" | "wide_research" | None
```

### ToolInterceptorResult

```python
@dataclass(slots=True)
class ToolInterceptorResult:
    override_memory_content: str | None = None   # Replace what LLM sees
    extra_messages: list[dict] | None = None      # Appended directly into tool_responses
    suppress_memory_content: bool = False          # Suppress LLM observation of original
```

### ToolInterceptor Protocol

```python
class ToolInterceptor(Protocol):
    async def on_tool_result(
        self,
        tool_result: ToolResult,
        serialized_content: str,
        context: ToolCallContext,
        emit_event: Callable[[BaseEvent], Awaitable[None]],
    ) -> ToolInterceptorResult | None: ...
```

**Key properties**:
- `emit_event` callback: stream ProgressEvents during long-running evidence acquisition
- `extra_messages` appended directly into `tool_responses` (ordering preserved, not buffered)
- Failure isolation: interceptor exceptions caught, logged, original result preserved
- Named boundary fields: `override_memory_content` / `suppress_memory_content` (not UI)

## Data Models

### EvidenceRecord (domain/models/evidence.py)

```python
class EvidenceRecord(BaseModel):
    model_config = ConfigDict(frozen=True)

    # Identity
    url: str
    domain: str
    title: str

    # Classification
    source_type: SourceType  # official | authoritative_neutral | independent | ugc_low_trust
    authority_score: float   # 0.0-1.0, separate from confidence
    source_importance: Literal["high", "medium", "low"]

    # Content (excerpt only inline — full content offloaded)
    excerpt: str                    # ~2000 chars for LLM context
    content_length: int
    content_ref: str | None = None  # Pointer to ToolResultStore

    # Extraction metadata
    access_method: AccessMethod     # scrapling_http | scrapling_dynamic | scrapling_stealthy | browser_promoted | browser_fallback
    fetch_tier_reached: int         # 1, 2, or 3
    extraction_duration_ms: int
    timestamp: datetime

    # Confidence assessment
    confidence_bucket: ConfidenceBucket  # HIGH | MEDIUM | LOW
    hard_fail_reasons: list[str]
    soft_fail_reasons: list[str]
    soft_point_total: int = 0

    # Browser promotion telemetry
    browser_promoted: bool = False
    browser_changed_outcome: bool = False

    # Provenance (preserved, separate from excerpt)
    original_snippet: str | None = None
    original_rank: int = 0
    query: str = ""
```

### SelectedSource, ConfidenceAssessment, SynthesisGateResult

See component contracts below for full field definitions.

### Mapper: EvidenceRecord → SourceCitation

```python
def evidence_to_source_citation(record: EvidenceRecord) -> SourceCitation:
    source_type_map = {
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

## Component Contracts

### SourceSelector

Deterministic pipeline: normalize → score → classify → constrain → select top N.

**Scoring axes** (configurable weights):
- `relevance_score` (0.35): query token overlap with title + snippet
- `authority_score` (0.25): from source classification
- `freshness_score` (0.20): date extraction, decay curve
- `rank_score` (0.20): 1/(rank+1) position discount

**Source classification** (four-tier, rule-based, no LLM):
- **official**: exact vendor/project domain, docs subdomain, .gov, .edu, official GitHub org
- **authoritative_neutral**: MDN, Wikipedia, established tech publications
- **independent**: news sites, blogs, comparison sites
- **ugc_low_trust**: forums, aggregators, mirrors, spammy rewrite sites

Classification pipeline:
1. Domain heuristic patterns (strong official, strong low-trust)
2. Entity-domain matching overlay (query tokens vs hostname/path/title)
3. Two separate labels: `source_type` + `authority_score` (avoids false binaries)

**Constraint enforcement**:
- At least 1 official (if any exist in results)
- At least 1 independent
- Max 1 per domain (allow 2 only for explicit multi-page needs)
- Comparative/adversarial intent detection → official doesn't dominate

### ContentConfidenceAssessor

**Hard-fail triggers** (any one → LOW confidence, REQUIRED browser promotion):
- Block/paywall/challenge markers
- JS shell / empty rendered content after Tier 3
- Extraction failure (<50 chars)
- Required field missing on critical (high-importance) page
- Severe title/URL/content mismatch

**Soft-fail triggers** (integer points, not pseudo-probabilities):
- Thin content (<500 chars)
- Boilerplate-heavy page (>0.6 ratio)
- Missing required entities (<30% match)
- No publish/update date (time-sensitive tasks)
- Weak content density (<0.3 unique word ratio)
- Partial structured extraction

**Decision matrix**:
```
hard_fail present       → LOW, REQUIRED
3+ soft points          → LOW, REQUIRED
2 soft + HIGH importance → MEDIUM, REQUIRED
2 soft + MED/LOW importance → MEDIUM, NO_VERIFY
0-1 soft points         → HIGH, NO_VERIFY
```

**Shadow score**: Computed for telemetry (0.0-1.0), NOT used for decisions.

### EvidenceAcquisitionService

For each selected source (concurrent, semaphore=4):
1. Scrapling `fetch_with_escalation()` (existing 3-tier: HTTP → Dynamic → Stealthy)
2. `ContentConfidenceAssessor.assess()`
3. Promotion decision → if REQUIRED: `Browser.navigate()` for full extraction
4. Re-assess confidence after browser promotion if outcome changed
5. Offload full content to `ToolResultStore`, keep 2000-char excerpt
6. Build immutable `EvidenceRecord`
7. Fire background `browser.navigate()` for CDP display (if not already promoted)

### SynthesisGuard

**Default thresholds**:
- 3+ sources actually fetched
- 2+ sources HIGH confidence
- 1+ official source (if available)
- 1+ independent source

**Relaxed thresholds** (activated when <5 search results OR all official URLs failed):
- 2+ sources fetched
- 1+ HIGH confidence
- Official not required

**Comparative/adversarial intent**: default thresholds but `require_official = False`.

**Verdicts**:
- `PASS` → allow synthesis
- `SOFT_FAIL` → allow with disclaimer injected into step context
- `HARD_FAIL` → block synthesis, emit ErrorEvent

## Configuration

All settings in `core/config_research_pipeline.py`, environment-variable overridable via `RESEARCH_*` prefix.

### Feature Flags
- `research_deterministic_pipeline_enabled: bool = True`
- `research_pipeline_mode: Literal["shadow", "enforced"] = "shadow"`

### Source Selection
- `research_source_select_count: int = 4`
- `research_source_max_per_domain: int = 1`
- `research_source_allow_multi_page_domains: bool = True`
- `research_weight_relevance/authority/freshness/rank: float` (0.35/0.25/0.20/0.20)

### Evidence Acquisition
- `research_acquisition_concurrency: int = 4`
- `research_acquisition_timeout_seconds: float = 30.0`
- `research_excerpt_chars: int = 2000`
- `research_full_content_offload: bool = True`

### Confidence Thresholds
- `research_soft_fail_verify_threshold: int = 2`
- `research_soft_fail_required_threshold: int = 3`
- `research_thin_content_chars: int = 500`
- `research_boilerplate_ratio_threshold: float = 0.6`

### Synthesis Gate (default + relaxed)
- `research_min_fetched_sources: int = 3` / relaxed: `2`
- `research_min_high_confidence: int = 2` / relaxed: `1`
- `research_require_official_source: bool = True` / relaxed: `False`
- `research_require_independent_source: bool = True`
- `research_relaxation_enabled: bool = True`

### Telemetry
- `research_telemetry_enabled: bool = True`

## Integration Points

### base.py (~50 lines)
- `self._tool_interceptors: list[ToolInterceptor] = []`
- `_run_interceptors()` method
- Integration in tool loop (both sequential and parallel paths): after serialization, before `tool_responses.append()`
- Yield buffered interceptor events, then append tool result, then extend with extra messages

### execution.py (~60 lines)
- Accept `research_execution_policy` in constructor
- Register as interceptor
- `_check_synthesis_gate()` before synthesis steps
- Synthesis step detection by keyword matching on step description

### plan_act.py (~40 lines)
- Instantiate SourceSelector, EvidenceAcquisitionService, SynthesisGuard, ResearchExecutionPolicy
- Inject into ExecutionAgent for `deep_research` mode (Phase 1)
- Uses existing `scraper` and `browser` references from tool construction

### source_tracker.py (no structural changes)
- Receives `SourceCitation` via `evidence_to_source_citation()` mapper
- Browser-promoted evidence → `source_type="browser"` (higher grounding weight)

### Delivery integrity gates (no code changes)
- Benefit passively from richer evidence in SourceTracker
- Pre-synthesis gate catches insufficient evidence before report generation

## Rollout

### Phase 1: Shadow Mode
- Pipeline runs fully, SynthesisGuard logs but doesn't block
- LLM receives evidence summaries (immediate quality improvement)
- Telemetry collects per-URL assessment data
- `deep_research` only

### Phase 2: Enforced Mode
- Flip `research_pipeline_mode = "enforced"` after reviewing shadow metrics
- HARD_FAIL blocks synthesis, SOFT_FAIL injects disclaimer

### Phase 3: Expand to wide_research
- Data-driven decision based on shadow telemetry
- Add `"wide_research"` to research mode check in plan_act.py

## File Inventory

### New Files (12 source + 8 test)

| File | Layer | Est. Lines |
|---|---|---|
| `domain/services/agents/research_execution_policy.py` | Domain | ~250 |
| `domain/services/agents/source_selector.py` | Domain | ~300 |
| `domain/services/agents/evidence_acquisition.py` | Domain | ~250 |
| `domain/services/agents/content_confidence.py` | Domain | ~250 |
| `domain/services/agents/synthesis_guard.py` | Domain | ~150 |
| `domain/services/agents/tool_interceptor.py` | Domain | ~40 |
| `domain/models/evidence.py` | Domain | ~120 |
| `core/config_research_pipeline.py` | Core | ~60 |
| `tests/domain/services/test_source_selector.py` | Test | ~400 |
| `tests/domain/services/test_content_confidence.py` | Test | ~350 |
| `tests/domain/services/test_evidence_acquisition.py` | Test | ~300 |
| `tests/domain/services/test_synthesis_guard.py` | Test | ~250 |
| `tests/domain/services/test_research_execution_policy.py` | Test | ~300 |
| `tests/domain/services/test_tool_interceptor.py` | Test | ~200 |
| `tests/integration/test_research_pipeline_integration.py` | Test | ~250 |
| `tests/integration/test_research_pipeline_shadow_mode.py` | Test | ~150 |

### Modified Files (5)

| File | Change | Est. Lines |
|---|---|---|
| `base.py` | Interceptor list, `_run_interceptors()`, tool loop integration | ~50 |
| `execution.py` | Accept policy, register interceptor, synthesis gate | ~60 |
| `plan_act.py` | Instantiate policy for research modes | ~40 |
| `config.py` | Add `ResearchPipelineSettingsMixin` | ~2 |
| `config_features.py` | Add feature flag key | ~2 |

**Total**: ~1,590 lines source + ~2,200 lines tests = ~3,790 lines

## What This Does NOT Change

- `info_search_web` API search path (still the discovery mechanism)
- Auto-enrichment in `search.py` (still runs as preliminary evidence)
- `wide_research` tool (unchanged in Phase 1)
- Planner prompt injection (can be simplified later, not blocking)
- Delivery integrity gates (enhanced passively, not replaced)
- `base.py` tool loop structure (only adds interceptor extension point)
