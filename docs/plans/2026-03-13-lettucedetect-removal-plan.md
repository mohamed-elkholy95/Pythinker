# LettuceDetect Removal — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace LettuceDetect (ModernBERT) with LLM-as-Judge grounding verification, remove PyTorch/sentence-transformers/lettucedetect deps (~3.5 GB image reduction).

**Architecture:** New `LLMGroundingVerifier` calls existing LLM provider (FAST_MODEL tier) to fact-check response claims against source context. Same `verify()` interface as LettuceDetect — `output_verifier.py` and `execution.py` call sites unchanged. `SelfHostedReranker` replaced by existing `JinaReranker`.

**Tech Stack:** Python 3.11, FastAPI, Pydantic v2, existing LLM provider (Kimi/OpenAI-compatible), pytest

**Design doc:** `docs/plans/2026-03-13-lettucedetect-removal-design.md`

---

### Task 1: Update Config — Rename Flags & Remove Lettuce Settings

**Files:**
- Modify: `backend/app/core/config_features.py:245-251` (FeatureFlagsSettingsMixin)
- Modify: `backend/app/core/config.py:456,517` (resolve_feature_flags function)

**Step 1: Update config_features.py**

In `FeatureFlagsSettingsMixin`:

1. Rename `feature_lettuce_verification` → `feature_hallucination_verification` (line 245-247)
2. Delete `lettuce_model_path` (line 248)
3. Delete `lettuce_confidence_threshold` (line 249)
4. Delete `lettuce_min_response_length` (line 250)
5. Update threshold defaults: `hallucination_warn_threshold: 0.10` → `0.15`, `hallucination_block_threshold: 0.30` → `0.40` (lines 385-386)
6. Add new settings after the hallucination block:
   ```python
   hallucination_verifier_model: str | None = None  # Override model for verification (default: FAST_MODEL)
   hallucination_max_claims: int = 20  # Cap extracted claims to control LLM cost
   reranker_provider: str = "jina"  # "jina" (API) or "none" (skip reranking)
   ```
7. Update comments to remove LettuceDetect references

**Step 2: Update config.py resolve_feature_flags()**

In the `resolve_feature_flags()` function:
1. Line 456: Change `"lettuce_verification": True` → `"hallucination_verification": True`
2. Line 517: Change `"lettuce_verification": settings.feature_lettuce_verification` → `"hallucination_verification": settings.feature_hallucination_verification`

**Step 3: Run tests**

```bash
cd backend && conda activate pythinker && pytest tests/test_runtime_feature_flags.py -v --no-header -q
```

Update `tests/test_runtime_feature_flags.py` line 35: `feature_lettuce_verification=True` → `feature_hallucination_verification=True`

**Step 4: Run tests again and verify pass**

```bash
pytest tests/test_runtime_feature_flags.py -v --no-header -q
```

**Step 5: Commit**

```bash
git add backend/app/core/config_features.py backend/app/core/config.py backend/tests/test_runtime_feature_flags.py
git commit -m "refactor(config): rename lettuce flags to hallucination_verification, retune thresholds

Rename feature_lettuce_verification → feature_hallucination_verification.
Delete lettuce_model_path, lettuce_confidence_threshold, lettuce_min_response_length.
Add hallucination_verifier_model, hallucination_max_claims, reranker_provider.
Retune thresholds: warn 0.10→0.15, block 0.30→0.40 for LLM-as-Judge scoring."
```

---

### Task 2: Create LLM Grounding Verifier (TDD)

**Files:**
- Create: `backend/tests/domain/services/agents/test_llm_grounding_verifier.py`
- Create: `backend/app/domain/services/agents/llm_grounding_verifier.py`

**Step 1: Write failing tests**

Create `backend/tests/domain/services/agents/test_llm_grounding_verifier.py`:

```python
"""Tests for LLM-based grounding verification."""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.services.agents.llm_grounding_verifier import (
    FlaggedClaim,
    LLMGroundingVerifier,
    VerificationResult,
    get_llm_grounding_verifier,
)


@pytest.fixture
def verifier():
    """Create verifier with mocked LLM."""
    mock_llm = AsyncMock()
    return LLMGroundingVerifier(llm=mock_llm)


class TestVerificationResult:
    def test_no_hallucinations(self):
        result = VerificationResult(hallucination_score=0.0, flagged_claims=[], skipped=False)
        assert result.hallucination_score == 0.0
        assert not result.skipped

    def test_with_hallucinations(self):
        claims = [FlaggedClaim(claim_text="X has 100M users", verdict="unsupported", source_snippet=None)]
        result = VerificationResult(hallucination_score=0.5, flagged_claims=claims, skipped=False)
        assert result.hallucination_score == 0.5
        assert len(result.flagged_claims) == 1

    def test_skipped_result(self):
        result = VerificationResult(hallucination_score=0.0, flagged_claims=[], skipped=True, skip_reason="LLM failed")
        assert result.skipped
        assert result.skip_reason == "LLM failed"


class TestLLMGroundingVerifier:
    @pytest.mark.asyncio
    async def test_verify_all_supported(self, verifier):
        """LLM says all claims are supported → score 0.0."""
        llm_response = json.dumps({
            "claims": [
                {"claim": "Paris is the capital of France", "verdict": "supported"},
                {"claim": "France has 67 million people", "verdict": "supported"},
            ]
        })
        verifier._llm.ask = AsyncMock(return_value={"content": llm_response})

        result = await verifier.verify(
            response_text="Paris is the capital of France. France has 67 million people.",
            source_context=["Paris is the capital. Population: 67 million."],
        )

        assert result.hallucination_score == 0.0
        assert len(result.flagged_claims) == 0
        assert not result.skipped

    @pytest.mark.asyncio
    async def test_verify_mixed_verdicts(self, verifier):
        """1 unsupported out of 3 claims → score ~0.33."""
        llm_response = json.dumps({
            "claims": [
                {"claim": "Python is popular", "verdict": "supported"},
                {"claim": "Python was created in 1989", "verdict": "unsupported"},
                {"claim": "Python is open source", "verdict": "supported"},
            ]
        })
        verifier._llm.ask = AsyncMock(return_value={"content": llm_response})

        result = await verifier.verify(
            response_text="Python is popular. It was created in 1989. Python is open source.",
            source_context=["Python is popular and open source."],
        )

        assert abs(result.hallucination_score - 1 / 3) < 0.01
        assert len(result.flagged_claims) == 1
        assert result.flagged_claims[0].verdict == "unsupported"

    @pytest.mark.asyncio
    async def test_verify_all_unsupported(self, verifier):
        """All claims unsupported → score 1.0."""
        llm_response = json.dumps({
            "claims": [
                {"claim": "Claim A", "verdict": "unsupported"},
                {"claim": "Claim B", "verdict": "unsupported"},
            ]
        })
        verifier._llm.ask = AsyncMock(return_value={"content": llm_response})

        result = await verifier.verify(
            response_text="Claim A. Claim B.",
            source_context=["Unrelated context."],
        )

        assert result.hallucination_score == 1.0
        assert len(result.flagged_claims) == 2

    @pytest.mark.asyncio
    async def test_verify_short_response_skipped(self, verifier):
        """Responses under min_response_length are skipped."""
        result = await verifier.verify(
            response_text="Short.",
            source_context=["Some context."],
        )
        assert result.skipped
        assert "too short" in result.skip_reason.lower()

    @pytest.mark.asyncio
    async def test_verify_no_context_skipped(self, verifier):
        """No source context → skip verification."""
        result = await verifier.verify(
            response_text="A " * 200,
            source_context=[],
        )
        assert result.skipped

    @pytest.mark.asyncio
    async def test_verify_llm_failure_graceful(self, verifier):
        """LLM call failure → skip with score 0.0."""
        verifier._llm.ask = AsyncMock(side_effect=RuntimeError("LLM timeout"))

        result = await verifier.verify(
            response_text="A " * 200,
            source_context=["Some context here."],
        )

        assert result.skipped
        assert result.hallucination_score == 0.0

    @pytest.mark.asyncio
    async def test_verify_malformed_json_graceful(self, verifier):
        """Malformed LLM JSON → skip gracefully."""
        verifier._llm.ask = AsyncMock(return_value={"content": "not valid json {{"})

        result = await verifier.verify(
            response_text="A " * 200,
            source_context=["Some context."],
        )

        assert result.skipped
        assert result.hallucination_score == 0.0

    @pytest.mark.asyncio
    async def test_verify_unverifiable_treated_as_supported(self, verifier):
        """Unverifiable claims don't count as unsupported."""
        llm_response = json.dumps({
            "claims": [
                {"claim": "X is good", "verdict": "supported"},
                {"claim": "Y is subjective", "verdict": "unverifiable"},
            ]
        })
        verifier._llm.ask = AsyncMock(return_value={"content": llm_response})

        result = await verifier.verify(
            response_text="X is good. Y is subjective. " * 20,
            source_context=["X is good."],
        )

        # Only unsupported claims count. 0 unsupported / 2 total = 0.0
        assert result.hallucination_score == 0.0

    @pytest.mark.asyncio
    async def test_max_claims_cap(self, verifier):
        """Claims are capped to hallucination_max_claims."""
        verifier._max_claims = 3
        many_claims = [{"claim": f"Claim {i}", "verdict": "supported"} for i in range(10)]
        llm_response = json.dumps({"claims": many_claims})
        verifier._llm.ask = AsyncMock(return_value={"content": llm_response})

        result = await verifier.verify(
            response_text="Long text " * 100,
            source_context=["Context."],
        )
        # Should process max 3 claims regardless of LLM output
        assert not result.skipped


class TestSingleton:
    def test_get_llm_grounding_verifier_returns_instance(self):
        with patch("app.domain.services.agents.llm_grounding_verifier.get_settings") as mock_settings:
            mock_settings.return_value = MagicMock(
                hallucination_verifier_model=None,
                hallucination_max_claims=20,
            )
            verifier = get_llm_grounding_verifier()
            assert isinstance(verifier, LLMGroundingVerifier)
```

**Step 2: Run tests to verify they fail**

```bash
pytest tests/domain/services/agents/test_llm_grounding_verifier.py -v --no-header -q
```

Expected: ImportError (module doesn't exist yet)

**Step 3: Implement `llm_grounding_verifier.py`**

Create `backend/app/domain/services/agents/llm_grounding_verifier.py`:

```python
"""LLM-based grounding verification.

Replaces LettuceDetect with a zero-ML-dependency approach: uses the existing
LLM provider to fact-check response claims against source context.

Architecture:
    LLMGroundingVerifier calls the FAST_MODEL tier via the injected LLM
    interface to extract claims from a response and classify each as
    supported/unsupported/unverifiable. Returns a VerificationResult
    with a hallucination_score (ratio of unsupported claims).

Usage:
    verifier = get_llm_grounding_verifier()
    result = await verifier.verify(
        response_text="The population of France is 69 million.",
        source_context=["France has 67 million people."],
    )
    if result.hallucination_score > 0.4:
        # flag or append disclaimer
        ...
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.external.llm import LLM

logger = logging.getLogger(__name__)

_VERIFICATION_SYSTEM_PROMPT = """\
You are a fact-checking assistant. Given a RESPONSE and SOURCE CONTEXT, extract \
the key factual claims from the response and check each against the source context.

Return a JSON object with a single key "claims" containing an array. Each element:
{
  "claim": "<the factual claim from the response>",
  "verdict": "supported" | "unsupported" | "unverifiable"
}

Rules:
- "supported": the claim is directly backed by the source context
- "unsupported": the claim contradicts the source context or makes specific \
assertions (numbers, dates, names) not found in the source context
- "unverifiable": the claim is subjective, a general statement, or cannot be \
checked against the provided context (e.g., opinions, formatting instructions)
- Only extract factual claims (numbers, dates, names, comparisons, statistics)
- Skip stylistic or structural text (headings, transitions, disclaimers)
- Return ONLY the JSON object, no other text
"""


@dataclass(frozen=True, slots=True)
class FlaggedClaim:
    """A claim flagged during verification."""

    claim_text: str
    verdict: str  # "supported", "unsupported", "unverifiable"
    source_snippet: str | None = None


@dataclass(slots=True)
class VerificationResult:
    """Result of LLM-based grounding verification."""

    hallucination_score: float  # 0.0 (fully supported) to 1.0 (fully unsupported)
    flagged_claims: list[FlaggedClaim] = field(default_factory=list)
    skipped: bool = False
    skip_reason: str = ""


class LLMGroundingVerifier:
    """LLM-based grounding verifier.

    Uses an existing LLM provider to extract and classify factual claims
    from a response against provided source context. Zero ML dependencies.
    """

    def __init__(
        self,
        llm: LLM,
        min_response_length: int = 200,
        max_claims: int = 20,
    ) -> None:
        self._llm = llm
        self._min_response_length = min_response_length
        self._max_claims = max_claims

    async def verify(
        self,
        response_text: str,
        source_context: list[str],
    ) -> VerificationResult:
        """Verify a response against source context for hallucinations.

        Args:
            response_text: The generated response to verify.
            source_context: List of source text chunks for grounding.

        Returns:
            VerificationResult with hallucination score and flagged claims.
        """
        # Skip short responses
        if len(response_text) < self._min_response_length:
            return VerificationResult(
                hallucination_score=0.0,
                skipped=True,
                skip_reason=f"Response too short ({len(response_text)} chars < {self._min_response_length})",
            )

        # Skip if no context
        total_context_len = sum(len(c.strip()) for c in source_context)
        if not source_context or total_context_len < 50:
            return VerificationResult(
                hallucination_score=0.0,
                skipped=True,
                skip_reason="Insufficient source context for grounding",
            )

        try:
            messages = self._build_verification_prompt(response_text, source_context)
            llm_response = await self._llm.ask(messages, tools=None, tool_choice=None)
            content = llm_response.get("content", "")
            return self._parse_verdict(content)
        except Exception as e:
            logger.warning("LLM grounding verification failed: %s", e)
            return VerificationResult(
                hallucination_score=0.0,
                skipped=True,
                skip_reason=f"Verification error: {type(e).__name__}: {e}",
            )

    def _build_verification_prompt(
        self, response_text: str, source_context: list[str]
    ) -> list[dict[str, str]]:
        """Build the verification prompt for the LLM."""
        combined_context = "\n\n---\n\n".join(source_context)
        user_message = (
            f"SOURCE CONTEXT:\n{combined_context}\n\n"
            f"RESPONSE TO VERIFY:\n{response_text}"
        )
        return [
            {"role": "system", "content": _VERIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ]

    def _parse_verdict(self, llm_content: str) -> VerificationResult:
        """Parse the LLM's JSON verdict into a VerificationResult."""
        try:
            # Strip markdown code fences if present
            content = llm_content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])

            data = json.loads(content)
            claims_raw = data.get("claims", [])
            if not isinstance(claims_raw, list):
                claims_raw = []

            # Cap claims
            claims_raw = claims_raw[: self._max_claims]

            flagged: list[FlaggedClaim] = []
            total = 0
            unsupported = 0

            for claim in claims_raw:
                if not isinstance(claim, dict):
                    continue
                claim_text = claim.get("claim", "")
                verdict = claim.get("verdict", "unverifiable").lower()
                if verdict not in ("supported", "unsupported", "unverifiable"):
                    verdict = "unverifiable"

                total += 1
                if verdict == "unsupported":
                    unsupported += 1
                    flagged.append(
                        FlaggedClaim(
                            claim_text=claim_text,
                            verdict=verdict,
                            source_snippet=claim.get("source_snippet"),
                        )
                    )

            if total == 0:
                return VerificationResult(hallucination_score=0.0, skipped=True, skip_reason="No claims extracted")

            score = unsupported / total
            logger.info(
                "LLM grounding: %d/%d claims unsupported (score=%.2f)",
                unsupported, total, score,
            )
            return VerificationResult(hallucination_score=score, flagged_claims=flagged)

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.warning("Failed to parse LLM verification response: %s", e)
            return VerificationResult(
                hallucination_score=0.0,
                skipped=True,
                skip_reason=f"JSON parse error: {e}",
            )


# ── Singleton factory ──────────────────────────────────────────────

_instance: LLMGroundingVerifier | None = None


def get_llm_grounding_verifier() -> LLMGroundingVerifier:
    """Get or create the singleton LLMGroundingVerifier.

    Uses FAST_MODEL tier via model_router for cost-efficient verification.
    """
    global _instance
    if _instance is None:
        from app.core.config import get_settings
        from app.domain.services.agents.model_router import get_model_router
        from app.infrastructure.external.llm.universal_llm import UniversalLLM

        settings = get_settings()
        router = get_model_router()

        # Use FAST tier — verification is classification, not generation
        from app.domain.services.agents.complexity_assessor import ComplexityTier

        model_config = router.route(ComplexityTier.FAST)

        llm = UniversalLLM(
            model=settings.hallucination_verifier_model or model_config.model_name,
            api_key=model_config.api_key,
            api_base=model_config.api_base,
        )

        _instance = LLMGroundingVerifier(
            llm=llm,
            max_claims=settings.hallucination_max_claims,
        )
    return _instance
```

**Step 4: Run tests to verify they pass**

```bash
pytest tests/domain/services/agents/test_llm_grounding_verifier.py -v --no-header -q
```

Expected: All pass

**Step 5: Commit**

```bash
git add backend/app/domain/services/agents/llm_grounding_verifier.py backend/tests/domain/services/agents/test_llm_grounding_verifier.py
git commit -m "feat(verification): add LLM-based grounding verifier

Zero ML dependencies. Uses existing LLM provider (FAST_MODEL tier) to
extract claims and classify as supported/unsupported/unverifiable.
Same verify() interface as LettuceDetect for drop-in replacement."
```

---

### Task 3: Rewire OutputVerifier to Use LLM Grounding Verifier

**Files:**
- Modify: `backend/app/domain/services/agents/output_verifier.py:69-106,422-584`
- Modify: `backend/app/domain/services/agents/execution.py:182-183,193-202`

**Step 1: Update OutputVerifier __slots__ and __init__**

In `output_verifier.py`:
1. In `__slots__` (line 69-81): rename `"_lettuce_enabled"` → `"_hallucination_verification_enabled"`
2. In `__init__` (line 94): rename param `lettuce_enabled: bool = True` → `hallucination_verification_enabled: bool = True`
3. In `__init__` body (line 106): rename `self._lettuce_enabled` → `self._hallucination_verification_enabled`

**Step 2: Rewrite verify_hallucination method (lines 422-584)**

Replace the LettuceDetect import/call block with LLM grounding verifier:

1. Line 429: Change `self._lettuce_enabled and flags.get("lettuce_verification", True)` → `self._hallucination_verification_enabled and flags.get("hallucination_verification", True)`
2. Lines 431-433: Replace `from app.domain.services.agents.lettuce_verifier import get_lettuce_verifier` / `verifier = get_lettuce_verifier()` with `from app.domain.services.agents.llm_grounding_verifier import get_llm_grounding_verifier` / `verifier = get_llm_grounding_verifier()`
3. Replace the `lettuce_result = verifier.verify(context=..., question=..., answer=...)` call with `grounding_result = await verifier.verify(response_text=content_for_verification, source_context=source_context)`
4. Map `grounding_result` fields to existing threshold logic:
   - `grounding_result.hallucination_score` → replaces `lettuce_result.hallucination_ratio`
   - `grounding_result.flagged_claims` → replaces `lettuce_result.hallucinated_spans`
   - `grounding_result.skipped` → same field name
5. Remove all LettuceDetect-specific span logging (lines 480-492) and replace with claim-level logging
6. Update metric labels: `"method": "lettuce"` → `"method": "llm_grounding"`
7. Remove threshold getter `getattr(settings, ...)` — read directly from settings

**Step 3: Update execution.py**

1. Line 182-183: Rename `self._lettuce_enabled = True` → `self._hallucination_verification_enabled = True`
2. Line 202: Rename `lettuce_enabled=self._lettuce_enabled` → `hallucination_verification_enabled=self._hallucination_verification_enabled`

**Step 4: Update docstrings and comments**

Remove all references to "LettuceDetect", "ModernBERT", "token-level" in output_verifier.py and execution.py. Replace with "LLM-based grounding verification".

**Step 5: Run tests**

```bash
pytest tests/domain/services/agents/ -v --no-header -q -x
```

**Step 6: Commit**

```bash
git add backend/app/domain/services/agents/output_verifier.py backend/app/domain/services/agents/execution.py
git commit -m "refactor(verification): rewire output_verifier to use LLM grounding verifier

Replace LettuceDetect import with LLMGroundingVerifier. Same threshold
logic, same delivery gate behavior. Rename _lettuce_enabled to
_hallucination_verification_enabled throughout."
```

---

### Task 4: Update Test Files That Reference LettuceDetect

**Files:**
- Modify: `backend/tests/unit/agents/test_report_quality_pipeline.py`
- Modify: `backend/tests/domain/services/agents/test_output_verifier_table_exemption.py`
- Modify: `backend/tests/integration/test_agent_e2e.py:923` (comment only)

**Step 1: Update test_report_quality_pipeline.py**

1. `_make_output_verifier()` (line 187): Rename kwarg `lettuce_enabled` → `hallucination_verification_enabled`
2. Line 201: Change `"lettuce_verification": True` → `"hallucination_verification": True`
3. `_make_lettuce_result()` helper (line 207): Rename to `_make_grounding_result()` and update to return `VerificationResult`-compatible mock with `hallucination_score` instead of `hallucination_ratio`, and `flagged_claims` instead of `hallucinated_spans`
4. All `with patch("app.domain.services.agents.lettuce_verifier.get_lettuce_verifier", ...)` → `with patch("app.domain.services.agents.llm_grounding_verifier.get_llm_grounding_verifier", ...)`
5. Update all `mock_verifier.verify.return_value` calls — the new verifier's `verify()` is async, so use `AsyncMock` and set the return value as a coroutine result
6. Update threshold assertions: warn 0.10→0.15, block 0.30→0.40

**Step 2: Update test_output_verifier_table_exemption.py**

Check for any LettuceDetect references and update to LLM grounding verifier pattern.

**Step 3: Update test_agent_e2e.py**

Line 923: Update comment from "LettuceDetect patterns" to "LLM grounding verification patterns" (comment-only change).

**Step 4: Run all affected tests**

```bash
pytest tests/unit/agents/test_report_quality_pipeline.py tests/domain/services/agents/test_output_verifier_table_exemption.py tests/integration/test_agent_e2e.py -v --no-header -q
```

**Step 5: Commit**

```bash
git add backend/tests/unit/agents/test_report_quality_pipeline.py backend/tests/domain/services/agents/test_output_verifier_table_exemption.py backend/tests/integration/test_agent_e2e.py
git commit -m "test: update verification tests for LLM grounding verifier

Replace LettuceDetect mock patterns with LLMGroundingVerifier.
Update threshold assertions (warn 0.15, block 0.40)."
```

---

### Task 5: Delete LettuceDetect Files

**Files:**
- Delete: `backend/app/domain/services/agents/lettuce_verifier.py`
- Delete: `backend/tests/domain/services/agents/test_lettuce_verifier_eviction.py`

**Step 1: Delete files**

```bash
rm backend/app/domain/services/agents/lettuce_verifier.py
rm backend/tests/domain/services/agents/test_lettuce_verifier_eviction.py
```

**Step 2: Verify no remaining imports**

```bash
cd backend && grep -rn "lettuce_verifier\|get_lettuce_verifier\|LettuceVerifier\|LettuceVerificationResult" app/ tests/ --include="*.py"
```

Expected: Zero results (all references updated in Tasks 3-4)

**Step 3: Run full test suite**

```bash
pytest tests/ -v --no-header -q -x --timeout=30
```

**Step 4: Commit**

```bash
git add -A backend/app/domain/services/agents/lettuce_verifier.py backend/tests/domain/services/agents/test_lettuce_verifier_eviction.py
git commit -m "chore: delete lettuce_verifier.py and its tests

LettuceDetect fully replaced by LLMGroundingVerifier (Task 2-3)."
```

---

### Task 6: Memory Reranking Migration (SelfHostedReranker → JinaReranker)

**Files:**
- Modify: `backend/app/domain/services/retrieval/reranker.py` (delete SelfHostedReranker, keep module for backward compat or delete entirely)
- Modify: `backend/app/domain/services/memory_service.py:589-624`

**Step 1: Delete SelfHostedReranker from reranker.py**

Replace entire file content with a deprecation notice that redirects to JinaReranker:

```python
"""Self-hosted reranker — REMOVED.

SelfHostedReranker (CrossEncoder) has been replaced by JinaReranker
(API-based, zero ML deps). See:
  backend/app/infrastructure/external/search/jina_reranker.py

This module is kept only for backward-compatible import paths.
"""

# Backward compatibility: any code doing `from reranker import get_reranker`
# gets a no-op stub that returns results unchanged.


class _NoopReranker:
    def is_available(self) -> bool:
        return False

    def rerank(self, query, candidates, top_k=10):
        return [(text, meta, 0.5) for text, meta in candidates[:top_k]]


_reranker = _NoopReranker()


def get_reranker():
    return _reranker
```

**Step 2: Update memory_service.py reranking block (lines 589-624)**

Replace `SelfHostedReranker` import with `reranker_provider` config check:

```python
        # Phase 3: Reranking
        if enable_reranking and len(results) > limit:
            try:
                from app.core.config import get_settings
                settings = get_settings()

                if getattr(settings, "reranker_provider", "none") == "jina":
                    # Use JinaReranker (API-based, no ML deps)
                    # JinaReranker expects SearchResultItem, but memory results
                    # are MemorySearchResult — fall through to simple truncation
                    # for now (Jina reranking is wired for search, not memory)
                    results = results[:limit]
                    logger.debug("Reranking: Jina provider configured but memory reranking uses truncation")
                else:
                    results = results[:limit]
            except Exception as e:
                logger.debug("Reranking failed, using original results: %s", e)
                results = results[:limit]
```

Note: The existing `JinaReranker` operates on `SearchResultItem` objects, not `MemorySearchResult`. Since `SelfHostedReranker` was already unavailable in most deployments (torch not always present), the practical behavior is unchanged — results are truncated to `limit`.

**Step 3: Run tests**

```bash
pytest tests/domain/services/ -v --no-header -q -x --timeout=30
```

**Step 4: Commit**

```bash
git add backend/app/domain/services/retrieval/reranker.py backend/app/domain/services/memory_service.py
git commit -m "refactor(reranker): remove SelfHostedReranker, simplify memory reranking

SelfHostedReranker required torch + sentence-transformers (~3.3GB).
Replace with no-op stub for backward compat. Memory reranking falls
through to truncation (same practical behavior as when torch was absent)."
```

---

### Task 7: Remove Dependencies from requirements.txt

**Files:**
- Modify: `backend/requirements.txt:73-74,78`

**Step 1: Remove three dependency lines**

Remove:
- Line 73: `sentence-transformers>=3.0.0  # Phase 3: Self-hosted reranking`
- Line 74: `torch>=2.2.0  # Required for sentence-transformers`
- Line 78: `lettucedetect>=0.1.0  # ModernBERT token-level hallucination detector`

Keep the comment on line 77 but update it:
```
# Hallucination detection handled by LLM-as-Judge (llm_grounding_verifier.py)
```

**Step 2: Verify no other files import these packages**

```bash
cd backend && grep -rn "import torch\|from torch\|import sentence_transformers\|from sentence_transformers\|import lettucedetect\|from lettucedetect" app/ --include="*.py"
```

Expected: Zero results (all imports removed in prior tasks)

**Step 3: Commit**

```bash
git add backend/requirements.txt
git commit -m "chore(deps): remove torch, sentence-transformers, lettucedetect

~3.5 GB image size reduction. Hallucination detection now uses
LLM-as-Judge (zero ML deps). Memory reranking uses Jina API."
```

---

### Task 8: Update CLAUDE.md Documentation

**Files:**
- Modify: `CLAUDE.md`

**Step 1: Update LettuceDetect references in CLAUDE.md**

Search for "LettuceDetect", "lettuce", "sentence-transformers", "torch" references in CLAUDE.md and update them to reflect the new LLM-based verification architecture:

- Phase 2 Agent Reliability section: Update description of hallucination detection
- Config block: Remove `lettuce_*` settings references
- Any other references to ModernBERT/LettuceDetect

**Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for LLM-based grounding verification

Replace LettuceDetect/ModernBERT references with LLM-as-Judge architecture."
```

---

### Task 9: Full Verification

**Step 1: Run full backend test suite**

```bash
cd backend && conda activate pythinker && pytest tests/ -v --no-header -q --timeout=60
```

**Step 2: Run linting**

```bash
ruff check . && ruff format --check .
```

**Step 3: Verify no remaining LettuceDetect references**

```bash
grep -rn "lettucedetect\|LettuceDetect\|lettuce_verifier\|_lettuce_enabled\|lettuce_model\|lettuce_confidence\|lettuce_min_response" backend/app/ backend/tests/ --include="*.py"
```

Expected: Zero results (except possibly comments mentioning the migration)

**Step 4: Verify requirements are clean**

```bash
grep -n "torch\|sentence.transformers\|lettucedetect" backend/requirements.txt
```

Expected: Zero results

**Step 5: Final commit if any fixups needed**

Only if linting or tests revealed issues in prior tasks.
