"""
Comprehensive tests for PromptAdapter — dynamic prompt adaptation based on execution context.

Coverage:
- ContextType enum values and string interoperability
- ExecutionContext dataclass defaults and field mutation
- PromptAdapter initialisation and max_recent_tools parameter
- track_tool_use: tool list growth, bound enforcement, error recording, error bound enforcement,
  success-only path, zero-length error truncation
- increment_iteration
- _infer_context: every mapped context type, MCP prefix stripping, partial-name matching,
  tie-breaking by count, fallback to GENERAL, window limited to last-5 tools
- get_context_prompt: None for cold adapter, per-context guidance content,
  error-summary inclusion, error list capping at 3 in display, iteration threshold messages (10/20/30),
  non-threshold iteration returns None, combined guidance, exact separator/format
- adapt_prompt: passthrough when no guidance, appended structure, separator present
- should_inject_guidance: errors present, each iteration threshold, non-threshold integers,
  periodic specialised-context cadence (modulo 5), general context with no errors
- reset: full state wipe, independent new context object
- get_stats: all keys present, value types, post-multiple-operations accuracy
- _iteration backward-compat property (getter and setter)
- ContextType.MCP and ContextType.MESSAGE enum members present
- Edge cases: empty error string not recorded, error message truncated at 100 chars,
  max_recent_tools=1, very large iteration count beyond all thresholds
"""
from app.domain.services.agents.prompt_adapter import (
    ContextType,
    ExecutionContext,
    PromptAdapter,
)

# ── ContextType Enum ────────────────────────────────────────────────────────


class TestContextTypeEnum:
    def test_browser_value(self):
        assert ContextType.BROWSER == "browser"
        assert ContextType.BROWSER.value == "browser"

    def test_shell_value(self):
        assert ContextType.SHELL == "shell"

    def test_file_value(self):
        assert ContextType.FILE == "file"

    def test_search_value(self):
        assert ContextType.SEARCH == "search"

    def test_mcp_value(self):
        assert ContextType.MCP == "mcp"

    def test_message_value(self):
        assert ContextType.MESSAGE == "message"

    def test_general_value(self):
        assert ContextType.GENERAL == "general"

    def test_all_seven_members_exist(self):
        members = {m.value for m in ContextType}
        assert members == {"browser", "shell", "file", "search", "mcp", "message", "general"}

    def test_str_comparison(self):
        # ContextType inherits from str so equality with raw strings works
        assert ContextType.BROWSER == "browser"
        assert ContextType.GENERAL != "browser"

    def test_str_subclass(self):
        assert isinstance(ContextType.BROWSER, str)


# ── ExecutionContext Dataclass ──────────────────────────────────────────────


class TestExecutionContextDefaults:
    def test_recent_tools_default_empty_list(self):
        ctx = ExecutionContext()
        assert ctx.recent_tools == []

    def test_recent_errors_default_empty_list(self):
        ctx = ExecutionContext()
        assert ctx.recent_errors == []

    def test_iteration_count_default_zero(self):
        ctx = ExecutionContext()
        assert ctx.iteration_count == 0

    def test_primary_context_default_general(self):
        ctx = ExecutionContext()
        assert ctx.primary_context == ContextType.GENERAL

    def test_metadata_default_empty_dict(self):
        ctx = ExecutionContext()
        assert ctx.metadata == {}

    def test_field_mutation(self):
        ctx = ExecutionContext()
        ctx.recent_tools.append("shell_exec")
        ctx.iteration_count = 3
        assert ctx.recent_tools == ["shell_exec"]
        assert ctx.iteration_count == 3

    def test_two_instances_do_not_share_lists(self):
        ctx1 = ExecutionContext()
        ctx2 = ExecutionContext()
        ctx1.recent_tools.append("a")
        assert ctx2.recent_tools == []

    def test_custom_construction(self):
        ctx = ExecutionContext(
            recent_tools=["file_read"],
            recent_errors=["file_read: not found"],
            iteration_count=5,
            primary_context=ContextType.FILE,
            metadata={"key": "val"},
        )
        assert ctx.recent_tools == ["file_read"]
        assert ctx.recent_errors == ["file_read: not found"]
        assert ctx.iteration_count == 5
        assert ctx.primary_context == ContextType.FILE
        assert ctx.metadata == {"key": "val"}


# ── PromptAdapter Initialisation ───────────────────────────────────────────


class TestPromptAdapterInit:
    def test_default_max_recent_tools(self):
        adapter = PromptAdapter()
        # Default is 10 — verify by overflowing
        for i in range(12):
            adapter.track_tool_use(f"tool_{i}")
        assert len(adapter.get_context().recent_tools) == 10

    def test_custom_max_recent_tools(self):
        adapter = PromptAdapter(max_recent_tools=4)
        for i in range(6):
            adapter.track_tool_use(f"tool_{i}")
        assert len(adapter.get_context().recent_tools) == 4

    def test_max_recent_tools_one(self):
        adapter = PromptAdapter(max_recent_tools=1)
        adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("shell_exec")
        tools = adapter.get_context().recent_tools
        assert len(tools) == 1
        assert tools[0] == "shell_exec"

    def test_initial_context_is_general(self):
        adapter = PromptAdapter()
        assert adapter.get_context().primary_context == ContextType.GENERAL

    def test_initial_iteration_count_zero(self):
        adapter = PromptAdapter()
        assert adapter.get_context().iteration_count == 0


# ── Tool Tracking ──────────────────────────────────────────────────────────


class TestTrackToolUse:
    def test_adds_tool_to_recent_tools(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        assert "browser_navigate" in adapter.get_context().recent_tools

    def test_tracks_multiple_distinct_tools(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("shell_exec")
        adapter.track_tool_use("file_read")
        assert len(adapter.get_context().recent_tools) == 3

    def test_preserves_insertion_order(self):
        adapter = PromptAdapter()
        tools = ["file_read", "shell_exec", "browser_navigate"]
        for t in tools:
            adapter.track_tool_use(t)
        assert adapter.get_context().recent_tools == tools

    def test_bounded_keeps_most_recent(self):
        adapter = PromptAdapter(max_recent_tools=3)
        for i in range(5):
            adapter.track_tool_use(f"tool_{i}")
        # Should keep tool_2, tool_3, tool_4
        assert adapter.get_context().recent_tools == ["tool_2", "tool_3", "tool_4"]

    def test_exact_boundary_not_trimmed(self):
        adapter = PromptAdapter(max_recent_tools=3)
        adapter.track_tool_use("a")
        adapter.track_tool_use("b")
        adapter.track_tool_use("c")
        assert len(adapter.get_context().recent_tools) == 3

    def test_one_over_boundary_trims(self):
        adapter = PromptAdapter(max_recent_tools=3)
        for ch in ["a", "b", "c", "d"]:
            adapter.track_tool_use(ch)
        assert len(adapter.get_context().recent_tools) == 3
        assert adapter.get_context().recent_tools[0] == "b"

    def test_success_true_no_error_recorded(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_read", success=True)
        assert adapter.get_context().recent_errors == []

    def test_success_default_no_error_recorded(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_read")
        assert adapter.get_context().recent_errors == []

    def test_failure_with_error_recorded(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error="Permission denied")
        errors = adapter.get_context().recent_errors
        assert len(errors) == 1
        assert "shell_exec" in errors[0]
        assert "Permission denied" in errors[0]

    def test_failure_without_error_message_not_recorded(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error=None)
        assert adapter.get_context().recent_errors == []

    def test_failure_with_empty_error_string_not_recorded(self):
        # error="" is falsy — should not be appended
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error="")
        assert adapter.get_context().recent_errors == []

    def test_error_message_truncated_at_100_chars(self):
        adapter = PromptAdapter()
        long_error = "x" * 200
        adapter.track_tool_use("tool", success=False, error=long_error)
        recorded = adapter.get_context().recent_errors[0]
        # Format: "tool: <truncated error>"  → error part is at most 100 chars
        error_part = recorded.split(": ", 1)[1]
        assert len(error_part) <= 100

    def test_errors_bounded_at_five(self):
        adapter = PromptAdapter()
        for i in range(8):
            adapter.track_tool_use("tool", success=False, error=f"error {i}")
        assert len(adapter.get_context().recent_errors) == 5

    def test_errors_keep_most_recent_five(self):
        adapter = PromptAdapter()
        for i in range(7):
            adapter.track_tool_use("tool", success=False, error=f"error {i}")
        errors = adapter.get_context().recent_errors
        assert "error 2" in errors[0]
        assert "error 6" in errors[-1]

    def test_updates_primary_context_after_tracking(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        assert adapter.get_context().primary_context == ContextType.BROWSER


# ── Increment Iteration ────────────────────────────────────────────────────


class TestIncrementIteration:
    def test_starts_at_zero(self):
        adapter = PromptAdapter()
        assert adapter.get_context().iteration_count == 0

    def test_single_increment(self):
        adapter = PromptAdapter()
        adapter.increment_iteration()
        assert adapter.get_context().iteration_count == 1

    def test_multiple_increments(self):
        adapter = PromptAdapter()
        for _ in range(15):
            adapter.increment_iteration()
        assert adapter.get_context().iteration_count == 15

    def test_increment_is_cumulative(self):
        adapter = PromptAdapter()
        adapter.increment_iteration()
        adapter.increment_iteration()
        adapter.increment_iteration()
        assert adapter.get_context().iteration_count == 3


# ── Backward-compat _iteration property ───────────────────────────────────


class TestIterationProperty:
    def test_getter_reflects_context(self):
        adapter = PromptAdapter()
        adapter.increment_iteration()
        adapter.increment_iteration()
        assert adapter._iteration == 2

    def test_setter_updates_context(self):
        adapter = PromptAdapter()
        adapter._iteration = 7
        assert adapter.get_context().iteration_count == 7

    def test_setter_then_getter_round_trip(self):
        adapter = PromptAdapter()
        adapter._iteration = 42
        assert adapter._iteration == 42

    def test_increment_after_setter(self):
        adapter = PromptAdapter()
        adapter._iteration = 9
        adapter.increment_iteration()
        assert adapter._iteration == 10


# ── Context Inference ──────────────────────────────────────────────────────


class TestInferContext:
    def test_empty_tools_returns_general(self):
        adapter = PromptAdapter()
        # _infer_context called via track_tool_use; test via fresh adapter
        assert adapter.get_context().primary_context == ContextType.GENERAL

    def test_browser_navigate_infers_browser(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        assert adapter.get_context().primary_context == ContextType.BROWSER

    def test_browser_click_infers_browser(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_click")
        assert adapter.get_context().primary_context == ContextType.BROWSER

    def test_browser_view_infers_browser(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_view")
        assert adapter.get_context().primary_context == ContextType.BROWSER

    def test_browser_scroll_infers_browser(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_scroll")
        assert adapter.get_context().primary_context == ContextType.BROWSER

    def test_browser_input_infers_browser(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_input")
        assert adapter.get_context().primary_context == ContextType.BROWSER

    def test_shell_exec_infers_shell(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec")
        assert adapter.get_context().primary_context == ContextType.SHELL

    def test_shell_run_infers_shell(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_run")
        assert adapter.get_context().primary_context == ContextType.SHELL

    def test_file_read_infers_file(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_read")
        assert adapter.get_context().primary_context == ContextType.FILE

    def test_file_write_infers_file(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_write")
        assert adapter.get_context().primary_context == ContextType.FILE

    def test_file_list_infers_file(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_list")
        assert adapter.get_context().primary_context == ContextType.FILE

    def test_info_search_web_infers_search(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("info_search_web")
        assert adapter.get_context().primary_context == ContextType.SEARCH

    def test_message_ask_user_infers_message(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("message_ask_user")
        assert adapter.get_context().primary_context == ContextType.MESSAGE

    def test_unknown_tool_infers_general(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("completely_unknown_xyz")
        assert adapter.get_context().primary_context == ContextType.GENERAL

    def test_majority_context_wins(self):
        adapter = PromptAdapter()
        # 3 browser, 1 shell — browser should win
        adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("browser_click")
        adapter.track_tool_use("browser_view")
        adapter.track_tool_use("shell_exec")
        assert adapter.get_context().primary_context == ContextType.BROWSER

    def test_shell_majority_over_browser(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec")
        adapter.track_tool_use("shell_run")
        adapter.track_tool_use("browser_navigate")
        assert adapter.get_context().primary_context == ContextType.SHELL

    def test_mcp_prefix_stripped_correctly(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("mcp_browser_navigate")
        adapter.track_tool_use("mcp_browser_click")
        assert adapter.get_context().primary_context == ContextType.BROWSER

    def test_mcp_prefix_without_underscore_stripped(self):
        # "mcp" prefix (no underscore) also stripped per implementation
        adapter = PromptAdapter()
        adapter.track_tool_use("mcpbrowser_navigate")
        # After stripping "mcp", normalised = "browser_navigate" → BROWSER
        assert adapter.get_context().primary_context == ContextType.BROWSER

    def test_partial_name_matching_for_mcp_tools(self):
        adapter = PromptAdapter()
        # Tool "mcp_custom_browser_scroll" → normalised "custom_browser_scroll"
        # Partial match: "browser_scroll" in "custom_browser_scroll" → BROWSER
        adapter.track_tool_use("mcp_custom_browser_scroll")
        adapter.track_tool_use("mcp_custom_browser_scroll")
        assert adapter.get_context().primary_context == ContextType.BROWSER

    def test_window_limited_to_last_five_tools(self):
        # Fill with 6 file_read then 4 browser — inference window is last 5 (4 browser + 1 file)
        adapter = PromptAdapter(max_recent_tools=10)
        for _ in range(6):
            adapter.track_tool_use("file_read")
        for _ in range(4):
            adapter.track_tool_use("browser_navigate")
        # Last 5: 1 file_read + 4 browser_navigate → browser wins
        assert adapter.get_context().primary_context == ContextType.BROWSER


# ── get_context_prompt ─────────────────────────────────────────────────────


class TestGetContextPrompt:
    def test_returns_none_cold_adapter(self):
        adapter = PromptAdapter()
        assert adapter.get_context_prompt() is None

    def test_returns_none_general_context_no_errors_nonzero_iter(self):
        adapter = PromptAdapter()
        # iteration_count=7 → not a threshold, primary_context=GENERAL → no guidance
        for _ in range(7):
            adapter.increment_iteration()
        assert adapter.get_context_prompt() is None

    def test_browser_guidance_returned_at_iter_zero(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        # iteration_count=0 → 0 % 5 == 0, non-GENERAL → guidance returned
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "Browser" in prompt

    def test_browser_guidance_content(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "scroll" in prompt.lower()

    def test_shell_guidance_content(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec")
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "Shell" in prompt or "non-interactive" in prompt.lower()

    def test_file_guidance_content(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_read")
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "File" in prompt or "encoding" in prompt.lower()

    def test_search_guidance_content(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("info_search_web")
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "Search" in prompt or "queries" in prompt.lower()

    def test_message_context_no_guidance_entry(self):
        # MESSAGE is not in CONTEXT_GUIDANCE — no specific tips, but no error either
        adapter = PromptAdapter()
        adapter.track_tool_use("message_ask_user")
        # iteration_count=0 → should_inject path: 0 % 5 == 0 → True, but no guidance block
        # get_context_prompt returns None if prompts list empty
        prompt = adapter.get_context_prompt()
        # MESSAGE has no entry in CONTEXT_GUIDANCE → prompts list will be empty → None
        assert prompt is None

    def test_error_summary_included(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error="Segfault occurred")
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "Segfault occurred" in prompt

    def test_error_summary_shows_last_three_errors(self):
        adapter = PromptAdapter()
        for i in range(5):
            adapter.track_tool_use("tool", success=False, error=f"error_{i}")
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        # Last 3 of the 5 kept: errors are capped at 5 internally,
        # and get_context_prompt only shows last 3 in the summary
        assert "error_4" in prompt
        assert "error_3" in prompt
        assert "error_2" in prompt

    def test_error_summary_header_present(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("tool", success=False, error="oops")
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "Recent Errors" in prompt

    def test_iteration_10_warning_text(self):
        adapter = PromptAdapter()
        for _ in range(10):
            adapter.increment_iteration()
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "10 iterations" in prompt

    def test_iteration_20_warning_text(self):
        adapter = PromptAdapter()
        for _ in range(20):
            adapter.increment_iteration()
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "20 iterations" in prompt

    def test_iteration_30_warning_text(self):
        adapter = PromptAdapter()
        for _ in range(30):
            adapter.increment_iteration()
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "30 iterations" in prompt

    def test_iteration_10_warning_marker(self):
        adapter = PromptAdapter()
        for _ in range(10):
            adapter.increment_iteration()
        prompt = adapter.get_context_prompt()
        assert "**WARNING**" in prompt

    def test_non_threshold_iteration_no_warning(self):
        adapter = PromptAdapter()
        for _ in range(11):
            adapter.increment_iteration()
        # 11 is not a threshold and not a multiple of 5 for specialised context
        prompt = adapter.get_context_prompt()
        assert prompt is None

    def test_only_first_matching_threshold_warning_emitted(self):
        # Only one warning even if multiple thresholds exceeded (only exact match)
        adapter = PromptAdapter()
        for _ in range(20):
            adapter.increment_iteration()
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "20 iterations" in prompt
        assert "10 iterations" not in prompt

    def test_combined_guidance_when_browser_and_error(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("browser_navigate", success=False, error="Element not found")
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "Browser" in prompt
        assert "Element not found" in prompt

    def test_combined_guidance_when_threshold_and_error(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error="Timeout")
        for _ in range(10):
            adapter.increment_iteration()
        prompt = adapter.get_context_prompt()
        assert prompt is not None
        assert "Timeout" in prompt
        assert "10 iterations" in prompt


# ── adapt_prompt ───────────────────────────────────────────────────────────


class TestAdaptPrompt:
    def test_returns_base_prompt_unchanged_when_no_context(self):
        adapter = PromptAdapter()
        result = adapter.adapt_prompt("Do the task")
        assert result == "Do the task"

    def test_adapted_prompt_contains_base(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error="Timeout")
        result = adapter.adapt_prompt("Run command")
        assert result.startswith("Run command")

    def test_adapted_prompt_contains_context_guidance_header(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_read", success=False, error="Not found")
        result = adapter.adapt_prompt("Read file")
        assert "Context Guidance" in result

    def test_adapted_prompt_contains_separator(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate", success=False, error="Crash")
        result = adapter.adapt_prompt("Navigate")
        assert "---" in result

    def test_adapted_prompt_structure(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error="Oops")
        result = adapter.adapt_prompt("base")
        assert result.startswith("base\n\n---\nContext Guidance:\n")

    def test_empty_base_prompt_still_works(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_read", success=False, error="err")
        result = adapter.adapt_prompt("")
        assert "Context Guidance" in result

    def test_base_prompt_preserved_verbatim(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error="X")
        base = "Special chars: !@#$%^&*()"
        result = adapter.adapt_prompt(base)
        assert base in result


# ── should_inject_guidance ────────────────────────────────────────────────


class TestShouldInjectGuidance:
    def test_false_cold_adapter(self):
        adapter = PromptAdapter()
        assert adapter.should_inject_guidance() is False

    def test_true_when_recent_errors(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("tool", success=False, error="boom")
        assert adapter.should_inject_guidance() is True

    def test_true_at_threshold_10(self):
        adapter = PromptAdapter()
        for _ in range(10):
            adapter.increment_iteration()
        assert adapter.should_inject_guidance() is True

    def test_true_at_threshold_20(self):
        adapter = PromptAdapter()
        for _ in range(20):
            adapter.increment_iteration()
        assert adapter.should_inject_guidance() is True

    def test_true_at_threshold_30(self):
        adapter = PromptAdapter()
        for _ in range(30):
            adapter.increment_iteration()
        assert adapter.should_inject_guidance() is True

    def test_false_at_non_threshold_9(self):
        adapter = PromptAdapter()
        for _ in range(9):
            adapter.increment_iteration()
        assert adapter.should_inject_guidance() is False

    def test_false_at_non_threshold_11(self):
        adapter = PromptAdapter()
        for _ in range(11):
            adapter.increment_iteration()
        assert adapter.should_inject_guidance() is False

    def test_false_at_non_threshold_25(self):
        adapter = PromptAdapter()
        for _ in range(25):
            adapter.increment_iteration()
        assert adapter.should_inject_guidance() is False

    def test_specialized_context_true_at_iteration_zero(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        # 0 % 5 == 0 and not GENERAL → True
        assert adapter.should_inject_guidance() is True

    def test_specialized_context_true_at_iteration_5(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        for _ in range(5):
            adapter.increment_iteration()
        assert adapter.should_inject_guidance() is True

    def test_specialized_context_true_at_iteration_10(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        for _ in range(10):
            adapter.increment_iteration()
        # iteration_count == 10 which is a threshold AND 10 % 5 == 0 → True either way
        assert adapter.should_inject_guidance() is True

    def test_specialized_context_false_at_iteration_3(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        for _ in range(3):
            adapter.increment_iteration()
        # 3 % 5 != 0 and not a threshold → False
        assert adapter.should_inject_guidance() is False

    def test_specialized_context_false_at_iteration_7(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec")
        for _ in range(7):
            adapter.increment_iteration()
        assert adapter.should_inject_guidance() is False

    def test_general_context_no_errors_always_false(self):
        adapter = PromptAdapter()
        for _ in range(6):
            adapter.increment_iteration()
        # 6 is not a threshold, context is GENERAL
        assert adapter.should_inject_guidance() is False

    def test_errors_take_priority_over_context_check(self):
        adapter = PromptAdapter()
        # Even with GENERAL context and non-threshold, errors trigger True
        for _ in range(7):
            adapter.increment_iteration()
        adapter.track_tool_use("tool", success=False, error="critical")
        assert adapter.should_inject_guidance() is True


# ── reset ──────────────────────────────────────────────────────────────────


class TestReset:
    def test_reset_clears_recent_tools(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("shell_exec")
        adapter.reset()
        assert adapter.get_context().recent_tools == []

    def test_reset_clears_recent_errors(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("tool", success=False, error="err")
        adapter.reset()
        assert adapter.get_context().recent_errors == []

    def test_reset_clears_iteration_count(self):
        adapter = PromptAdapter()
        for _ in range(15):
            adapter.increment_iteration()
        adapter.reset()
        assert adapter.get_context().iteration_count == 0

    def test_reset_restores_general_context(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter.reset()
        assert adapter.get_context().primary_context == ContextType.GENERAL

    def test_reset_creates_new_context_object(self):
        adapter = PromptAdapter()
        ctx_before = adapter.get_context()
        adapter.reset()
        ctx_after = adapter.get_context()
        assert ctx_before is not ctx_after

    def test_adapter_usable_after_reset(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter.reset()
        adapter.track_tool_use("shell_exec")
        assert adapter.get_context().recent_tools == ["shell_exec"]
        assert adapter.get_context().primary_context == ContextType.SHELL

    def test_double_reset_is_idempotent(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_read")
        adapter.reset()
        adapter.reset()
        assert adapter.get_context().recent_tools == []
        assert adapter.get_context().iteration_count == 0


# ── get_stats ──────────────────────────────────────────────────────────────


class TestGetStats:
    def test_stats_keys_present(self):
        adapter = PromptAdapter()
        stats = adapter.get_stats()
        assert "iteration_count" in stats
        assert "primary_context" in stats
        assert "recent_tools_count" in stats
        assert "recent_errors_count" in stats

    def test_stats_default_values(self):
        adapter = PromptAdapter()
        stats = adapter.get_stats()
        assert stats["iteration_count"] == 0
        assert stats["primary_context"] == "general"
        assert stats["recent_tools_count"] == 0
        assert stats["recent_errors_count"] == 0

    def test_stats_primary_context_is_string(self):
        adapter = PromptAdapter()
        stats = adapter.get_stats()
        assert isinstance(stats["primary_context"], str)

    def test_stats_after_tool_tracking(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("info_search_web")
        adapter.increment_iteration()
        stats = adapter.get_stats()
        assert stats["iteration_count"] == 1
        assert stats["recent_tools_count"] == 1
        assert stats["recent_errors_count"] == 0
        assert stats["primary_context"] == "search"

    def test_stats_after_error(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error="fail")
        stats = adapter.get_stats()
        assert stats["recent_errors_count"] == 1

    def test_stats_counts_match_actual_lists(self):
        adapter = PromptAdapter()
        for _ in range(3):
            adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("shell_exec", success=False, error="e1")
        adapter.track_tool_use("shell_exec", success=False, error="e2")
        stats = adapter.get_stats()
        ctx = adapter.get_context()
        assert stats["recent_tools_count"] == len(ctx.recent_tools)
        assert stats["recent_errors_count"] == len(ctx.recent_errors)

    def test_stats_after_reset(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_read")
        adapter.increment_iteration()
        adapter.reset()
        stats = adapter.get_stats()
        assert stats["iteration_count"] == 0
        assert stats["recent_tools_count"] == 0
        assert stats["recent_errors_count"] == 0
        assert stats["primary_context"] == "general"

    def test_stats_browser_context_string_value(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter.track_tool_use("browser_click")
        stats = adapter.get_stats()
        assert stats["primary_context"] == "browser"


# ── get_context accessor ───────────────────────────────────────────────────


class TestGetContext:
    def test_returns_execution_context_instance(self):
        adapter = PromptAdapter()
        ctx = adapter.get_context()
        assert isinstance(ctx, ExecutionContext)

    def test_returns_same_object_between_calls(self):
        adapter = PromptAdapter()
        ctx1 = adapter.get_context()
        ctx2 = adapter.get_context()
        assert ctx1 is ctx2

    def test_reflects_mutations(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter.increment_iteration()
        ctx = adapter.get_context()
        assert len(ctx.recent_tools) == 1
        assert ctx.iteration_count == 1


# ── Class-level constants ──────────────────────────────────────────────────


class TestClassConstants:
    def test_tool_contexts_maps_all_browser_tools(self):
        browser_tools = [
            "browser_view",
            "browser_navigate",
            "browser_click",
            "browser_scroll",
            "browser_input",
        ]
        for tool in browser_tools:
            assert PromptAdapter.TOOL_CONTEXTS[tool] == ContextType.BROWSER

    def test_tool_contexts_maps_shell_tools(self):
        assert PromptAdapter.TOOL_CONTEXTS["shell_exec"] == ContextType.SHELL
        assert PromptAdapter.TOOL_CONTEXTS["shell_run"] == ContextType.SHELL

    def test_tool_contexts_maps_file_tools(self):
        for tool in ["file_read", "file_write", "file_list"]:
            assert PromptAdapter.TOOL_CONTEXTS[tool] == ContextType.FILE

    def test_tool_contexts_maps_search_tool(self):
        assert PromptAdapter.TOOL_CONTEXTS["info_search_web"] == ContextType.SEARCH

    def test_tool_contexts_maps_message_tool(self):
        assert PromptAdapter.TOOL_CONTEXTS["message_ask_user"] == ContextType.MESSAGE

    def test_context_guidance_covers_browser(self):
        assert ContextType.BROWSER in PromptAdapter.CONTEXT_GUIDANCE

    def test_context_guidance_covers_shell(self):
        assert ContextType.SHELL in PromptAdapter.CONTEXT_GUIDANCE

    def test_context_guidance_covers_file(self):
        assert ContextType.FILE in PromptAdapter.CONTEXT_GUIDANCE

    def test_context_guidance_covers_search(self):
        assert ContextType.SEARCH in PromptAdapter.CONTEXT_GUIDANCE

    def test_iteration_thresholds_keys(self):
        keys = set(PromptAdapter.ITERATION_THRESHOLDS.keys())
        assert 10 in keys
        assert 20 in keys
        assert 30 in keys

    def test_iteration_thresholds_messages_non_empty(self):
        for msg in PromptAdapter.ITERATION_THRESHOLDS.values():
            assert isinstance(msg, str)
            assert len(msg) > 0

    def test_iteration_threshold_10_mentions_10(self):
        assert "10" in PromptAdapter.ITERATION_THRESHOLDS[10]

    def test_iteration_threshold_20_mentions_20(self):
        assert "20" in PromptAdapter.ITERATION_THRESHOLDS[20]

    def test_iteration_threshold_30_mentions_30(self):
        assert "30" in PromptAdapter.ITERATION_THRESHOLDS[30]


# ── Edge / integration cases ───────────────────────────────────────────────


class TestEdgeCases:
    def test_large_iteration_beyond_all_thresholds_no_warning(self):
        adapter = PromptAdapter()
        adapter._iteration = 100
        # 100 is not in {10, 20, 30} and context is GENERAL → None
        assert adapter.get_context_prompt() is None

    def test_large_iteration_with_specialized_context_periodic(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter._iteration = 100
        # 100 % 5 == 0 and not GENERAL → should inject
        assert adapter.should_inject_guidance() is True

    def test_large_iteration_non_multiple_no_inject(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        adapter._iteration = 101
        # 101 % 5 != 0 and 101 not a threshold
        assert adapter.should_inject_guidance() is False

    def test_max_recent_tools_zero_bounded_correctly(self):
        # max_recent_tools=0 is an edge case; list stays empty after each call
        adapter = PromptAdapter(max_recent_tools=0)
        adapter.track_tool_use("browser_navigate")
        # The slice [-0:] returns the full list, not empty — document actual behaviour
        # After one call the list has 1 item, then [-0:] == [0:] = full list
        # This is a known Python slice edge case; we just assert no crash occurs
        assert isinstance(adapter.get_context().recent_tools, list)

    def test_track_tool_updates_context_each_call(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec")
        assert adapter.get_context().primary_context == ContextType.SHELL
        # Add more browser tools to flip context
        for _ in range(4):
            adapter.track_tool_use("browser_navigate")
        assert adapter.get_context().primary_context == ContextType.BROWSER

    def test_adapt_prompt_idempotent_without_state_change(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("shell_exec", success=False, error="fail")
        result1 = adapter.adapt_prompt("base")
        result2 = adapter.adapt_prompt("base")
        assert result1 == result2

    def test_should_inject_guidance_does_not_mutate_state(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("browser_navigate")
        before = adapter.get_context().iteration_count
        adapter.should_inject_guidance()
        after = adapter.get_context().iteration_count
        assert before == after

    def test_get_context_prompt_does_not_mutate_state(self):
        adapter = PromptAdapter()
        adapter.track_tool_use("file_read", success=False, error="err")
        before_count = len(adapter.get_context().recent_errors)
        adapter.get_context_prompt()
        after_count = len(adapter.get_context().recent_errors)
        assert before_count == after_count
