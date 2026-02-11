# Robust Typo Correction Enhancement Design

**Date**: 2026-02-11
**Priority**: Medium
**Component**: `PromptQuickValidator`
**Status**: In Progress (Plan Updated)

---

## Current Implementation Analysis

### Strengths
- Fast and deterministic
- Conservative fuzzy matching (`difflib` cutoff `0.9`)
- Safe target list reduces over-correction risk
- Regex-based exact replacements for known high-frequency typos

### Limitations
- Hard-coded typo dictionary in service code
- No confidence scoring exposed to downstream decisions
- No correction telemetry pipeline
- No user feedback loop
- No pluggable correction backend (RapidFuzz/SymSpell)

---

## Updated Recommendation

### Decision
Adopt a **hybrid, layered approach**:
1. Keep `PromptQuickValidator` as the default low-latency guardrail
2. Add optional confidence scoring with `RapidFuzz`
3. Add optional `SymSpell` backend in infrastructure layer for advanced correction
4. Add correction analytics via infrastructure events/metrics (not domain file writes)

### Why this path
- Preserves current speed and deterministic behavior
- Adds measurable quality controls before risky auto-correction
- Follows repository dependency direction (Domain -> Application -> Infrastructure -> Interfaces)
- Enables gradual rollout with feature flags and A/B evaluation

---

## Architecture and Layering

### Domain Layer
- Keep typo normalization policy and safe target constraints in domain service
- Do not add direct file/database persistence to domain objects
- Expose correction decision as value data (original token, candidate token, confidence, accepted)

### Application Layer
- Orchestrate validator flow
- Apply feature flags and thresholds
- Emit correction events to analytics interface

### Infrastructure Layer
- Implement optional providers:
  - `RapidFuzzScorer` for confidence-scored candidate ranking
  - `SymSpellProvider` for dictionary-backed correction
- Handle dictionary loading, caching, and provider initialization
- Handle persistence/metrics transport

### Interfaces Layer
- API/session boundaries can pass user feedback events (accept/reject correction)
- No business correction logic in routes/controllers

---

## Implementation Plan

### Phase 1: Stabilize Current Validator (Immediate)
**Status**: Not Started

1. Add explicit technical term protection set
2. Add confidence-returning correction path while keeping existing behavior default
3. Add correction decision telemetry hooks (in-memory event emission only)
4. Expand typo replacements only for validated high-frequency errors
5. Update and harden unit tests for false-positive protection

**Exit criteria**
- No regression in existing validator tests
- Technical terms remain unchanged in protected cases
- Confidence score available for each correction decision

### Phase 2: Confidence-Scored Matching via RapidFuzz (Next)
**Status**: Not Started

1. Add optional RapidFuzz scorer in infrastructure
2. Use `extractOne` + `score_cutoff` for deterministic acceptance/rejection
3. Keep domain safe-target gating as final approval step
4. Add threshold configuration and benchmark tests

**Exit criteria**
- Measurable reduction in false positives vs baseline
- P95 latency impact remains within defined budget

### Phase 3: Optional SymSpell Backend (Future)
**Status**: Not Started

1. Add `SymSpellProvider` behind feature flag
2. Load unigram frequency dictionary for single-token correction
3. Load bigram dictionary when `lookup_compound` is enabled
4. Add project/domain dictionary entries (`pythinker`, `qdrant`, etc.) at startup
5. Support casing transfer where applicable

**Exit criteria**
- SymSpell path is fully optional and disabled by default
- Startup/load failures degrade gracefully to base validator

### Phase 4: Feedback + Analytics Loop (Future)
**Status**: Not Started

1. Capture user override events at interface boundary
2. Store feedback in infrastructure persistence (not domain filesystem writes)
3. Build correction quality metrics dashboard
4. Run A/B evaluation across correction modes

**Exit criteria**
- Accepted/rejected correction metrics available per mode
- Data-driven threshold tuning workflow documented

---

## Configuration Plan (Pydantic Settings v2 Style)

Use grouped/nested settings instead of many flat flags.

```python
# backend/app/core/config.py (proposed shape)
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict


class TypoCorrectionSettings(BaseModel):
    enabled: bool = True
    confidence_threshold: float = 0.90
    max_suggestions: int = 1
    log_events: bool = True


class RapidFuzzSettings(BaseModel):
    enabled: bool = False
    score_cutoff: float = 90.0


class SymSpellSettings(BaseModel):
    enabled: bool = False
    dictionary_path: str = "data/frequency_dictionary_en_82_765.txt"
    bigram_path: str = "data/frequency_bigramdictionary_en_243_342.txt"
    max_edit_distance: int = 2
    prefix_length: int = 7


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_nested_delimiter="__")

    typo_correction: TypoCorrectionSettings = TypoCorrectionSettings()
    rapidfuzz: RapidFuzzSettings = RapidFuzzSettings()
    symspell: SymSpellSettings = SymSpellSettings()
```

Example env vars:
- `TYPO_CORRECTION__ENABLED=true`
- `RAPIDFUZZ__ENABLED=false`
- `SYMSPELL__ENABLED=false`

---

## Testing and Validation Plan

### Unit tests
- Existing behavior compatibility tests for `PromptQuickValidator`
- Technical term protection tests (no over-correction)
- Confidence threshold tests (below-threshold returns original)
- Casing preservation tests

### Integration tests
- RapidFuzz-enabled path with deterministic cutoff behavior
- SymSpell-enabled path with dictionary load success/fallback behavior

### Performance tests
- Use percentile-based benchmarks (`P50/P95`) over repeated runs
- Avoid single-call wall-clock assertions that are CI-noise prone

### Quality metrics
- Correction acceptance rate
- False positive rate on protected technical vocabulary
- Latency delta per correction mode

---

## Success Metrics

1. Correction acceptance rate >= 95% for applied corrections
2. False positive rate <= 2% on protected technical terms
3. P95 added latency within target budget
4. Measurable reduction in manual typo correction occurrences
5. Clear rollout/fallback behavior for each correction backend

---

## Open Decisions

1. Should correction remain spelling-only in v1?
- Recommendation: Yes. Keep grammar correction out of scope initially.

2. Should user feedback be global or per-user?
- Recommendation: Start global with auditable event schema, then extend per-user if needed.

3. Should SymSpell be enabled by default?
- Recommendation: No. Ship behind flag and enable after benchmark + quality gates.

---

## Context7-Validated References

- SymSpellPy dictionary loading and API usage:
  - https://github.com/mammothb/symspellpy/blob/master/docs/examples/dictionary.rst
  - https://github.com/mammothb/symspellpy/blob/master/docs/examples/lookup.rst
  - https://github.com/mammothb/symspellpy/blob/master/docs/examples/lookup_compound.rst
- RapidFuzz matching patterns (`extractOne`, `score_cutoff`):
  - https://github.com/rapidfuzz/rapidfuzz/blob/main/README.md
- Pydantic Settings v2 nested settings and env parsing:
  - https://github.com/pydantic/pydantic-settings/blob/main/docs/index.md
