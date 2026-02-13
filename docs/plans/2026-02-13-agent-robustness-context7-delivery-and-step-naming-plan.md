# Agent Robustness Plan: Context7 Best Practices + Step Naming Quality

**Date:** 2026-02-13
**Status:** Proposed
**Scope:** Improve agent reliability, relevance, and output correctness by hardening request fidelity, step/task naming, routing, guardrails, and delivery validation.

---

## Objectives

1. Ensure agent responses stay faithful to user request entities/versions (e.g., `Claude Sonnet 4.5` must never become `Sonnet 5`).
2. Reduce unrelated/off-topic responses by adding deterministic pre-execution and pre-delivery checks.
3. Improve plan-step/task naming quality so routing and execution remain precise.
4. Add measurable quality gates and tracing for continuous tuning.

---

## Why This Plan

Current architecture already includes strong components (`PromptQuickValidator`, `FastPathRouter`, `OutputCoverageValidator`, delivery integrity gate), but behavior can still drift when:

- Prompt normalization changes semantics instead of formatting.
- Fast-path classification takes shortcuts without strict query fidelity checks.
- Planner step names become generic/merged, reducing downstream routing precision.
- Final output checks are mostly coverage/format based, not strict entity fidelity based.

---

## Phase Plan and Status

| Phase | Status | Duration | Primary Outcome |
|---|---|---:|---|
| 0. Baseline + Observability | Not Started | 1-2 days | Drift/relevance baseline metrics and trace labels |
| 1. Request Contract + Locked Terms | Not Started | 2-3 days | Immutable contract extracted at ingress |
| 2. Naming Quality Gate for Steps/Tasks | Not Started | 2-3 days | Plan steps become explicit, testable, and route-safe |
| 3. Router + Tool Fidelity Guardrails | Not Started | 2-3 days | Query/entity fidelity enforced before tool calls |
| 4. Delivery Integrity v2 | Not Started | 3-4 days | Final response blocked if entity mismatch or low relevance |
| 5. Contradiction / Bad-Logic Clarification | Not Started | 2 days | Contradictory prompts trigger clarification path |
| 6. Evaluation + Rollout | Not Started | 2-3 days | Shadow -> enforce rollout with KPI gates |

---

## Detailed Workstreams

### Phase 0: Baseline + Observability

- Add metrics:
  - `entity_drift_rate`
  - `irrelevant_answer_rate`
  - `step_name_quality_score`
  - `guardrail_tripwire_count`
- Add trace attributes for each stage:
  - `normalize`, `classify`, `plan`, `execute`, `summarize`, `delivery_gate`.
- Run baseline over representative prompts (including model-version queries).

### Phase 1: Request Contract + Locked Terms

- Introduce a `RequestContract` object at ingress in `PlanActFlow`.
- Contract fields:
  - `intent`, `action_type`, `exact_query`
  - `locked_entities`, `locked_versions`, `numeric_constraints`
  - `must_not_change_tokens`
- Update prompt quick validation to allow typo cleanup but forbid semantic mutation for locked terms.

### Phase 2: Naming Quality Gate for Steps/Tasks

- Add a `StepNamingPolicy` checker in planner flow.
- Required step pattern:
  - `Action Verb + Object + Tool (if needed) + Expected Output`
- Reject/repair generic step labels:
  - `consolidate`, `handle`, `do work`, `finalize` without explicit object/outcome.
- When step merging occurs, preserve explicit task-level metadata and enforce renamed, concrete final step labels.

### Phase 3: Router + Tool Fidelity Guardrails

- In fast path and full path:
  - if `locked_entities/versions` exist, enforce strict query fidelity.
- Add pre-tool-call guardrail:
  - tool args must include required locked terms when relevant.
- If fidelity fails:
  - one deterministic repair pass; then clarification prompt.

### Phase 4: Delivery Integrity v2

- Extend final output gate beyond coverage:
  - strict entity/version fidelity
  - semantic relevance threshold to user request
  - contradiction check against request contract
- Block final output if fidelity/relevance fails (fail-closed behavior in strict mode).
- Keep deterministic fallback only for formatting misses, not semantic misses.

### Phase 5: Contradiction / Bad-Logic Clarification

- Enhance guardrails to detect contradictory or impossible user logic.
- If detected:
  - ask concise clarification before plan execution.
- Log category and resolution path for analytics.

### Phase 6: Evaluation + Rollout

- Add regression suite for:
  - entity/version preservation (`Sonnet 4.5`, `Opus 4.6`, etc.)
  - unrelated response rejection
  - naming quality enforcement
- Rollout strategy:
  - shadow mode -> partial enforcement -> full enforcement.

---

## Code Areas to Update

- `backend/app/domain/services/flows/plan_act.py`
- `backend/app/domain/services/flows/enhanced_prompt_quick_validator.py`
- `backend/app/domain/services/flows/fast_path.py`
- `backend/app/domain/services/agents/planner.py`
- `backend/app/domain/services/agents/output_coverage_validator.py`
- `backend/app/domain/services/agents/guardrails.py`
- `backend/app/domain/services/agents/execution.py`
- `backend/tests/...` (new and updated tests for fidelity, relevance, naming quality)

---

## Acceptance Criteria

1. `entity/version drift` = `0%` in regression tests.
2. `irrelevant_answer_rate` < `2%` in eval set.
3. `vague_step_name_rate` < `1%` of generated plans.
4. Additional guardrail latency < `150ms` P95.
5. No release without passing delivery-fidelity gate in enforce mode.

---

## Risks and Mitigations

- Risk: Over-strict gates may block valid responses.
  - Mitigation: staged rollout with shadow metrics and threshold tuning.
- Risk: Planner flexibility reduced by naming constraints.
  - Mitigation: allow controlled templates, but enforce explicit object/outcome fields.
- Risk: Fast-path latency increase.
  - Mitigation: short-circuit deterministic checks; bypass heavy validation for low-risk prompts.

---

## Context7 Best-Practice References

### LangGraph (stateful workflow design, conditional routing, checkpointing, interrupts)
- https://docs.langchain.com/oss/python/langgraph/workflows-agents
- https://docs.langchain.com/oss/python/langgraph/interrupts
- https://docs.langchain.com/oss/python/langgraph/functional-api

### OpenAI Agents SDK (guardrails, structured outputs, tool constraints, tracing)
- https://github.com/openai/openai-agents-python/blob/main/docs/guardrails.md
- https://github.com/openai/openai-agents-python/blob/main/docs/agents.md
- https://github.com/openai/openai-agents-python/blob/main/docs/tools.md
- https://github.com/openai/openai-agents-python/blob/main/docs/quickstart.md

---

## Immediate Next Step

Start with Phases 1 and 2 together:
- lock request entities/versions at ingress,
- enforce step/task naming quality before execution,
- add regression test for `Claude Sonnet 4.5` drift scenario.
