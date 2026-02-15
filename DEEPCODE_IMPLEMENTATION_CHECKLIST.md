# DeepCode Integration Checklist v2

**Last Updated:** 2026-02-15 | **Status:** Ready for Implementation

> **Note:** v1 proposed 33 files by rebuilding existing infrastructure. v2 targets only genuine gaps: **7 new files + 4 modifications.**

---

## Quick Links

- **Full Plan:** [docs/architecture/DEEPCODE_INTEGRATION_PLAN.md](docs/architecture/DEEPCODE_INTEGRATION_PLAN.md) (v2)
- **Summary:** [docs/architecture/DEEPCODE_INTEGRATION_SUMMARY.md](docs/architecture/DEEPCODE_INTEGRATION_SUMMARY.md)

---

## Phase 1: Adaptive Model Selection (Week 1 — P0) ✅ COMPLETED

### Config Changes ✅
- [x] Add `adaptive_model_selection_enabled: bool = False` to `Settings`
- [x] Add `fast_model: str = "claude-haiku-4-5"` to `Settings`
- [x] Add `balanced_model: str = ""` to `Settings`
- [x] Add `powerful_model: str = "claude-sonnet-4-5"` to `Settings`
- [x] Add `effective_balanced_model` as `@computed_field`

### ComplexityAssessor Enhancement ✅
- [x] Add `ModelTier` enum (`FAST`, `BALANCED`, `POWERFUL`)
- [x] Add `StepModelRecommendation` model with `@computed_field`
- [x] Add `recommend_model_tier()` method

### ExecutionAgent Enhancement ✅
- [x] Add `_select_model_for_step()` method
- [x] Use model override in LLM call when available
- [x] Add Prometheus counter `pythinker_model_tier_selections_total`

### LLM Protocol Enhancement ✅
- [x] Add `model` parameter to `LLM.ask()` protocol
- [x] Add `model` parameter to `LLM.ask_stream()` protocol
- [x] Add `model` parameter to `LLM.ask_structured()` protocol
- [x] Update `OpenAILLM` to use model override in all three methods

### BaseAgent Enhancement ✅
- [x] Add `_step_model_override` attribute to BaseAgent
- [x] Pass model override to `llm.ask()` in execution loop
- [x] Reset model override in ExecutionAgent after step completion

### Frontend
- [ ] Create `frontend/src/composables/useModelTier.ts` (optional)
- [ ] Display model tier badge in step indicator (optional)

### Tests ✅
- [x] `backend/tests/domain/services/agents/test_adaptive_model.py`
  - [x] Test fast tier selection for summaries
  - [x] Test powerful tier for architecture
  - [x] Test default balanced fallback
  - [x] Test feature flag disabled returns None
  - [x] Test Prometheus metrics incremented

### Phase 1 Validation
- [ ] `ruff check . && ruff format --check .` (pending environment setup)
- [ ] `pytest tests/ -v --tb=short` (pending environment setup)
- [ ] `cd frontend && bun run lint && bun run type-check` (N/A for backend-only changes)

---

## Phase 2: Tool Efficiency + Truncation Detection (Week 2 — P1)

### Tool Efficiency Monitor
- [ ] Create `backend/app/domain/services/agents/tool_efficiency_monitor.py`
  - [ ] `EfficiencySignal` dataclass
  - [ ] `ToolEfficiencyMonitor` class
  - [ ] `READ_TOOLS` and `ACTION_TOOLS` classification sets
  - [ ] `record()` method
  - [ ] `check_efficiency()` method
  - [ ] `reset()` method
- [ ] Integrate into `BaseAgent` tool execution loop
  - [ ] Record each tool call
  - [ ] Inject nudge message when imbalanced
- [ ] Add Prometheus counter `pythinker_tool_efficiency_nudges_total`

### Truncation Detector
- [ ] Create `backend/app/domain/services/agents/truncation_detector.py`
  - [ ] `TruncationAssessment` model with `@model_validator`
  - [ ] `TruncationDetector` class
  - [ ] Last-line analysis
  - [ ] Unclosed code block detection
  - [ ] Regex pattern matching
  - [ ] Markdown structure check
- [ ] Integrate into `ExecutionAgent` after LLM response
  - [ ] Log warning on detection
  - [ ] Optional: retry with continuation prompt
- [ ] Add Prometheus counter `pythinker_output_truncations_total`

### Tests
- [ ] `backend/tests/domain/services/agents/test_tool_efficiency_monitor.py`
  - [ ] Test no nudge within threshold
  - [ ] Test nudge after excessive reads
  - [ ] Test action resets streak
  - [ ] Test reset clears state
- [ ] `backend/tests/domain/services/agents/test_truncation_detector.py`
  - [ ] Test complete output not flagged
  - [ ] Test unclosed code block detected
  - [ ] Test mid-sentence truncation
  - [ ] Test proper ending not flagged
  - [ ] Test Pydantic model_validator auto-suggestion

### Phase 2 Validation
- [ ] `ruff check . && ruff format --check .`
- [ ] `pytest tests/ -v --tb=short`

---

## Phase 3: Document Segmentation + File Tracker (Week 3 — P2)

### Document Segmenter
- [ ] Create `backend/app/domain/services/document/__init__.py`
- [ ] Create `backend/app/domain/services/document/segmenter.py`
  - [ ] `DocumentSegment` dataclass
  - [ ] `DocumentSegmenter` class (uses existing `TokenManager`)
  - [ ] Section-boundary-aware splitting
  - [ ] Configurable max tokens per segment

### Implementation Tracker
- [ ] Create `backend/app/domain/services/agents/implementation_tracker.py`
  - [ ] `FileStatus` enum
  - [ ] `TrackedFile` dataclass
  - [ ] `ImplementationTracker` class
  - [ ] `register_files()`, `mark_started()`, `mark_completed()`
  - [ ] `progress` property (0.0-1.0)

### Tests
- [ ] `backend/tests/domain/services/document/test_segmenter.py`
- [ ] `backend/tests/domain/services/agents/test_implementation_tracker.py`

### Phase 3 Validation
- [ ] `ruff check . && ruff format --check .`
- [ ] `pytest tests/ -v --tb=short`
- [ ] No regressions in full test suite

---

## Success Criteria

- [ ] **Cost:** 20%+ reduction on mixed-complexity sessions (model selection)
- [ ] **Quality:** 90%+ truncated outputs detected (truncation detector)
- [ ] **Efficiency:** 50%+ reduction in analysis paralysis patterns (efficiency monitor)
- [ ] **Coverage:** 95%+ on all new code
- [ ] **Regressions:** Zero — all existing tests continue passing

---

## Commands

```bash
conda activate pythinker && cd backend

# Lint
ruff check . && ruff format --check .

# Test new files
pytest tests/domain/services/agents/test_tool_efficiency_monitor.py -v
pytest tests/domain/services/agents/test_truncation_detector.py -v
pytest tests/domain/services/agents/test_adaptive_model.py -v
pytest tests/domain/services/agents/test_implementation_tracker.py -v
pytest tests/domain/services/document/test_segmenter.py -v

# Coverage
pytest tests/domain/services/ --cov=app.domain.services -k "efficiency or truncation or adaptive or tracker or segmenter"

# Frontend
cd frontend && bun run lint && bun run type-check
```
