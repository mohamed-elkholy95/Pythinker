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
        llm_response = json.dumps(
            {
                "claims": [
                    {"claim": "Paris is the capital of France", "verdict": "supported"},
                    {"claim": "France has 67 million people", "verdict": "supported"},
                ]
            }
        )
        verifier._llm.ask = AsyncMock(return_value={"content": llm_response})

        result = await verifier.verify(
            response_text="Paris is the capital of France. France has 67 million people. " * 5,
            source_context=[
                "Paris is the capital of France, a country in Western Europe. The population is approximately 67 million people according to the latest census data."
            ],
        )

        assert result.hallucination_score == 0.0
        assert len(result.flagged_claims) == 0
        assert not result.skipped

    @pytest.mark.asyncio
    async def test_verify_mixed_verdicts(self, verifier):
        """1 unsupported out of 3 claims → score ~0.33."""
        llm_response = json.dumps(
            {
                "claims": [
                    {"claim": "Python is popular", "verdict": "supported"},
                    {"claim": "Python was created in 1989", "verdict": "unsupported"},
                    {"claim": "Python is open source", "verdict": "supported"},
                ]
            }
        )
        verifier._llm.ask = AsyncMock(return_value={"content": llm_response})

        result = await verifier.verify(
            response_text="Python is popular. It was created in 1989. Python is open source. " * 5,
            source_context=[
                "Python is a popular programming language that is open source and widely used in industry and academia."
            ],
        )

        assert abs(result.hallucination_score - 1 / 3) < 0.01
        assert len(result.flagged_claims) == 1
        assert result.flagged_claims[0].verdict == "unsupported"

    @pytest.mark.asyncio
    async def test_verify_all_unsupported(self, verifier):
        """All claims unsupported → score 1.0."""
        llm_response = json.dumps(
            {
                "claims": [
                    {"claim": "Claim A", "verdict": "unsupported"},
                    {"claim": "Claim B", "verdict": "unsupported"},
                ]
            }
        )
        verifier._llm.ask = AsyncMock(return_value={"content": llm_response})

        result = await verifier.verify(
            response_text="Claim A is definitely true. Claim B is also definitely correct. " * 5,
            source_context=[
                "This is an entirely unrelated context about different topics that does not support either claim at all."
            ],
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
        llm_response = json.dumps(
            {
                "claims": [
                    {"claim": "X is good", "verdict": "supported"},
                    {"claim": "Y is subjective", "verdict": "unverifiable"},
                ]
            }
        )
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
            source_context=["This is a sufficiently long source context for grounding verification testing purposes."],
        )
        # Should process max 3 claims regardless of LLM output
        assert not result.skipped


class TestSingleton:
    def test_get_llm_grounding_verifier_returns_instance(self):
        import app.domain.services.agents.llm_grounding_verifier as mod

        # Reset singleton
        mod._instance = None

        mock_settings = MagicMock(
            hallucination_verifier_model=None,
            hallucination_max_claims=20,
        )
        mock_llm = MagicMock()

        with (
            patch("app.core.config.get_settings", return_value=mock_settings),
            patch(
                "app.domain.services.agents.model_router.get_model_router",
                return_value=MagicMock(_get_config=MagicMock(return_value=MagicMock(model_name="test-model"))),
            ),
            patch(
                "app.infrastructure.external.llm.universal_llm.UniversalLLM",
                return_value=mock_llm,
            ),
        ):
            verifier = get_llm_grounding_verifier()
            assert isinstance(verifier, LLMGroundingVerifier)

        # Cleanup singleton
        mod._instance = None
