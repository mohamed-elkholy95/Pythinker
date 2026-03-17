"""Search fidelity check and repair (2026-02-13 plan Phase 4)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app.domain.models.request_contract import RequestContract


def check_search_fidelity(
    search_query: str,
    contract: RequestContract | None,
) -> tuple[bool, str]:
    """Verify search query contains relevant locked entities.

    Returns:
        (passed, repaired_query)
        If passed is False, repaired_query may have entity prepended.
    """
    if not contract or not contract.locked_entities:
        return True, search_query

    query_lower = search_query.lower()
    has_entity = any(e.lower() in query_lower for e in contract.locked_entities)
    if has_entity:
        return True, search_query

    # Repair: prepend most relevant locked entity
    first_entity = contract.locked_entities[0]
    repaired = f"{first_entity} {search_query}".strip()
    return False, repaired
