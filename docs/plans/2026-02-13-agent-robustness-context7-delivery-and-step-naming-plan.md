# Agent Robustness Plan: Request Fidelity, Step Naming Quality & Delivery Integrity

**Date:** 2026-02-13
**Revised:** 2026-02-13
**Status:** Proposed
**Scope:** Improve agent reliability, relevance, and output correctness by hardening request fidelity, step/task naming, routing, guardrails, and delivery validation.

---

## Objectives

1. Ensure agent responses stay faithful to user request entities/versions (e.g., `Claude Sonnet 4.5` must never become `Sonnet 5`).
2. Reduce unrelated/off-topic responses by adding deterministic pre-execution and pre-delivery checks.
3. Improve plan-step/task naming quality so routing and execution remain precise.
4. Add measurable quality gates and tracing for continuous tuning.
5. Provide independent feature flags and rollback for each component.

---

## Why This Plan

Current architecture includes strong components (`EnhancedPromptQuickValidator`, `FastPathRouter`, `OutputCoverageValidator`, `OutputGuardrails`, compliance gates), but behavior can still drift when:

- **Prompt normalization** only fixes surface typos (`enhanced_prompt_quick_validator.py:294-320`) — no entity extraction or canonicalization occurs.
- **Fast-path classification** (`fast_path.py`) routes queries by intent (`GREETING`, `KNOWLEDGE`, etc.) without checking entity fidelity.
- **Planner step names** are LLM-generated free-form text (`Step.description`, `plan.py:131`) — merging via `_consolidate_similar_steps()` (`planner.py:609-646`) creates generic labels that lose specificity.
- **OutputGuardrails** (`guardrails.py:539-762`) exist with relevance checking (`_check_relevance`, line 685) and contradiction detection (`_check_consistency`, line 717) but are **not wired into PlanActFlow's SUMMARIZING phase**. Final validation only runs compliance gates (security/policy), not semantic fidelity.

### Verified Architecture Gaps

| Gap | Evidence | Impact |
|-----|----------|--------|
| No entity extraction at ingress | `PlanActFlow.run()` passes raw `message.message` to fast-path | Same query with entity variations produces different plans |
| Free-form step descriptions | `Step` model only has `description: str` (plan.py:131) | LLM generates different labels for identical operations |
| Merging destroys specificity | `_normalize_plan_steps()` creates "Consolidate remaining..." (planner.py:698) | Downstream routing loses context |
| OutputGuardrails disconnected | Not imported or called in `plan_act.py` | Relevance/consistency checks never run |
| No entity drift detection | Zero references to entity tracking anywhere | Drift is invisible |

---

## Phase Plan and Status

| Phase | Status | Size | Primary Outcome |
|---|---|:---:|---|
| 0. Baseline + Wire Existing Guardrails | Not Started | M | OutputGuardrails integrated, Prometheus metrics, latency baseline |
| 1. Request Contract + Locked Terms | Not Started | L | Immutable contract extracted at ingress with entity locking |
| 2. Structured Step Model | Not Started | M | Plan steps use typed fields, not free-form text |
| 3. Delivery Integrity v2 | Not Started | L | Final response blocked if entity mismatch or low relevance |
| 4. Router + Search Fidelity Guardrails | Not Started | M | Entity fidelity enforced in search queries and LLM prompts |
| 5. Contradiction / Bad-Logic Clarification | Not Started | S | Contradictory prompts trigger clarification path |
| 6. Evaluation + Regression Suite | Not Started | M | Continuous regression with shadow-to-enforce rollout |

**Execution priority:** 0 → 1 → 2 → 3 → 4 → 5 (Phase 6 runs continuously from Phase 0 onward)

---

## Feature Flags

All new components are gated by feature flags in `backend/app/core/config.py` (Settings class). Each flag defaults to `False` so nothing activates until explicitly enabled.

```python
# --- Agent Robustness Feature Flags ---
# Phase 0
enable_output_guardrails_in_flow: bool = False  # Wire OutputGuardrails into SUMMARIZING

# Phase 1
enable_request_contract: bool = False  # Extract RequestContract at ingress

# Phase 2
enable_structured_step_model: bool = False  # Use structured Step fields instead of free-form

# Phase 3
enable_delivery_fidelity_v2: bool = False  # Entity/relevance fidelity in delivery gate
delivery_fidelity_mode: str = "shadow"  # "shadow" | "warn" | "enforce"

# Phase 4
enable_search_fidelity_guardrail: bool = False  # Entity fidelity in search queries

# Phase 5
enable_contradiction_clarification: bool = False  # Contradictory prompt detection
```

**Rollback:** Set any flag to `False` to immediately disable that component with zero code changes.

---

## Detailed Workstreams

### Phase 0: Baseline + Wire Existing Guardrails

**Goal:** Get immediate data by (a) wiring the existing `OutputGuardrails` into `PlanActFlow` and (b) adding Prometheus metrics for all robustness dimensions.

#### Task 0.1: Wire OutputGuardrails into PlanActFlow (S)

**What:** Import and call `OutputGuardrails.analyze()` in the SUMMARIZING phase of `PlanActFlow`, gated by `enable_output_guardrails_in_flow`.

**Where to modify:**
- `backend/app/domain/services/flows/plan_act.py` — SUMMARIZING phase (around line 2552)
  - Import `OutputGuardrails` from `guardrails.py`
  - After `executor.summarize()` generates the report content, call `output_guardrails.analyze(content, original_query=message.message)`
  - Log the `OutputAnalysisResult` (issues, relevance score, needs_revision)
  - In shadow mode: log only, never block
  - In enforce mode: if `not result.should_deliver`, emit `ErrorEvent` and transition to `ERROR`

**Existing code to reuse:**
- `OutputGuardrails` class — `guardrails.py:539-762` (already has `analyze()`, `_check_relevance()`, `_check_consistency()`)
- `GuardrailsManager` — `guardrails.py:769-831` (already wraps input+output)

**Test:**
- `backend/tests/domain/services/flows/test_plan_act_output_guardrails.py`
- Verify: off-topic output detected, contradictory output flagged, safe output passes

#### Task 0.2: Add Prometheus Robustness Metrics (S)

**What:** Add counters and histograms to `prometheus_metrics.py` for tracking robustness.

**Metrics to add:**
```python
# Counters
entity_drift_detected_total = Counter("pythinker_entity_drift_detected_total", ...)
output_relevance_failures_total = Counter("pythinker_output_relevance_failures_total", ...)
step_name_quality_violations_total = Counter("pythinker_step_name_quality_violations_total", ...)
guardrail_tripwire_total = Counter("pythinker_guardrail_tripwire_total", ...)
delivery_fidelity_blocks_total = Counter("pythinker_delivery_fidelity_blocks_total", ...)

# Histograms
guardrail_latency_seconds = Histogram("pythinker_guardrail_latency_seconds", ...)
output_relevance_score = Histogram("pythinker_output_relevance_score", ...)
```

**Where to modify:**
- `backend/app/infrastructure/observability/prometheus_metrics.py` — add metrics following existing patterns
- `backend/app/interfaces/api/metrics_routes.py` — expose via `/metrics` endpoint (already exists)

**Test:**
- `backend/tests/infrastructure/observability/test_robustness_metrics.py`

#### Task 0.3: Baseline Latency Measurement (S)

**What:** Measure current `PlanActFlow.run()` end-to-end latency distribution before adding guardrails.

**How:** Add timing instrumentation around the SUMMARIZING phase. Record P50/P95/P99 for 20+ representative prompts. Store results in `docs/reports/` as baseline reference.

**No test needed** — this is a measurement task.

---

### Phase 1: Request Contract + Locked Terms

**Goal:** Extract an immutable `RequestContract` at ingress that preserves the user's exact entities, versions, and numeric constraints throughout the pipeline.

#### Task 1.1: Define RequestContract Domain Model (S)

**What:** Create a Pydantic domain model representing the immutable contract.

**File:** `backend/app/domain/models/request_contract.py`

```python
class RequestContract(BaseModel):
    """Immutable contract extracted from user request at ingress.

    Preserves exact entities, versions, and constraints that must not
    be mutated by normalization, planning, or execution stages.
    """
    exact_query: str  # Original user text, unmodified
    intent: str  # Classified intent (from FastPathRouter)
    action_type: str  # "research", "browse", "code", "general"

    # Locked terms — must appear in final output
    locked_entities: list[str] = []  # e.g., ["Claude Sonnet 4.5", "Python 3.12"]
    locked_versions: list[str] = []  # e.g., ["4.5", "3.12"]
    numeric_constraints: list[str] = []  # e.g., ["top 5", "under $100"]

    # Extraction metadata
    extraction_method: str = "hybrid"  # "regex", "llm", "hybrid"
    extraction_confidence: float = 1.0
```

**DDD layer:** Domain model (no external dependencies).

#### Task 1.2: Implement Entity Extraction (M)

**What:** Build the extraction logic that populates `RequestContract.locked_entities` and `locked_versions`.

**File:** `backend/app/domain/services/flows/request_contract_extractor.py`

**Extraction strategy (hybrid, no LLM call required):**

1. **Regex patterns for known entity types:**
   - Model names: `Claude\s+(Sonnet|Opus|Haiku)\s+\d+(\.\d+)?`, `GPT-?\d+(\.\d+)?`, `Llama\s*\d+`
   - Version numbers: `v?\d+\.\d+(\.\d+)?`, `version\s+\d+`
   - Technology names: match against existing technical terms whitelist in `enhanced_prompt_quick_validator.py:57-124`
   - Numeric constraints: `top\s+\d+`, `\d+\s*(items|results|examples)`, `under\s+\$?\d+`

2. **Fallback for unrecognized entities:**
   - Quoted strings: `"exact phrase"` or `'exact phrase'`
   - Capitalized multi-word sequences: `Proper Noun Sequences`
   - These get lower `extraction_confidence` (0.7 vs 1.0 for regex matches)

3. **No LLM call** — extraction must be deterministic and fast (< 5ms).

**Test:**
- `backend/tests/domain/services/flows/test_request_contract_extractor.py`
- Cases: model names, version numbers, quoted strings, mixed queries, no entities

#### Task 1.3: Integrate RequestContract into PlanActFlow (M)

**What:** Extract the contract at the start of `PlanActFlow.run()` and propagate it through the pipeline.

**Where to modify:**
- `backend/app/domain/services/flows/plan_act.py`
  - After message validation, before fast-path routing (around line 1728):
    ```python
    if settings.enable_request_contract:
        self._request_contract = RequestContractExtractor.extract(message.message)
    ```
  - Store on `self._request_contract` for access by downstream stages
  - Pass to `PlannerAgent` via context dict
  - Pass to `OutputGuardrails` in SUMMARIZING phase

- `backend/app/domain/services/flows/enhanced_prompt_quick_validator.py`
  - If `locked_entities` exist, skip fuzzy correction for tokens that match locked terms
  - Prevents typo correction from mutating `"Sonnet 4.5"` to something else

**Test:**
- `backend/tests/domain/services/flows/test_request_contract_integration.py`
- Verify: locked entities survive normalization, contract propagates to planner and summarizer

---

### Phase 2: Structured Step Model

**Goal:** Replace free-form `Step.description` with structured fields that the LLM fills via Pydantic structured output. This is more reliable than regex-validating free-form text.

#### Task 2.1: Extend Step Model with Structured Fields (S)

**What:** Add typed fields to the existing `Step` model in `plan.py`.

**Where to modify:** `backend/app/domain/models/plan.py` (line 127-159)

```python
class Step(BaseModel):
    # ... existing fields ...

    # Structured naming fields (Phase 2)
    action_verb: str | None = None  # e.g., "Search", "Browse", "Analyze", "Write"
    target_object: str | None = None  # e.g., "Python 3.12 release notes"
    tool_hint: str | None = None  # e.g., "web_search", "browser", "file"
    # expected_output already exists (line 148)

    @computed_field
    @property
    def display_label(self) -> str:
        """Generate deterministic display label from structured fields."""
        if self.action_verb and self.target_object:
            parts = [self.action_verb, self.target_object]
            if self.tool_hint:
                parts.append(f"via {self.tool_hint}")
            return " ".join(parts)
        return self.description  # Fallback to free-form
```

**Backward compatible:** Old steps without structured fields still work via `description` fallback.

#### Task 2.2: Update StructuredPlanOutput for Structured Steps (S)

**What:** Update the Pydantic model that the LLM fills when creating plans.

**Where to modify:** `backend/app/domain/models/structured_outputs.py`

Add structured step description fields to the existing `StructuredPlanOutput` / `StepDescription`:
```python
class StepDescription(BaseModel):
    description: str  # Keep for backward compat
    action_verb: str = ""  # New: required action
    target_object: str = ""  # New: what to act on
    tool_hint: str | None = None  # New: suggested tool
    expected_output: str = ""  # New: what success looks like
```

#### Task 2.3: Update Planner Prompts and Merging Logic (M)

**What:** Update planner system prompt to request structured fields, and fix merging to preserve them.

**Where to modify:**
- `backend/app/domain/services/prompts/planner.py` — Update `PLANNER_SYSTEM_PROMPT` to instruct the LLM to fill structured fields
- `backend/app/domain/services/agents/planner.py`
  - `_step_from_description()` (line 152) — map structured fields from `StepDescription` to `Step`
  - `_consolidate_similar_steps()` (line 609) — when merging, combine `target_object` values instead of dropping them
  - `_normalize_plan_steps()` (line 648) — when merging overflow steps, create a combined `target_object` listing each original target, not a generic "Consolidate remaining..." label

**Test:**
- `backend/tests/domain/services/agents/test_planner_structured_steps.py`
- Verify: LLM output parsed into structured fields, merged steps preserve targets, display_label generates correctly

#### Task 2.4: Step Quality Validator (S)

**What:** Add a lightweight validator that checks step quality after plan creation.

**File:** `backend/app/domain/services/flows/step_quality_validator.py`

**Validation rules (deterministic, no LLM):**
- `action_verb` must not be empty or a banned generic verb (`"handle"`, `"do"`, `"process"`, `"finalize"`, `"consolidate"`)
- `target_object` must not be empty
- `target_object` should contain at least one locked entity from `RequestContract` (if applicable)
- Emit `step_name_quality_violations_total` Prometheus counter on failure

**Behavior when validation fails:**
- If `enable_structured_step_model` is `True`: log warning, attempt one repair pass (fill from `description` via regex), then proceed
- Never block plan execution — quality gate is advisory in initial rollout

**Test:**
- `backend/tests/domain/services/flows/test_step_quality_validator.py`

---

### Phase 3: Delivery Integrity v2

**Goal:** Extend the final output gate beyond security/compliance to include entity fidelity and semantic relevance, using the `RequestContract` from Phase 1.

#### Task 3.1: Entity Fidelity Checker (M)

**What:** Check that locked entities/versions from the `RequestContract` appear in the final output.

**File:** `backend/app/domain/services/agents/delivery_fidelity.py`

```python
class DeliveryFidelityChecker:
    """Validates final output against RequestContract."""

    def check_entity_fidelity(
        self,
        output: str,
        contract: RequestContract,
    ) -> FidelityResult:
        """Check that locked entities appear in output."""
        missing = []
        for entity in contract.locked_entities:
            if entity.lower() not in output.lower():
                missing.append(entity)
        for version in contract.locked_versions:
            if version not in output:
                missing.append(f"version {version}")

        return FidelityResult(
            passed=len(missing) == 0,
            missing_entities=missing,
            fidelity_score=1.0 - (len(missing) / max(len(contract.locked_entities) + len(contract.locked_versions), 1)),
        )
```

**Behavior by mode (controlled by `delivery_fidelity_mode`):**
- `shadow`: Log fidelity result + increment `entity_drift_detected_total` counter. Never block.
- `warn`: Log + emit a `WarningEvent` to the frontend. Deliver output anyway.
- `enforce`: If `fidelity_score < 0.8`, block output and emit `ErrorEvent`. Trigger one retry of summarization with explicit instruction to include missing entities.

#### Task 3.2: Integrate into PlanActFlow SUMMARIZING Phase (M)

**What:** Wire `DeliveryFidelityChecker` and enhanced `OutputGuardrails` into the SUMMARIZING phase.

**Where to modify:** `backend/app/domain/services/flows/plan_act.py` — SUMMARIZING phase (line ~2552)

**Pipeline order:**
1. `executor.summarize()` — generates report content
2. `OutputGuardrails.analyze()` — relevance + consistency (from Phase 0)
3. `DeliveryFidelityChecker.check_entity_fidelity()` — entity/version presence
4. `_run_compliance_gates()` — security/policy (existing)
5. If all pass → emit `ReportEvent`
6. If fidelity fails in enforce mode → retry summarization once with explicit entity list, then fail if still missing

**Test:**
- `backend/tests/domain/services/agents/test_delivery_fidelity.py`
- Cases: all entities present, one missing, all missing, version drift, numeric constraint missing

---

### Phase 4: Router + Search Fidelity Guardrails

**Goal:** Ensure entity fidelity is maintained when constructing search queries and LLM prompts during execution.

#### Task 4.1: Search Query Fidelity Check (S)

**What:** Before `web_search` or `browser` tool calls, verify that the search query/URL preserves locked entities.

**Where to modify:**
- `backend/app/domain/services/agents/execution.py` — before tool dispatch
- Only applies to search-related tools (`web_search`, `browser`)
- Does **NOT** apply to raw tool parameters like file paths, shell commands, etc.

**Check logic:**
```python
def check_search_fidelity(search_query: str, contract: RequestContract) -> bool:
    """Verify search query contains relevant locked entities."""
    if not contract.locked_entities:
        return True
    # At least one locked entity should appear in search query
    return any(
        entity.lower() in search_query.lower()
        for entity in contract.locked_entities
    )
```

**Behavior on failure:**
- One repair pass: prepend the most relevant locked entity to the search query
- If repair is not applicable (e.g., follow-up query that legitimately doesn't need the entity), skip

#### Task 4.2: LLM Prompt Context Injection (S)

**What:** When constructing LLM prompts for execution steps, include locked entities as explicit context.

**Where to modify:**
- `backend/app/domain/services/agents/execution.py` — prompt construction
- Append a system-level reminder: `"IMPORTANT: The user's request specifically mentions: {locked_entities}. Preserve these exact terms in your response."`

**Test:**
- `backend/tests/domain/services/agents/test_search_fidelity.py`
- Cases: entity in query (pass), entity missing (repair), no entities (skip)

---

### Phase 5: Contradiction / Bad-Logic Clarification

**Goal:** Detect contradictory or impossible user requests before planning, and ask for clarification.

**Priority:** Low — this is a nice-to-have. The existing `_check_consistency()` in guardrails (line 717) uses naive regex patterns (is/is not, can/cannot) that produce false positives on legitimate comparisons. This phase should replace it with something more useful or be deprioritized.

#### Task 5.1: Enhanced Contradiction Detection (M)

**What:** Replace the regex-based contradiction check with pattern-based detection of structurally contradictory requests.

**File:** `backend/app/domain/services/agents/guardrails.py` — replace `_check_consistency()` (line 717)

**Structural contradiction patterns:**
- Mutually exclusive constraints: "find X but not X", "compare A with A"
- Impossible numeric constraints: "top 0 results", "between 100 and 50"
- Self-referential loops: "summarize the summary of the summary"

**Behavior:** If detected at ingress (in `InputGuardrails`), emit a clarification prompt asking the user to resolve the contradiction. Log category for analytics.

**Test:**
- `backend/tests/domain/services/agents/test_contradiction_detection.py`

---

### Phase 6: Evaluation + Regression Suite (Continuous)

**Goal:** Maintain a regression test suite that validates all robustness properties. This phase starts during Phase 0 and grows with each subsequent phase.

#### Task 6.1: Entity Drift Regression Suite (S)

**File:** `backend/tests/evals/test_entity_drift_regression.py`

**Test cases:**
```python
# Must preserve exact entity
("What is Claude Sonnet 4.5?", ["Claude Sonnet 4.5"]),
("Compare GPT-4 and Claude Opus 4.6", ["GPT-4", "Claude Opus 4.6"]),
("Python 3.12 new features", ["Python 3.12"]),
# Must preserve version numbers
("FastAPI 0.115 migration guide", ["0.115"]),
# Must preserve numeric constraints
("Top 5 JavaScript frameworks", ["Top 5"]),
```

#### Task 6.2: Step Naming Quality Regression (S)

**File:** `backend/tests/evals/test_step_naming_regression.py`

**Test cases:**
- No step with `action_verb` in banned list passes validation
- Merged steps preserve at least one `target_object` from originals
- `display_label` is non-empty for all steps

#### Task 6.3: Delivery Fidelity Regression (S)

**File:** `backend/tests/evals/test_delivery_fidelity_regression.py`

**Test cases:**
- Output containing all locked entities → passes
- Output missing a locked entity → detected (shadow: logged, enforce: blocked)
- Version number drift (e.g., "4.5" → "5.0") → detected

#### Task 6.4: Rollout Strategy

**Stages:**
1. **Shadow mode** (default): All checks run, all results logged, nothing blocked. Monitor `entity_drift_detected_total` and `output_relevance_failures_total` in Grafana.
2. **Warn mode**: Enable `delivery_fidelity_mode: "warn"`. Frontend shows warnings but delivers output.
3. **Enforce mode**: Enable `delivery_fidelity_mode: "enforce"`. Outputs with entity drift or low relevance are blocked and retried.

**KPI gates for mode promotion:**
- Shadow → Warn: `entity_drift_detected_total` rate stabilizes, false positive rate < 5%
- Warn → Enforce: Zero user complaints about false blocks in warn mode over 1 week

---

## Scope: PlanActGraphFlow

The `PlanActGraphFlow` (`plan_act_graph.py:474`) is an alternative flow variant. Changes in this plan target `PlanActFlow` only. If `PlanActGraphFlow` is actively used, the same patterns should be ported in a follow-up plan after `PlanActFlow` is validated.

**Action:** Verify which flow is active via `Settings.flow_mode` before Phase 0 starts. If both are in use, scope increases by ~30%.

---

## Code Areas to Update

### New Files
| File | Phase | Purpose |
|------|-------|---------|
| `backend/app/domain/models/request_contract.py` | 1 | RequestContract domain model |
| `backend/app/domain/services/flows/request_contract_extractor.py` | 1 | Entity extraction logic |
| `backend/app/domain/services/flows/step_quality_validator.py` | 2 | Step naming validation |
| `backend/app/domain/services/agents/delivery_fidelity.py` | 3 | Entity fidelity checker |

### Modified Files
| File | Phase | Change |
|------|-------|--------|
| `backend/app/core/config.py` | 0 | Feature flags |
| `backend/app/infrastructure/observability/prometheus_metrics.py` | 0 | Robustness metrics |
| `backend/app/domain/services/flows/plan_act.py` | 0,1,3 | OutputGuardrails integration, RequestContract, DeliveryFidelity |
| `backend/app/domain/services/flows/enhanced_prompt_quick_validator.py` | 1 | Skip correction for locked entities |
| `backend/app/domain/models/plan.py` | 2 | Structured Step fields |
| `backend/app/domain/models/structured_outputs.py` | 2 | Structured StepDescription |
| `backend/app/domain/services/agents/planner.py` | 2 | Structured step creation, merge fixes |
| `backend/app/domain/services/prompts/planner.py` | 2 | Prompt updates for structured output |
| `backend/app/domain/services/agents/execution.py` | 4 | Search fidelity, entity context injection |
| `backend/app/domain/services/agents/guardrails.py` | 5 | Enhanced contradiction detection |

### Test Files
| File | Phase |
|------|-------|
| `backend/tests/domain/services/flows/test_plan_act_output_guardrails.py` | 0 |
| `backend/tests/infrastructure/observability/test_robustness_metrics.py` | 0 |
| `backend/tests/domain/services/flows/test_request_contract_extractor.py` | 1 |
| `backend/tests/domain/services/flows/test_request_contract_integration.py` | 1 |
| `backend/tests/domain/services/agents/test_planner_structured_steps.py` | 2 |
| `backend/tests/domain/services/flows/test_step_quality_validator.py` | 2 |
| `backend/tests/domain/services/agents/test_delivery_fidelity.py` | 3 |
| `backend/tests/domain/services/agents/test_search_fidelity.py` | 4 |
| `backend/tests/domain/services/agents/test_contradiction_detection.py` | 5 |
| `backend/tests/evals/test_entity_drift_regression.py` | 6 |
| `backend/tests/evals/test_step_naming_regression.py` | 6 |
| `backend/tests/evals/test_delivery_fidelity_regression.py` | 6 |

---

## Acceptance Criteria

1. **Entity/version drift** = `0%` in regression tests.
2. **`irrelevant_answer_rate`** < `2%` in eval set.
3. **`vague_step_name_rate`** < `1%` of generated plans (measured by `step_name_quality_violations_total`).
4. **Additional guardrail latency** < `150ms` P95 over Phase 0 baseline.
5. **No release** without passing delivery-fidelity gate in enforce mode.
6. **All feature flags** independently toggleable — disabling one component must not break others.
7. **OutputGuardrails** wired into PlanActFlow (Phase 0 prerequisite for all subsequent phases).

---

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|:---:|:---:|---|
| Over-strict entity fidelity blocks valid responses (e.g., paraphrased entity names) | Medium | High | Shadow mode first; tune `fidelity_score` threshold (start at 0.8); allow partial matches |
| Regex-based entity extraction misses complex entities | Medium | Medium | Hybrid approach: regex for known patterns, quoted-string/capitalization heuristics for unknown; log extraction confidence for tuning |
| Structured step fields not consistently filled by LLM | High | Medium | Fallback to `description` field (backward compat); repair pass fills from description; advisory-only in initial rollout |
| Fast-path latency increase from entity extraction | Low | Low | Extraction is regex-only (< 5ms); short-circuit for queries with no extractable entities |
| `PlanActGraphFlow` diverges from hardened `PlanActFlow` | Medium | Medium | Verify active flow variant before starting; port changes in follow-up if needed |
| False positives in contradiction detection | High | Low | Phase 5 is lowest priority; structural patterns only (not semantic); advisory-only |

---

## Monitoring & Observability

All metrics are exposed via the existing Prometheus/Grafana/Loki stack.

### Prometheus Metrics (Phase 0)
```
pythinker_entity_drift_detected_total{phase="summarize|execute|route"}
pythinker_output_relevance_failures_total{severity="low|medium|high"}
pythinker_step_name_quality_violations_total{violation="empty_verb|empty_target|banned_verb"}
pythinker_guardrail_tripwire_total{guardrail="fidelity|relevance|consistency|contradiction"}
pythinker_delivery_fidelity_blocks_total{mode="shadow|warn|enforce"}
pythinker_guardrail_latency_seconds{phase="extract|validate|fidelity|relevance"}
pythinker_output_relevance_score{bucket="0.0-0.3|0.3-0.6|0.6-1.0"}
```

### Grafana Dashboard
- **Row 1:** Entity drift rate over time (counter rate)
- **Row 2:** Output relevance score distribution (histogram)
- **Row 3:** Guardrail latency P50/P95/P99 (histogram)
- **Row 4:** Step naming quality violations (counter rate)
- **Row 5:** Delivery fidelity blocks by mode (counter rate)

### Loki Log Labels
```
{container_name="pythinker-backend-1"} |= "entity_drift" | json | level="warning"
{container_name="pythinker-backend-1"} |= "fidelity_check" | json | result="fail"
{container_name="pythinker-backend-1"} |= "step_quality" | json | violation!=""
```

---

## Context7 Best-Practice References

### LangGraph — Applied Patterns
- **Conditional routing with state**: Phase 4 search fidelity check mirrors LangGraph conditional edges — route to repair node if fidelity fails, otherwise proceed
- **Checkpointing**: RequestContract acts as a checkpoint artifact that persists across flow stages (similar to LangGraph state snapshots)
- Ref: https://docs.langchain.com/oss/python/langgraph/workflows-agents

### OpenAI Agents SDK — Applied Patterns
- **Input guardrails → tripwire model**: Phase 0 wiring follows the SDK pattern of guardrails that run in parallel with agent execution and can halt the pipeline
- **Structured outputs**: Phase 2 structured Step model follows the SDK pattern of using Pydantic models as tool output schemas
- Ref: https://github.com/openai/openai-agents-python/blob/main/docs/guardrails.md

---

## Immediate Next Steps

1. **Verify active flow variant:** Check `Settings.flow_mode` to confirm `PlanActFlow` is the primary flow.
2. **Start Phase 0:** Wire `OutputGuardrails` into `PlanActFlow` SUMMARIZING phase + add Prometheus metrics.
3. **Start Phase 1 in parallel:** Define `RequestContract` model + implement regex-based entity extraction.
4. **Add first regression test:** Entity drift test for `"Claude Sonnet 4.5"` preservation.
