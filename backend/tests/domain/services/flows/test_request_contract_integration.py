"""Integration tests for RequestContract in PlanActFlow (2026-02-13 plan Phase 1)."""

from app.domain.services.flows.enhanced_prompt_quick_validator import EnhancedPromptQuickValidator
from app.domain.services.flows.request_contract_extractor import extract


def test_locked_entities_survive_validation() -> None:
    """When locked entities are passed, validator should not correct them."""
    validator = EnhancedPromptQuickValidator(enabled=True)
    # "Sonnet" might get typo-corrected; with locked entity it should stay
    result = validator.validate(
        "What is Claude Sonnet 4.5?",
        locked_entities=["Claude Sonnet 4.5"],
    )
    # Sonnet and 4.5 should remain
    assert "Sonnet" in result or "sonnet" in result.lower()
    assert "4.5" in result


def test_contract_propagates_intent_and_action() -> None:
    """Contract preserves intent and action_type when provided."""
    r = extract("Research Python 3.12", intent="TASK", action_type="research")
    assert r.intent == "TASK"
    assert r.action_type == "research"
    assert "Python" in str(r.locked_entities) or "python" in str(r.locked_entities).lower()


def test_extract_with_intent_from_fast_path() -> None:
    """Contract can be populated with intent from FastPathRouter."""
    r = extract(
        "Compare Claude Sonnet 4.5 and GPT-4",
        intent="TASK",
        action_type="research",
    )
    assert r.intent == "TASK"
    assert len(r.locked_entities) >= 1
