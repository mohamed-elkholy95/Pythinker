"""Tests for search fidelity check (2026-02-13 plan Phase 4)."""

from app.domain.models.request_contract import RequestContract
from app.domain.services.agents.search_fidelity import check_search_fidelity


def test_entity_in_query_passes() -> None:
    """Query containing locked entity passes."""
    contract = RequestContract(
        exact_query="Research Claude Sonnet 4.5",
        locked_entities=["Claude Sonnet 4.5"],
    )
    passed, _ = check_search_fidelity("Claude Sonnet 4.5 capabilities", contract)
    assert passed is True


def test_entity_missing_repairs() -> None:
    """Query missing entity returns repaired query with entity prepended."""
    contract = RequestContract(
        exact_query="Research Claude Sonnet 4.5",
        locked_entities=["Claude Sonnet 4.5"],
    )
    passed, repaired = check_search_fidelity("AI model capabilities", contract)
    assert passed is False
    assert repaired.startswith("Claude Sonnet 4.5")
    assert "AI model capabilities" in repaired


def test_no_contract_passes() -> None:
    """When contract is None, always passes."""
    passed, query = check_search_fidelity("anything", None)
    assert passed is True
    assert query == "anything"


def test_empty_entities_passes() -> None:
    """When contract has no locked entities, passes."""
    contract = RequestContract(exact_query="Hi", locked_entities=[])
    passed, query = check_search_fidelity("search query", contract)
    assert passed is True
    assert query == "search query"
