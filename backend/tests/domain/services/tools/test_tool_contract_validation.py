"""Smoke tests for WP-7: tool contract validation is now wired at startup.

Prior bug: validate_tool_contracts() was only reachable via warm_cache_for_common_tasks()
which had no call site — so contract validation never ran.

Fix: get_toolset_manager() calls warm_cache_for_common_tasks() on first creation so that
validate_tool_contracts() executes at startup and logs any schema violations.
"""

from unittest.mock import MagicMock, patch

import pytest

from app.domain.services.tools.dynamic_toolset import DynamicToolsetManager


def test_validate_tool_contracts_returns_list():
    """validate_tool_contracts() returns a list (empty = all tools valid)."""
    manager = DynamicToolsetManager()
    violations = manager.validate_tool_contracts()
    assert isinstance(violations, list)


def test_warm_cache_calls_validate_tool_contracts():
    """warm_cache_for_common_tasks() invokes validate_tool_contracts() internally."""
    manager = DynamicToolsetManager()

    called = []
    original = manager.validate_tool_contracts

    def recording_validate():
        called.append(True)
        return original()

    manager.validate_tool_contracts = recording_validate
    manager.warm_cache_for_common_tasks()
    assert len(called) == 1, "warm_cache_for_common_tasks() must call validate_tool_contracts()"


def test_get_toolset_manager_triggers_warm_cache_on_first_call():
    """get_toolset_manager() wires warm_cache_for_common_tasks() on first creation."""
    import app.domain.services.tools.dynamic_toolset as _mod

    # Reset module-level singleton so the factory path runs fresh
    original = _mod._toolset_manager
    _mod._toolset_manager = None
    try:
        warm_called = []
        original_class_init = DynamicToolsetManager.__init__

        def patched_warm(self_inner):
            warm_called.append(True)

        with patch.object(DynamicToolsetManager, "warm_cache_for_common_tasks", patched_warm):
            from app.domain.services.tools.dynamic_toolset import get_toolset_manager

            _mod._toolset_manager = None  # ensure fresh
            manager = get_toolset_manager()
            assert manager is not None
            assert len(warm_called) == 1, "warm_cache_for_common_tasks must be called once on first get"
    finally:
        _mod._toolset_manager = original


def test_validate_tool_contracts_detects_missing_description():
    """validate_tool_contracts() flags tools without a description."""
    manager = DynamicToolsetManager()

    # Register a tool with no description
    from app.domain.services.tools.dynamic_toolset import ToolInfo

    from app.domain.services.tools.dynamic_toolset import ToolCategory

    bad_tool = ToolInfo(
        name="bad_tool",
        description="",
        category=ToolCategory.SYSTEM,
        keywords=set(),
        schema={
            "type": "function",
            "function": {
                "name": "bad_tool",
                "description": "",
                "parameters": {"type": "object", "properties": {}},
            },
        },
    )
    manager._tools["bad_tool"] = bad_tool

    violations = manager.validate_tool_contracts()
    assert any("bad_tool" in v and "description" in v for v in violations), (
        "Expected a violation for a tool with no description"
    )


def test_validate_tool_contracts_detects_param_missing_type():
    """validate_tool_contracts() flags parameters without a 'type' field."""
    manager = DynamicToolsetManager()

    from app.domain.services.tools.dynamic_toolset import ToolInfo

    from app.domain.services.tools.dynamic_toolset import ToolCategory

    bad_param_tool = ToolInfo(
        name="param_tool",
        description="Valid description",
        category=ToolCategory.SYSTEM,
        keywords={"param"},
        schema={
            "type": "function",
            "function": {
                "name": "param_tool",
                "description": "Valid description",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            # 'type' intentionally missing
                            "description": "The search query",
                        }
                    },
                },
            },
        },
    )
    manager._tools["param_tool"] = param_tool = bad_param_tool

    violations = manager.validate_tool_contracts()
    assert any("param_tool" in v and "type" in v for v in violations), (
        "Expected a violation for a parameter missing 'type'"
    )
