"""Entity drift regression suite (2026-02-13 plan Phase 6)."""

import pytest

from app.domain.services.flows.request_contract_extractor import extract


@pytest.mark.parametrize(
    "query,expected_entities",
    [
        ("What is Claude Sonnet 4.5?", ["Claude Sonnet 4.5"]),
        ("Compare GPT-4 and Claude Opus 4.6", ["GPT-4", "Claude Opus 4.6"]),
        ("Python 3.12 new features", ["Python 3.12"]),
        ("FastAPI 0.115 migration guide", ["0.115"]),
        ("Top 5 JavaScript frameworks", ["Top 5"]),
    ],
)
def test_entity_preservation(query: str, expected_entities: list[str]) -> None:
    """Extraction must preserve exact entities from query."""
    r = extract(query)
    entities_lower = [e.lower() for e in r.locked_entities]
    numeric_lower = [n.lower() for n in r.numeric_constraints]
    for expected in expected_entities:
        exp_lower = expected.lower()
        found = (
            exp_lower in entities_lower
            or any(exp_lower in e for e in entities_lower)
            or expected in r.locked_versions
            or exp_lower in numeric_lower
            or any(exp_lower in n for n in numeric_lower)
        )
        assert found, (
            f"Expected '{expected}' not found in "
            f"entities={r.locked_entities}, versions={r.locked_versions}, "
            f"numeric={r.numeric_constraints}"
        )
