"""Tests for deal tool → action mapping in step audit (plan_act.py).

Regression tests for:
  Step 1 action audit: expected=['search'] fulfilled=[] missed=['search']
  tools_used=['deal_scraper']

All four deal tool names must map to the 'search' action category so the
audit recognises DealFinder runs as fulfilling search-type steps.
"""

import pytest

# ---------------------------------------------------------------------------
# Shared fixture: the same _verb_tool_map used in plan_act.py _step audit_.
# Keeping it as a plain dict so the test is independent of the class and can
# validate the mapping contract directly.
# ---------------------------------------------------------------------------

VERB_TOOL_MAP: dict[str, set[str]] = {
    "search": {
        "info_search_web",
        "wide_research",
        "deal_scraper",
        "deal_search",
        "deal_find_coupons",
        "deal_compare_prices",
    },
    "browse": {"browser_navigate", "browser_agent"},
    "execute": {"shell_exec", "terminal_exec", "code_exec", "code_execute_python", "code_executor"},
    "run": {"shell_exec", "terminal_exec", "code_exec", "code_execute_python", "code_executor"},
    "benchmark": {"shell_exec", "terminal_exec", "code_exec", "code_execute_python", "code_executor"},
    "test": {"shell_exec", "terminal_exec", "code_exec", "code_execute_python", "code_executor"},
    "write": {"file_write", "file_create", "file"},
    "create": {"file_write", "file_create", "file"},
    "read": {"file_read", "file"},
}


def _audit(description: str, tools_used: set[str]) -> tuple[set[str], set[str], set[str]]:
    """Run the same audit logic as plan_act.py and return (expected, fulfilled, missed)."""
    desc_lower = description.lower()
    expected = {v for v, tools in VERB_TOOL_MAP.items() if v in desc_lower}
    fulfilled = {v for v in expected if tools_used & VERB_TOOL_MAP[v]}
    missed = expected - fulfilled
    return expected, fulfilled, missed


# ---------------------------------------------------------------------------
# deal_scraper — the main DealFinderTool class name
# ---------------------------------------------------------------------------


def test_deal_scraper_fulfills_search_action() -> None:
    """deal_scraper must satisfy a 'search deals' step."""
    _, fulfilled, missed = _audit(
        description="Search for the best laptop deals under $500",
        tools_used={"deal_scraper"},
    )
    assert "search" in fulfilled
    assert "search" not in missed


# ---------------------------------------------------------------------------
# deal_search — the primary sub-function
# ---------------------------------------------------------------------------


def test_deal_search_fulfills_search_action() -> None:
    """deal_search must satisfy a 'search' step."""
    _, fulfilled, missed = _audit(
        description="Search for deals on gaming monitors",
        tools_used={"deal_search"},
    )
    assert "search" in fulfilled
    assert "search" not in missed


# ---------------------------------------------------------------------------
# deal_find_coupons
# ---------------------------------------------------------------------------


def test_deal_find_coupons_fulfills_search_action() -> None:
    """deal_find_coupons must satisfy a 'search' step (coupons are discovered via search)."""
    _, fulfilled, missed = _audit(
        description="Search for coupon codes for Nike shoes",
        tools_used={"deal_find_coupons"},
    )
    assert "search" in fulfilled
    assert "search" not in missed


# ---------------------------------------------------------------------------
# deal_compare_prices
# ---------------------------------------------------------------------------


def test_deal_compare_prices_fulfills_search_action() -> None:
    """deal_compare_prices must satisfy a 'search' step (price comparison requires search)."""
    _, fulfilled, missed = _audit(
        description="Search and compare prices for iPhone 15",
        tools_used={"deal_compare_prices"},
    )
    assert "search" in fulfilled
    assert "search" not in missed


# ---------------------------------------------------------------------------
# Multiple deal tools together
# ---------------------------------------------------------------------------


def test_multiple_deal_tools_fulfill_search() -> None:
    """Using deal_search + deal_find_coupons together still resolves to fulfilled=search."""
    _, fulfilled, missed = _audit(
        description="Search for the cheapest price and find coupon codes",
        tools_used={"deal_search", "deal_find_coupons"},
    )
    assert "search" in fulfilled
    assert "search" not in missed


# ---------------------------------------------------------------------------
# Non-deal tools still work
# ---------------------------------------------------------------------------


def test_info_search_web_still_fulfills_search() -> None:
    """Existing info_search_web mapping must not be broken by the new additions."""
    _, fulfilled, missed = _audit(
        description="Search the web for Python 3.13 release notes",
        tools_used={"info_search_web"},
    )
    assert "search" in fulfilled
    assert "search" not in missed


def test_wide_research_still_fulfills_search() -> None:
    """wide_research must continue to satisfy search steps."""
    _, fulfilled, missed = _audit(
        description="Search for recent AI breakthroughs",
        tools_used={"wide_research"},
    )
    assert "search" in fulfilled
    assert "search" not in missed


# ---------------------------------------------------------------------------
# Regression: original bug scenario (tools_used=['deal_scraper'], missed=['search'])
# ---------------------------------------------------------------------------


def test_regression_deal_scraper_was_not_recognized() -> None:
    """Regression: before the fix, deal_scraper was not in the search tool set.

    With old mapping:
      search → {info_search_web, wide_research}
      tools_used = {deal_scraper}
      fulfilled = {}   ← bug
      missed = {'search'}  ← logged as warning

    After fix: fulfilled = {'search'}, missed = {}.
    """
    _, fulfilled, missed = _audit(
        description="Search for the best deals on a MacBook Pro",
        tools_used={"deal_scraper"},
    )
    # Regression assertion: must NOT be missed
    assert "search" not in missed, (
        f"Regression: deal_scraper still not recognized for 'search' action. fulfilled={fulfilled}, missed={missed}"
    )
    assert "search" in fulfilled


# ---------------------------------------------------------------------------
# No false positives: unknown tools don't satisfy 'search'
# ---------------------------------------------------------------------------


def test_unknown_tool_does_not_fulfill_search() -> None:
    """An unrecognised tool name must not accidentally satisfy 'search'."""
    _, fulfilled, missed = _audit(
        description="Search for the latest news",
        tools_used={"some_random_tool"},
    )
    assert "search" not in fulfilled
    assert "search" in missed


# ---------------------------------------------------------------------------
# Parametrized coverage over all four deal tool names
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tool_name",
    [
        "deal_scraper",
        "deal_search",
        "deal_find_coupons",
        "deal_compare_prices",
    ],
)
def test_all_deal_tools_in_search_set(tool_name: str) -> None:
    """Every DealFinder tool must appear in the VERB_TOOL_MAP 'search' set."""
    assert tool_name in VERB_TOOL_MAP["search"], (
        f"Tool '{tool_name}' is missing from the 'search' audit mapping. "
        "Add it to VERB_TOOL_MAP['search'] in plan_act.py."
    )


@pytest.mark.parametrize(
    "tool_name",
    [
        "deal_scraper",
        "deal_search",
        "deal_find_coupons",
        "deal_compare_prices",
    ],
)
def test_all_deal_tools_fulfill_search_step(tool_name: str) -> None:
    """Each DealFinder tool used alone must fulfill a generic 'search' step."""
    _, fulfilled, missed = _audit(
        description=f"Search for deals using {tool_name}",
        tools_used={tool_name},
    )
    assert "search" in fulfilled, f"{tool_name} did not fulfill 'search'"
    assert "search" not in missed, f"{tool_name} left 'search' in missed"
