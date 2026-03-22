# LettuceDetect Removal — LLM-as-Judge Grounding Verification

**Date:** 2026-03-13
**Status:** Approved
**Goal:** Remove PyTorch, sentence-transformers, and LettuceDetect from the backend image. Replace with LLM-based grounding verification (~3.5 GB image reduction, zero GPU/CUDA dependency).

---

## Section 1: Scope of Removal

### Dependencies removed from `requirements.txt`

| Package | Size | Current use |
|---------|------|-------------|
| `torch>=2.2.0` | ~2.5 GB | LettuceDetect + SelfHostedReranker |
| `sentence-transformers>=3.0.0` | ~800 MB | SelfHostedReranker (CrossEncoder) |
| `lettucedetect>=0.1.0` | ~50 MB | Hallucination detection |

### Files deleted

| File | Reason |
|------|--------|
| `backend/app/domain/services/agents/lettuce_verifier.py` | Entire LettuceDetect wrapper |
| `tests/domain/services/test_lettuce_verifier.py` | Tests for deleted file |

### Files modified

| File | Change |
|------|--------|
| `backend/requirements.txt` | Remove 3 deps |
| `backend/app/core/config_features.py` | Rename `feature_lettuce_verification` to `feature_hallucination_verification`, delete `lettuce_model_name`, `lettuce_eviction_ttl` |
| `backend/app/domain/services/retrieval/reranker.py` | Delete `SelfHostedReranker` class |
| `backend/app/domain/services/memory_service.py` | Default to `JinaReranker` |

---

## Section 2: Replacement — LLM Grounding Verifier

### Architecture

```
output_verifier.py (unchanged orchestrator)
    |
    v
llm_grounding_verifier.py (NEW - replaces lettuce_verifier.py)
    |
    v
existing LLM provider (Kimi / OpenAI-compatible via universal_llm.py)
```

### Interface (same as LettuceDetect)

```python
verify(response_text: str, source_context: str) -> VerificationResult
```

Returns `VerificationResult` with:
- `hallucination_score: float` (0.0-1.0) — ratio of unsupported claims
- `flagged_claims: list[FlaggedClaim]` — per-claim verdicts
- `skipped: bool` — True if verification failed gracefully

### Design decisions

1. **Same interface** — `output_verifier.py` and `execution.py` unchanged
2. **Structured prompt** — LLM extracts claims, checks each against source context, returns JSON with per-claim verdicts (supported/unsupported/unverifiable)
3. **FAST_MODEL tier** — Classification task, not generation. Routes through `model_router.py` with `ComplexityTier.FAST`
4. **Singleton, no warm-up** — `get_llm_grounding_verifier()` factory. Instant (no model loading)
5. **Graceful degradation** — LLM failure returns `VerificationResult(hallucination_score=0.0, skipped=True)`

### Scoring

```
hallucination_score = unsupported_claims / total_claims
```

Claim-level binary verdicts instead of token-level probabilities. Coarser but more interpretable, avoids false-positive problem where LettuceDetect flagged stylistic paraphrasing.

### New file structure

```
backend/app/domain/services/agents/llm_grounding_verifier.py
    LLMGroundingVerifier
        verify(response_text, source_context) -> VerificationResult
        _build_verification_prompt(response, context) -> list[dict]
        _parse_verdict(llm_response) -> VerificationResult
    FlaggedClaim (dataclass: claim_text, verdict, source_snippet)
    VerificationResult (dataclass: hallucination_score, flagged_claims, skipped)
    get_llm_grounding_verifier() -> LLMGroundingVerifier
```

---

## Section 3: Memory Reranking Migration

### Current state

- `SelfHostedReranker` (CrossEncoder) requires torch + sentence-transformers
- `JinaReranker` (API-based) already fully implemented at `backend/app/infrastructure/external/search/jina_reranker.py`
- Only caller: `memory_service.py` lines 590-618

### Migration

| Action | Detail |
|--------|--------|
| Delete `SelfHostedReranker` from `reranker.py` | Only class needing torch |
| Keep `JinaReranker` as primary | Already works, no ML deps |
| Keep `Reranker` protocol | Future-proof |
| Update `memory_service.py` | Default to `JinaReranker` |
| New config: `reranker_provider` | `"jina"` (default) or `"none"` |

### Trade-off

API call per rerank (~50ms) vs local model (0ms but 3.5GB image + 1.5GB GPU RAM). Reranking is infrequent (memory retrieval only). Jina free tier handles volume.

---

## Section 4: Config & Test Changes

### Config changes (`config_features.py`)

| Old | New |
|-----|-----|
| `feature_lettuce_verification` | `feature_hallucination_verification` |
| `hallucination_warn_threshold: 0.10` | `hallucination_warn_threshold: 0.15` |
| `hallucination_block_threshold: 0.30` | `hallucination_block_threshold: 0.40` |
| `lettuce_model_name` | deleted |
| `lettuce_eviction_ttl` | deleted |

### New config

| Setting | Default | Purpose |
|---------|---------|---------|
| `hallucination_verifier_model` | `None` (FAST_MODEL) | Override model for verification |
| `hallucination_max_claims` | `20` | Cap claims to control cost |
| `reranker_provider` | `"jina"` | `"jina"` or `"none"` |

### Test changes

| File | Action |
|------|--------|
| `test_lettuce_verifier.py` | Delete |
| `test_llm_grounding_verifier.py` | Create (mock LLM, test scoring, test degradation) |
| `test_output_verifier.py` | Update threshold assertions |
| `test_delivery_integrity_gate.py` | Update threshold references |
| `test_reranker.py` | Remove `SelfHostedReranker` tests |

### Expected impact

| Metric | Before | After |
|--------|--------|-------|
| Backend image | ~4.2 GB | ~700 MB |
| Cold start | 5-10s | 0s |
| Verification latency | ~200ms (local) | ~500ms (API) |
| GPU memory | ~1.5 GB | 0 |
| Dependencies removed | 3 | -- |
| False positive rate | High (needed heuristics) | Lower (semantic) |
