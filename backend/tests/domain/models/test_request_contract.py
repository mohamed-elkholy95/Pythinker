"""Tests for RequestContract domain model."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.domain.models.request_contract import RequestContract


@pytest.mark.unit
class TestRequestContractDefaults:
    def test_required_field_only(self) -> None:
        rc = RequestContract(exact_query="Find the best Python package manager")
        assert rc.exact_query == "Find the best Python package manager"

    def test_intent_default_empty_string(self) -> None:
        rc = RequestContract(exact_query="some query")
        assert rc.intent == ""

    def test_action_type_default_general(self) -> None:
        rc = RequestContract(exact_query="some query")
        assert rc.action_type == "general"

    def test_locked_entities_default_empty(self) -> None:
        rc = RequestContract(exact_query="some query")
        assert rc.locked_entities == []

    def test_locked_versions_default_empty(self) -> None:
        rc = RequestContract(exact_query="some query")
        assert rc.locked_versions == []

    def test_numeric_constraints_default_empty(self) -> None:
        rc = RequestContract(exact_query="some query")
        assert rc.numeric_constraints == []

    def test_extraction_method_default_hybrid(self) -> None:
        rc = RequestContract(exact_query="some query")
        assert rc.extraction_method == "hybrid"

    def test_extraction_confidence_default_one(self) -> None:
        rc = RequestContract(exact_query="some query")
        assert rc.extraction_confidence == 1.0

    def test_missing_exact_query_raises(self) -> None:
        with pytest.raises(ValidationError):
            RequestContract()  # type: ignore[call-arg]


@pytest.mark.unit
class TestRequestContractExplicitFields:
    def test_intent_set(self) -> None:
        rc = RequestContract(
            exact_query="Compare Python 3.12 vs 3.11",
            intent="comparison",
        )
        assert rc.intent == "comparison"

    def test_action_type_research(self) -> None:
        rc = RequestContract(
            exact_query="Research AI frameworks",
            action_type="research",
        )
        assert rc.action_type == "research"

    def test_action_type_browse(self) -> None:
        rc = RequestContract(exact_query="Open docs page", action_type="browse")
        assert rc.action_type == "browse"

    def test_action_type_code(self) -> None:
        rc = RequestContract(exact_query="Write a function", action_type="code")
        assert rc.action_type == "code"

    def test_locked_entities_populated(self) -> None:
        rc = RequestContract(
            exact_query="Benchmark Claude Sonnet 4.5 on Python 3.12",
            locked_entities=["Claude Sonnet 4.5", "Python 3.12"],
        )
        assert len(rc.locked_entities) == 2
        assert "Claude Sonnet 4.5" in rc.locked_entities
        assert "Python 3.12" in rc.locked_entities

    def test_locked_versions_populated(self) -> None:
        rc = RequestContract(
            exact_query="Use version 4.5 and 3.12",
            locked_versions=["4.5", "3.12"],
        )
        assert rc.locked_versions == ["4.5", "3.12"]

    def test_numeric_constraints_populated(self) -> None:
        rc = RequestContract(
            exact_query="Top 5 tools under $100",
            numeric_constraints=["top 5", "under $100"],
        )
        assert rc.numeric_constraints == ["top 5", "under $100"]

    def test_extraction_method_regex(self) -> None:
        rc = RequestContract(
            exact_query="some query",
            extraction_method="regex",
        )
        assert rc.extraction_method == "regex"

    def test_extraction_method_llm(self) -> None:
        rc = RequestContract(
            exact_query="some query",
            extraction_method="llm",
        )
        assert rc.extraction_method == "llm"

    def test_extraction_confidence_partial(self) -> None:
        rc = RequestContract(
            exact_query="some query",
            extraction_confidence=0.75,
        )
        assert rc.extraction_confidence == 0.75

    def test_extraction_confidence_zero(self) -> None:
        rc = RequestContract(
            exact_query="some query",
            extraction_confidence=0.0,
        )
        assert rc.extraction_confidence == 0.0


@pytest.mark.unit
class TestRequestContractFullyPopulated:
    def test_all_fields_set(self) -> None:
        rc = RequestContract(
            exact_query="Top 5 Python 3.12 async frameworks under $0 (free)",
            intent="research",
            action_type="research",
            locked_entities=["Python 3.12"],
            locked_versions=["3.12"],
            numeric_constraints=["top 5", "free"],
            extraction_method="hybrid",
            extraction_confidence=0.95,
        )
        assert rc.exact_query == "Top 5 Python 3.12 async frameworks under $0 (free)"
        assert rc.intent == "research"
        assert rc.action_type == "research"
        assert rc.locked_entities == ["Python 3.12"]
        assert rc.locked_versions == ["3.12"]
        assert rc.numeric_constraints == ["top 5", "free"]
        assert rc.extraction_method == "hybrid"
        assert rc.extraction_confidence == 0.95

    def test_exact_query_preserved_unmodified(self) -> None:
        raw = "  What is  GPT-5.3  exactly?  "
        rc = RequestContract(exact_query=raw)
        assert rc.exact_query == raw

    def test_lists_are_independent_between_instances(self) -> None:
        rc1 = RequestContract(exact_query="q1")
        rc2 = RequestContract(exact_query="q2")
        rc1.locked_entities.append("entity_a")
        assert rc2.locked_entities == []

    def test_serialization_roundtrip(self) -> None:
        rc = RequestContract(
            exact_query="Find top 3 tools for Python 3.12",
            intent="research",
            action_type="research",
            locked_entities=["Python 3.12"],
            locked_versions=["3.12"],
            numeric_constraints=["top 3"],
            extraction_method="hybrid",
            extraction_confidence=0.9,
        )
        data = rc.model_dump()
        rc2 = RequestContract.model_validate(data)
        assert rc2.exact_query == rc.exact_query
        assert rc2.intent == rc.intent
        assert rc2.action_type == rc.action_type
        assert rc2.locked_entities == rc.locked_entities
        assert rc2.locked_versions == rc.locked_versions
        assert rc2.numeric_constraints == rc.numeric_constraints
        assert rc2.extraction_method == rc.extraction_method
        assert rc2.extraction_confidence == rc.extraction_confidence

    def test_model_json_roundtrip(self) -> None:
        rc = RequestContract(
            exact_query="Find the best uv alternatives",
            locked_entities=["uv"],
        )
        json_str = rc.model_dump_json()
        rc2 = RequestContract.model_validate_json(json_str)
        assert rc2.exact_query == rc.exact_query
        assert rc2.locked_entities == rc.locked_entities
