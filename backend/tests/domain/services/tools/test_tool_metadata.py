"""Tests for Phase 1A: ToolDefaults, build_tool, BaseTool metadata, and cross-validation."""

from __future__ import annotations

import pytest

from app.domain.models.tool_permission import PermissionTier
from app.domain.services.tools.base import (
    BaseTool,
    ToolDefaults,
    build_tool,
    tool,
    validate_metadata_consistency,
)

# ── ToolDefaults ──────────────────────────────────────────────────────


class TestToolDefaults:
    def test_fail_closed_defaults(self):
        """All defaults should be fail-closed (safe)."""
        td = ToolDefaults()
        assert td.is_enabled is True
        assert td.is_read_only is False
        assert td.is_destructive is False
        assert td.is_concurrency_safe is False
        assert td.required_tier is PermissionTier.DANGER
        assert td.should_defer is False
        assert td.max_result_size_chars == 8000
        assert td.category == "general"
        assert td.user_facing_name == ""

    def test_custom_overrides(self):
        td = ToolDefaults(
            is_read_only=True,
            is_concurrency_safe=True,
            required_tier=PermissionTier.READ_ONLY,
            category="search",
            max_result_size_chars=30_000,
        )
        assert td.is_read_only is True
        assert td.is_concurrency_safe is True
        assert td.is_destructive is False  # Not overridden
        assert td.required_tier is PermissionTier.READ_ONLY
        assert td.category == "search"
        assert td.max_result_size_chars == 30_000

    def test_frozen(self):
        td = ToolDefaults()
        with pytest.raises(AttributeError):
            td.is_read_only = True  # type: ignore[misc]

    def test_to_dict_includes_all_fields(self):
        td = ToolDefaults(category="shell", should_defer=True)
        d = td.to_dict()
        assert "is_enabled" in d
        assert "is_read_only" in d
        assert "is_destructive" in d
        assert "is_concurrency_safe" in d
        assert "required_tier" in d
        assert "check_permissions" in d
        assert "user_facing_name" in d
        assert "max_result_size_chars" in d
        assert "should_defer" in d
        assert "category" in d
        assert d["category"] == "shell"
        assert d["should_defer"] is True


# ── build_tool ────────────────────────────────────────────────────────


class TestBuildTool:
    def test_returns_defaults_when_empty(self):
        merged = build_tool()
        assert merged["is_read_only"] is False
        assert merged["is_destructive"] is False
        assert merged["required_tier"] is PermissionTier.DANGER
        assert merged["max_result_size_chars"] == 8000

    def test_overrides_via_kwargs(self):
        merged = build_tool(is_read_only=True, required_tier=PermissionTier.READ_ONLY, category="file")
        assert merged["is_read_only"] is True
        assert merged["required_tier"] is PermissionTier.READ_ONLY
        assert merged["category"] == "file"
        assert merged["is_destructive"] is False  # Not overridden

    def test_tool_def_dict_merged(self):
        merged = build_tool({"name": "test_tool", "description": "A test"})
        assert merged["name"] == "test_tool"
        assert merged["description"] == "A test"
        assert merged["is_read_only"] is False  # Default preserved

    def test_kwargs_override_tool_def(self):
        merged = build_tool({"is_read_only": False}, is_read_only=True)
        assert merged["is_read_only"] is True  # Kwarg wins


# ── BaseTool metadata properties ──────────────────────────────────────


class TestBaseToolMetadata:
    def test_default_defaults_are_fail_closed(self):
        bt = BaseTool()
        assert bt.is_read_only is False
        assert bt.is_destructive is False
        assert bt.is_concurrency_safe is False
        assert bt.required_tier is PermissionTier.DANGER
        assert bt.should_defer is False
        assert bt.max_result_size_chars == 8000
        assert bt.tool_category == "general"
        assert bt.user_facing_name == ""  # Falls back to empty name

    def test_custom_defaults_propagate(self):
        bt = BaseTool(
            defaults=ToolDefaults(
                is_read_only=True,
                is_concurrency_safe=True,
                required_tier=PermissionTier.READ_ONLY,
                category="search",
                max_result_size_chars=20_000,
                user_facing_name="Search",
            )
        )
        assert bt.is_read_only is True
        assert bt.is_concurrency_safe is True
        assert bt.is_destructive is False
        assert bt.required_tier is PermissionTier.READ_ONLY
        assert bt.tool_category == "search"
        assert bt.max_result_size_chars == 20_000
        assert bt.user_facing_name == "Search"

    def test_user_facing_name_fallback(self):
        class MyTool(BaseTool):
            name = "my_tool"

        bt = MyTool()
        assert bt.user_facing_name == "my_tool"  # Falls back to name

    def test_is_enabled_default(self):
        bt = BaseTool()
        assert bt.is_enabled is True

    def test_disabled_tool(self):
        bt = BaseTool(defaults=ToolDefaults(is_enabled=False))
        assert bt.is_enabled is False


# ── @tool decorator metadata ──────────────────────────────────────────


class TestToolDecoratorMetadata:
    def test_decorator_stores_metadata(self):
        @tool(
            name="test_fn",
            description="A test function",
            parameters={},
            required=[],
            is_read_only=True,
            is_concurrency_safe=True,
            required_tier=PermissionTier.READ_ONLY,
        )
        async def test_fn():
            pass

        assert hasattr(test_fn, "_tool_metadata")
        meta: ToolDefaults = test_fn._tool_metadata
        assert meta.is_read_only is True
        assert meta.is_concurrency_safe is True
        assert meta.is_destructive is False  # Default
        assert meta.required_tier is PermissionTier.READ_ONLY

    def test_decorator_default_metadata_is_fail_closed(self):
        @tool(
            name="test_fn2",
            description="Another test",
            parameters={},
            required=[],
        )
        async def test_fn2():
            pass

        meta: ToolDefaults = test_fn2._tool_metadata
        assert meta.is_read_only is False
        assert meta.is_concurrency_safe is False
        assert meta.is_destructive is False
        assert meta.required_tier is PermissionTier.DANGER

    def test_decorator_destructive_flag(self):
        @tool(
            name="delete_fn",
            description="Deletes things",
            parameters={},
            required=[],
            is_destructive=True,
        )
        async def delete_fn():
            pass

        assert delete_fn._tool_metadata.is_destructive is True

    def test_decorator_preserves_function_name(self):
        @tool(
            name="my_func",
            description="Test",
            parameters={},
            required=[],
            is_read_only=True,
        )
        async def my_func():
            pass

        assert my_func._function_name == "my_func"
        assert hasattr(my_func, "_tool_schema")


# ── get_function_metadata ─────────────────────────────────────────────


class TestGetFunctionMetadata:
    def test_returns_function_metadata_when_present(self):
        class MyTool(BaseTool):
            name = "test"

            @tool(
                name="read_fn",
                description="Reads",
                parameters={},
                required=[],
                is_read_only=True,
                is_concurrency_safe=True,
            )
            async def read_fn(self):
                pass

        bt = MyTool(defaults=ToolDefaults(is_destructive=True))
        meta = bt.get_function_metadata("read_fn")
        # Per-function metadata should win
        assert meta.is_read_only is True
        assert meta.is_concurrency_safe is True
        # Instance defaults should NOT bleed through
        assert meta.is_destructive is False

    def test_falls_back_to_instance_defaults(self):
        class MyTool(BaseTool):
            name = "test"

        bt = MyTool(defaults=ToolDefaults(is_destructive=True, category="shell"))
        meta = bt.get_function_metadata("unknown_fn")
        assert meta.is_destructive is True
        assert meta.category == "shell"


# ── validate_metadata_consistency ─────────────────────────────────────


class TestValidateMetadataConsistency:
    def test_no_warnings_for_consistent_metadata(self):
        class ReadTool(BaseTool):
            name = "file"

            @tool(
                name="file_read",
                description="Reads a file",
                parameters={},
                required=[],
                is_read_only=True,
                is_concurrency_safe=True,
            )
            async def file_read(self):
                pass

        warnings = validate_metadata_consistency([ReadTool()])
        # file_read IS in ToolName._READ_ONLY, so this should be consistent
        assert len(warnings) == 0

    def test_warns_on_read_only_mismatch(self):
        class ActionTool(BaseTool):
            name = "shell"

            @tool(
                name="shell_exec",
                description="Runs a command",
                parameters={},
                required=[],
                is_read_only=True,  # WRONG - shell_exec is NOT read-only in ToolName
            )
            async def shell_exec(self):
                pass

        warnings = validate_metadata_consistency([ActionTool()])
        assert any("shell_exec" in w and "is_read_only" in w for w in warnings)

    def test_warns_on_enum_says_read_only_but_metadata_says_no(self):
        class FileTool(BaseTool):
            name = "file"

            @tool(
                name="file_read",
                description="Reads a file",
                parameters={},
                required=[],
                # is_read_only defaults to False - but ToolName._READ_ONLY includes file_read
            )
            async def file_read(self):
                pass

        warnings = validate_metadata_consistency([FileTool()])
        assert any("file_read" in w and "is_read_only" in w for w in warnings)

    def test_skips_unknown_tool_names(self):
        class CustomTool(BaseTool):
            name = "custom"

            @tool(
                name="custom_do_stuff",
                description="Custom action",
                parameters={},
                required=[],
                is_read_only=True,
            )
            async def custom_do_stuff(self):
                pass

        # custom_do_stuff is not in ToolName enum - should be skipped
        warnings = validate_metadata_consistency([CustomTool()])
        assert len(warnings) == 0

    def test_empty_tool_list(self):
        warnings = validate_metadata_consistency([])
        assert len(warnings) == 0
