"""Tests for DeliveryFidelityChecker (2026-02-13 plan Phase 3)."""

from app.domain.models.request_contract import RequestContract
from app.domain.services.agents.delivery_fidelity import (
    DeliveryFidelityChecker,
)


def test_all_entities_present_passes() -> None:
    """Output containing all locked entities passes."""
    contract = RequestContract(
        exact_query="What is Claude Sonnet 4.5?",
        locked_entities=["Claude Sonnet 4.5"],
        locked_versions=["4.5"],
    )
    checker = DeliveryFidelityChecker()
    result = checker.check_entity_fidelity(
        "Claude Sonnet 4.5 is an AI model. Version 4.5 was released in 2025.",
        contract,
    )
    assert result.passed is True
    assert result.fidelity_score == 1.0
    assert result.missing_entities == []


def test_one_entity_missing_fails() -> None:
    """Output missing a locked entity fails."""
    contract = RequestContract(
        exact_query="Compare GPT-4 and Claude Opus",
        locked_entities=["GPT-4", "Claude Opus"],
    )
    checker = DeliveryFidelityChecker()
    result = checker.check_entity_fidelity(
        "Claude Opus is a strong model.",
        contract,
    )
    assert result.passed is False
    assert "GPT-4" in result.missing_entities
    assert result.fidelity_score < 1.0


def test_version_drift_detected() -> None:
    """Missing version number is detected."""
    contract = RequestContract(
        exact_query="Python 3.12 features",
        locked_entities=["Python 3.12"],
        locked_versions=["3.12"],
    )
    checker = DeliveryFidelityChecker()
    result = checker.check_entity_fidelity(
        "Python has many features.",
        contract,
    )
    assert result.passed is False
    assert "version 3.12" in result.missing_entities


def test_no_contract_passes() -> None:
    """When contract is None, always passes."""
    checker = DeliveryFidelityChecker()
    result = checker.check_entity_fidelity("Some output", None)
    assert result.passed is True
    assert result.fidelity_score == 1.0


def test_empty_contract_passes() -> None:
    """When contract has no locked terms, passes."""
    contract = RequestContract(exact_query="Hello", locked_entities=[], locked_versions=[])
    checker = DeliveryFidelityChecker()
    result = checker.check_entity_fidelity("Any output", contract)
    assert result.passed is True
    assert result.fidelity_score == 1.0
