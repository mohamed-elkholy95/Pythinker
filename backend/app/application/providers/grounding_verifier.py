"""Application-layer factory for LLMGroundingVerifier.

Infrastructure wiring (UniversalLLM, model_router, settings) belongs here,
not in the domain layer.
"""

from __future__ import annotations

from app.domain.services.agents.llm_grounding_verifier import LLMGroundingVerifier

_instance: LLMGroundingVerifier | None = None


def get_llm_grounding_verifier() -> LLMGroundingVerifier:
    """Get or create the singleton LLMGroundingVerifier.

    Uses FAST_MODEL tier via model_router for cost-efficient verification.
    """
    global _instance
    if _instance is None:
        from app.core.config import get_settings
        from app.domain.services.agents.model_router import ModelTier, get_model_router
        from app.infrastructure.external.llm.universal_llm import UniversalLLM

        settings = get_settings()
        router = get_model_router()

        # Use FAST tier — verification is classification, not generation
        model_config = router._get_config(ModelTier.FAST)

        llm = UniversalLLM(
            model_name=settings.hallucination_verifier_model or model_config.model_name,
        )

        _instance = LLMGroundingVerifier(
            llm=llm,
            max_claims=settings.hallucination_max_claims,
        )
    return _instance
