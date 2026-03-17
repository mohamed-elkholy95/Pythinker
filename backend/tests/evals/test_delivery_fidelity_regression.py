"""Delivery fidelity regression (2026-02-13 plan Phase 6)."""

from app.domain.models.request_contract import RequestContract
from app.domain.services.agents.delivery_fidelity import DeliveryFidelityChecker


def test_output_with_all_entities_passes() -> None:
    """Output containing all locked entities passes."""
    contract = RequestContract(
        exact_query="Claude Sonnet 4.5 features",
        locked_entities=["Claude Sonnet 4.5"],
        locked_versions=["4.5"],
    )
    checker = DeliveryFidelityChecker()
    result = checker.check_entity_fidelity(
        "Claude Sonnet 4.5 offers strong reasoning. Version 4.5 was released in 2025.",
        contract,
    )
    assert result.passed
    assert result.fidelity_score == 1.0


def test_output_missing_entity_detected() -> None:
    """Output missing locked entity is detected."""
    contract = RequestContract(
        exact_query="What is Claude Sonnet 4.5?",
        locked_entities=["Claude Sonnet 4.5"],
    )
    checker = DeliveryFidelityChecker()
    result = checker.check_entity_fidelity(
        "Claude Opus is a different model.",
        contract,
    )
    assert not result.passed
    assert "Claude Sonnet 4.5" in result.missing_entities


def test_version_drift_detected() -> None:
    """Version number drift (e.g. 4.5 -> 5.0) is detected as missing."""
    contract = RequestContract(
        exact_query="Python 3.12",
        locked_entities=["Python 3.12"],
        locked_versions=["3.12"],
    )
    checker = DeliveryFidelityChecker()
    result = checker.check_entity_fidelity(
        "Python 5.0 introduces new features.",  # Wrong version
        contract,
    )
    assert not result.passed
    assert any("3.12" in m for m in result.missing_entities)
