# Adaptive Verbosity + Clarification Gate Design

## Goal
Build a general-purpose advanced agent that:
- stays concise by default,
- asks the user for clarification when task intent is unclear,
- preserves output quality (no drop in execution rigor).

## Constraints
- Do not reduce core execution quality (planning/tool use/verification quality floor must remain).
- Improve perceived responsiveness during long runs.
- Keep compatibility with existing PlanAct flow and current SSE frontend.

## Option Analysis

### Option A: Prompt-only conciseness rules
- Change system prompts to request shorter answers.
- Pros: fastest to implement.
- Cons: unstable, model-dependent, can shorten important details and degrade quality.

### Option B: Post-hoc truncation
- Keep current execution, then trim final output by token/length limits.
- Pros: simple.
- Cons: high risk of deleting required info/caveats/artifacts.

### Option C (Recommended): Policy engine + quality floor
- Add a deterministic `ResponsePolicyEngine` that decides verbosity from task assessment.
- Keep execution quality checks unchanged or stronger.
- Apply constrained compression only after quality checks pass.
- Pros: predictable, testable, quality-safe, adaptive.
- Cons: moderate implementation effort.

Recommendation: Option C.

## Architecture

### New Domain Service
Create `backend/app/domain/services/agents/response_policy.py`:
- `TaskAssessment`
  - `complexity_score: float`
  - `risk_score: float`
  - `ambiguity_score: float`
  - `evidence_need_score: float`
  - `confidence_score: float`
  - `needs_clarification: bool`
  - `clarification_questions: list[str]`
- `VerbosityMode = concise | standard | detailed`
- `ResponsePolicy`
  - `mode: VerbosityMode`
  - `force_detailed_reason: str | None`
  - `min_required_sections: list[str]`
  - `allow_compression: bool`

### Inputs for Assessment
- `ComplexityAssessor` (already exists).
- `InputGuardrails` ambiguity signals (already exists, currently underused in PlanAct).
- Lightweight risk heuristics:
  - high risk keywords (`production`, `security`, `payment`, `migration`, `legal`, `medical`, `financial`),
  - tool intent (destructive operations),
  - verification-critical tasks (comparison/benchmark/current facts).
- Evidence need heuristics:
  - requests with `latest`, `compare`, `source`, `proof`, `today`, numbers/dates.

### Decision Rules
- `needs_clarification = ambiguity_score >= 0.6 or confidence_score < 0.65`
- Force `detailed` when `risk_score >= 0.7`.
- `concise` only when:
  - low risk,
  - low ambiguity,
  - quality floor checks pass.
- `standard` is default fallback.

## Clarification Flow

### PlanAct Integration
In `backend/app/domain/services/flows/plan_act.py` at the start of `run()`:
1. Evaluate task assessment.
2. If `needs_clarification`:
   - emit a concise clarification question,
   - call `message_ask_user` via tool path (preferred) or emit `WaitEvent` with a blocking question event,
   - exit current run cleanly.
3. `AgentTaskRunner` already maps `WaitEvent` to `SessionStatus.WAITING`.

This gives explicit steering before expensive execution and avoids low-quality guesses.

### Eventing/UI
Reuse existing `message` + `wait` events first (no protocol break).
Optional later: add dedicated `confidence` event to expose why clarification was requested.

## Quality-Preserving Short Answers

### Keep Quality Floor
Do not skip current quality path:
- planning validation,
- execution,
- CoVe,
- critic/revision loop.

### Add Compression Stage After Quality
In `ExecutionAgent.summarize()`:
1. Generate full-quality answer.
2. Run `OutputCoverageValidator`:
   - checks required deliverables present,
   - checks requested constraints addressed,
   - checks caveats/sources preserved when needed.
3. If policy allows, run `ResponseCompressor` to target `concise` format.
4. If coverage drops, reject compressed output and return `standard` output.

### Concise Output Contract
Even in concise mode, always include:
- final result,
- artifact/file references,
- key caveat/limitation (if any),
- actionable next step when appropriate.

## API and Settings Changes

### Backend settings schema
Extend settings endpoints:
- `response_verbosity_preference: adaptive | concise | detailed` (default `adaptive`)
- `clarification_policy: auto | always | never` (default `auto`)
- `quality_floor_enforced: bool` (default `true`)

Files:
- `backend/app/interfaces/schemas/settings.py`
- `backend/app/interfaces/api/settings_routes.py`

### Frontend settings schema
Extend:
- `frontend/src/api/settings.ts`
- settings UI controls (verbosity + clarification policy).

## Observability and SLOs
Add metrics:
- `clarification_requested_total`
- `clarification_resolved_total`
- `clarification_wait_seconds`
- `response_policy_mode_total{mode}`
- `compression_rejected_total` (quality floor protection)
- `final_response_tokens{mode}`
- `user_stop_rate_before_done`

Targets:
- reduce manual stop rate on ambiguous tasks,
- reduce median response length without increasing critic failure rate.

## Rollout Plan

### Phase 1 (safe)
- Implement policy engine + logging only (`feature_adaptive_verbosity_shadow=true`).
- No behavior changes; capture proposed mode and clarification decisions.

### Phase 2
- Enable clarification gate for high ambiguity only.
- Keep output mode `standard`.

### Phase 3
- Enable adaptive verbosity + compression with quality floor enforcement.

### Phase 4
- Add dedicated confidence/clarification UI signals if needed.

## Test Plan

### Unit
- `response_policy` scoring and thresholds.
- `OutputCoverageValidator` rejection cases.

### Integration
- ambiguous input triggers `wait` and `SessionStatus.WAITING`.
- resume after user clarification continues execution.
- concise mode never drops required attachments/constraints.

### Regression
- high-risk tasks still produce detailed outputs.
- critic/CoVe quality outcomes unchanged or improved.

