"""Tests for pure functions and static methods in browser_agent.py.

Covers:
- extract_first_json: JSON extraction from raw LLM output
- BrowserAgentTool._normalize_action_name: action name aliasing
- BrowserAgentTool._coerce_int: numeric coercion
- BrowserAgentTool._first_int: first coercible int from varargs
- BrowserAgentTool._extract_action_from_dump: ActionModel dump parsing
- BrowserAgentTool._map_action_to_function: action → cursor + function name
- BrowserAgentTool._describe_action: human-readable step label generation
- BrowserAgentTool._extract_coordinates: coordinate resolution from args/metadata
- BrowserAgentTool._sanitize_task_prompt: task hardening suffix
- BrowserAgentTool._clean_llm_response: markdown fence removal
- _PROGRESS_QUEUE_MAX_SIZE constant
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.domain.services.tools.browser_agent import (
    _PROGRESS_QUEUE_MAX_SIZE,
    BROWSER_USE_AVAILABLE,
    BrowserAgentTool,
    extract_first_json,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool() -> BrowserAgentTool:
    """Return a BrowserAgentTool instance without a real browser_use dependency."""
    if not BROWSER_USE_AVAILABLE:
        pytest.skip("browser_use package is required for BrowserAgentTool instantiation")
    tool = BrowserAgentTool.__new__(BrowserAgentTool)
    # Populate only the attributes touched by the pure/static methods under test
    tool._settings = SimpleNamespace(
        browser_agent_max_steps=25,
        browser_agent_timeout=120,
        browser_agent_use_vision=False,
        browser_agent_max_failures=3,
        browser_agent_llm_timeout=90,
        browser_agent_step_timeout=30,
        browser_agent_flash_mode=False,
    )
    return tool


# ---------------------------------------------------------------------------
# _PROGRESS_QUEUE_MAX_SIZE
# ---------------------------------------------------------------------------


class TestProgressQueueMaxSize:
    def test_is_positive_integer(self) -> None:
        assert isinstance(_PROGRESS_QUEUE_MAX_SIZE, int)
        assert _PROGRESS_QUEUE_MAX_SIZE > 0

    def test_value_is_200(self) -> None:
        assert _PROGRESS_QUEUE_MAX_SIZE == 200


# ---------------------------------------------------------------------------
# extract_first_json
# ---------------------------------------------------------------------------


class TestExtractFirstJson:
    # --- basic valid JSON ---------------------------------------------------

    def test_plain_json_object_returned_unchanged(self) -> None:
        payload = '{"key": "value"}'
        assert extract_first_json(payload) == payload

    def test_plain_json_array_returned_unchanged(self) -> None:
        payload = "[1, 2, 3]"
        assert extract_first_json(payload) == payload

    # --- empty / falsy input ------------------------------------------------

    def test_empty_string_returned_as_is(self) -> None:
        assert extract_first_json("") == ""

    def test_none_like_falsy_returned_early(self) -> None:
        # The function guard is `if not text: return text`
        assert extract_first_json("") == ""

    # --- markdown code fence stripping --------------------------------------

    def test_strips_json_code_fence(self) -> None:
        text = '```json\n{"foo": 1}\n```'
        result = extract_first_json(text)
        assert result == '{"foo": 1}'

    def test_strips_plain_code_fence(self) -> None:
        text = '```\n{"bar": 2}\n```'
        result = extract_first_json(text)
        assert result == '{"bar": 2}'

    def test_strips_code_fence_no_newline(self) -> None:
        text = '```json{"baz": 3}```'
        result = extract_first_json(text)
        assert result == '{"baz": 3}'

    # --- think-tag stripping ------------------------------------------------

    def test_strips_think_block_before_json(self) -> None:
        text = '<think>reasoning here</think>{"answer": 42}'
        result = extract_first_json(text)
        assert result == '{"answer": 42}'

    def test_strips_multiline_think_block(self) -> None:
        text = '<think>\nline1\nline2\n</think>\n{"x": 1}'
        result = extract_first_json(text)
        assert result == '{"x": 1}'

    def test_think_block_with_code_fence(self) -> None:
        text = '<think>r</think>\n```json\n{"y": 2}\n```'
        result = extract_first_json(text)
        assert result == '{"y": 2}'

    # --- trailing characters ------------------------------------------------

    def test_extracts_json_with_trailing_text(self) -> None:
        text = '{"key": "val"} some trailing text'
        result = extract_first_json(text)
        assert result == '{"key": "val"}'

    def test_extracts_first_json_of_multiple_objects(self) -> None:
        text = '{"first": 1}\n{"second": 2}'
        result = extract_first_json(text)
        assert result == '{"first": 1}'

    # --- nested structures --------------------------------------------------

    def test_nested_object_preserved(self) -> None:
        payload = '{"outer": {"inner": [1, 2, 3]}}'
        assert extract_first_json(payload) == payload

    def test_nested_array_of_objects(self) -> None:
        payload = '[{"a": 1}, {"b": 2}]'
        assert extract_first_json(payload) == payload

    # --- escaped strings ----------------------------------------------------

    def test_escaped_quote_in_string_value(self) -> None:
        payload = '{"msg": "say \\"hello\\""}'
        result = extract_first_json(payload)
        assert result == payload

    def test_escaped_backslash_in_string_value(self) -> None:
        payload = '{"path": "C:\\\\Users\\\\name"}'
        result = extract_first_json(payload)
        assert result == payload

    # --- fallback: line-by-line ---------------------------------------------

    def test_falls_back_to_line_scan_for_valid_json_line(self) -> None:
        # Pre-amble that fails bracket scan, but valid JSON on a later line
        text = 'not json at all\n{"fallback": true}'
        result = extract_first_json(text)
        assert result == '{"fallback": true}'

    # --- no valid JSON ------------------------------------------------------

    def test_returns_original_when_no_valid_json(self) -> None:
        text = "completely plain text with no JSON"
        result = extract_first_json(text)
        # Should return original text (last-resort fallback)
        assert result == text

    # --- unicode content ----------------------------------------------------

    def test_unicode_values_preserved(self) -> None:
        payload = '{"emoji": "😀", "arabic": "مرحبا"}'
        assert extract_first_json(payload) == payload


# ---------------------------------------------------------------------------
# BrowserAgentTool._normalize_action_name
# ---------------------------------------------------------------------------


class TestNormalizeActionName:
    def test_empty_string_returns_wait(self) -> None:
        assert BrowserAgentTool._normalize_action_name("") == "wait"

    def test_go_to_url_maps_to_navigate(self) -> None:
        assert BrowserAgentTool._normalize_action_name("go_to_url") == "navigate"

    def test_click_element_maps_to_click(self) -> None:
        assert BrowserAgentTool._normalize_action_name("click_element") == "click"

    def test_click_element_by_index_maps_to_click(self) -> None:
        assert BrowserAgentTool._normalize_action_name("click_element_by_index") == "click"

    def test_input_text_maps_to_input(self) -> None:
        assert BrowserAgentTool._normalize_action_name("input_text") == "input"

    def test_scroll_down_maps_to_scroll(self) -> None:
        assert BrowserAgentTool._normalize_action_name("scroll_down") == "scroll"

    def test_scroll_up_maps_to_scroll(self) -> None:
        assert BrowserAgentTool._normalize_action_name("scroll_up") == "scroll"

    def test_scroll_to_text_maps_to_find_text(self) -> None:
        assert BrowserAgentTool._normalize_action_name("scroll_to_text") == "find_text"

    def test_extract_content_maps_to_extract(self) -> None:
        assert BrowserAgentTool._normalize_action_name("extract_content") == "extract"

    def test_unknown_action_returned_lowercased(self) -> None:
        assert BrowserAgentTool._normalize_action_name("WAIT") == "wait"

    def test_already_canonical_name_returned_as_is(self) -> None:
        assert BrowserAgentTool._normalize_action_name("click") == "click"

    def test_navigate_passthrough(self) -> None:
        assert BrowserAgentTool._normalize_action_name("navigate") == "navigate"

    def test_mixed_case_alias_normalized(self) -> None:
        # Aliases are matched after .lower(), so INPUT_TEXT should work
        assert BrowserAgentTool._normalize_action_name("INPUT_TEXT") == "input"


# ---------------------------------------------------------------------------
# BrowserAgentTool._coerce_int
# ---------------------------------------------------------------------------


class TestCoerceInt:
    def test_int_returned_as_int(self) -> None:
        assert BrowserAgentTool._coerce_int(42) == 42

    def test_zero_returned_as_zero(self) -> None:
        assert BrowserAgentTool._coerce_int(0) == 0

    def test_negative_int_returned(self) -> None:
        assert BrowserAgentTool._coerce_int(-5) == -5

    def test_float_truncated_to_int(self) -> None:
        assert BrowserAgentTool._coerce_int(3.9) == 3

    def test_float_zero_returns_zero(self) -> None:
        assert BrowserAgentTool._coerce_int(0.0) == 0

    def test_bool_true_returns_none(self) -> None:
        # bool is a subclass of int, but should be rejected
        assert BrowserAgentTool._coerce_int(True) is None

    def test_bool_false_returns_none(self) -> None:
        assert BrowserAgentTool._coerce_int(False) is None

    def test_string_returns_none(self) -> None:
        assert BrowserAgentTool._coerce_int("5") is None

    def test_none_returns_none(self) -> None:
        assert BrowserAgentTool._coerce_int(None) is None

    def test_dict_returns_none(self) -> None:
        assert BrowserAgentTool._coerce_int({"x": 1}) is None

    def test_list_returns_none(self) -> None:
        assert BrowserAgentTool._coerce_int([1, 2]) is None


# ---------------------------------------------------------------------------
# BrowserAgentTool._first_int
# ---------------------------------------------------------------------------


class TestFirstInt:
    def test_returns_first_valid_int(self) -> None:
        assert BrowserAgentTool._first_int(None, 10, 20) == 10

    def test_skips_none_values(self) -> None:
        assert BrowserAgentTool._first_int(None, None, 7) == 7

    def test_skips_bool_values(self) -> None:
        assert BrowserAgentTool._first_int(True, False, 3) == 3

    def test_returns_none_when_all_non_coercible(self) -> None:
        assert BrowserAgentTool._first_int(None, "abc", True) is None

    def test_no_args_returns_none(self) -> None:
        assert BrowserAgentTool._first_int() is None

    def test_float_is_coercible(self) -> None:
        assert BrowserAgentTool._first_int(None, 2.7) == 2

    def test_returns_zero_when_first_is_zero(self) -> None:
        assert BrowserAgentTool._first_int(0, 5) == 0

    def test_single_valid_int(self) -> None:
        assert BrowserAgentTool._first_int(99) == 99


# ---------------------------------------------------------------------------
# BrowserAgentTool._extract_action_from_dump
# ---------------------------------------------------------------------------


class TestExtractActionFromDump:
    def test_dict_value_returns_action_and_args(self) -> None:
        dump = {"click": {"index": 3}}
        action, args = BrowserAgentTool._extract_action_from_dump(dump)
        assert action == "click"
        assert args == {"index": 3}

    def test_non_dict_non_none_returns_empty_args(self) -> None:
        dump = {"wait": True}
        action, args = BrowserAgentTool._extract_action_from_dump(dump)
        assert action == "wait"
        assert args == {}

    def test_interacted_element_key_is_skipped(self) -> None:
        dump = {"interacted_element": {"id": 99}, "navigate": {"url": "https://x.com"}}
        action, args = BrowserAgentTool._extract_action_from_dump(dump)
        assert action == "navigate"
        assert args == {"url": "https://x.com"}

    def test_empty_dump_returns_wait(self) -> None:
        action, args = BrowserAgentTool._extract_action_from_dump({})
        assert action == "wait"
        assert args == {}

    def test_all_none_values_returns_wait(self) -> None:
        dump = {"scroll": None, "navigate": None}
        action, args = BrowserAgentTool._extract_action_from_dump(dump)
        assert action == "wait"
        assert args == {}

    def test_only_interacted_element_returns_wait(self) -> None:
        dump = {"interacted_element": {"id": 1}}
        action, args = BrowserAgentTool._extract_action_from_dump(dump)
        assert action == "wait"
        assert args == {}

    def test_string_value_treated_as_non_none(self) -> None:
        dump = {"scroll_down": "true"}
        action, args = BrowserAgentTool._extract_action_from_dump(dump)
        assert action == "scroll_down"
        assert args == {}


# ---------------------------------------------------------------------------
# BrowserAgentTool._map_action_to_function
# ---------------------------------------------------------------------------


class TestMapActionToFunction:
    def test_click_maps_to_browser_click(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("click", {})
        assert cursor == "click"
        assert fn == "browser_click"

    def test_click_element_alias_maps_to_browser_click(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("click_element", {})
        assert cursor == "click"
        assert fn == "browser_click"

    def test_input_maps_to_browser_input(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("input", {})
        assert cursor == "input"
        assert fn == "browser_input"

    def test_input_text_alias_maps_to_browser_input(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("input_text", {})
        assert cursor == "input"
        assert fn == "browser_input"

    def test_select_dropdown_maps_to_browser_input(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("select_dropdown", {})
        assert cursor == "input"
        assert fn == "browser_input"

    def test_navigate_maps_to_browser_navigate(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("navigate", {})
        assert cursor == "navigate"
        assert fn == "browser_navigate"

    def test_go_to_url_alias_maps_to_browser_navigate(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("go_to_url", {})
        assert cursor == "navigate"
        assert fn == "browser_navigate"

    def test_search_maps_to_browser_navigate(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("search", {})
        assert cursor == "navigate"
        assert fn == "browser_navigate"

    def test_go_back_maps_to_browser_navigate(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("go_back", {})
        assert cursor == "navigate"
        assert fn == "browser_navigate"

    def test_scroll_down_direction_true(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("scroll", {"down": True})
        assert cursor == "scroll"
        assert fn == "browser_scroll_down"

    def test_scroll_up_direction_false(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("scroll", {"down": False})
        assert cursor == "scroll"
        assert fn == "browser_scroll_up"

    def test_scroll_default_direction_is_down(self) -> None:
        # When 'down' key is absent, default is True → scroll_down
        cursor, fn = BrowserAgentTool._map_action_to_function("scroll", {})
        assert cursor == "scroll"
        assert fn == "browser_scroll_down"

    def test_find_text_maps_to_scroll_cursor(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("find_text", {})
        assert cursor == "scroll"
        assert fn == "browser_scroll_down"

    def test_extract_maps_to_browser_agent_extract(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("extract", {})
        assert cursor == "extract"
        assert fn == "browser_agent_extract"

    def test_extract_content_alias_maps_to_browser_agent_extract(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("extract_content", {})
        assert cursor == "extract"
        assert fn == "browser_agent_extract"

    def test_search_page_maps_to_browser_agent_extract(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("search_page", {})
        assert cursor == "extract"
        assert fn == "browser_agent_extract"

    def test_find_elements_maps_to_browser_agent_extract(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("find_elements", {})
        assert cursor == "extract"
        assert fn == "browser_agent_extract"

    def test_read_long_content_maps_to_browser_agent_extract(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("read_long_content", {})
        assert cursor == "extract"
        assert fn == "browser_agent_extract"

    def test_unknown_action_maps_to_wait(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("unknown_action", {})
        assert cursor == "wait"
        assert fn == "browser_agent_run"

    def test_wait_maps_to_browser_agent_run(self) -> None:
        cursor, fn = BrowserAgentTool._map_action_to_function("wait", {})
        assert cursor == "wait"
        assert fn == "browser_agent_run"


# ---------------------------------------------------------------------------
# BrowserAgentTool._describe_action
# ---------------------------------------------------------------------------


class TestDescribeAction:
    def test_click_with_index(self) -> None:
        label = BrowserAgentTool._describe_action("click", {"index": 5})
        assert label == "Click element 5"

    def test_click_without_index(self) -> None:
        label = BrowserAgentTool._describe_action("click", {})
        assert label == "Click"

    def test_input_with_index(self) -> None:
        label = BrowserAgentTool._describe_action("input", {"index": 2})
        assert label == "Type into element 2"

    def test_input_without_index(self) -> None:
        label = BrowserAgentTool._describe_action("input", {})
        assert label == "Type text"

    def test_navigate_with_url(self) -> None:
        label = BrowserAgentTool._describe_action("navigate", {"url": "https://example.com"})
        assert label == "Navigate to https://example.com"

    def test_navigate_without_url(self) -> None:
        label = BrowserAgentTool._describe_action("navigate", {})
        assert label == "Navigate"

    def test_navigate_with_empty_url_string(self) -> None:
        label = BrowserAgentTool._describe_action("navigate", {"url": ""})
        assert label == "Navigate"

    def test_navigate_with_non_string_url(self) -> None:
        label = BrowserAgentTool._describe_action("navigate", {"url": 42})
        assert label == "Navigate"

    def test_scroll_down(self) -> None:
        label = BrowserAgentTool._describe_action("scroll", {"down": True})
        assert label == "Scroll down"

    def test_scroll_up(self) -> None:
        label = BrowserAgentTool._describe_action("scroll", {"down": False})
        assert label == "Scroll up"

    def test_scroll_default_is_down(self) -> None:
        label = BrowserAgentTool._describe_action("scroll", {})
        assert label == "Scroll down"

    def test_find_text_with_text(self) -> None:
        label = BrowserAgentTool._describe_action("find_text", {"text": "Privacy Policy"})
        assert label == "Find text: Privacy Policy"

    def test_find_text_without_text(self) -> None:
        label = BrowserAgentTool._describe_action("find_text", {})
        assert label == "Find text on page"

    def test_find_text_with_empty_string(self) -> None:
        label = BrowserAgentTool._describe_action("find_text", {"text": ""})
        assert label == "Find text on page"

    def test_extract_action(self) -> None:
        label = BrowserAgentTool._describe_action("extract", {})
        assert label == "Extract page content"

    def test_unknown_action_title_cased(self) -> None:
        label = BrowserAgentTool._describe_action("some_custom_action", {})
        assert label == "Some Custom Action"

    def test_wait_title_cased(self) -> None:
        label = BrowserAgentTool._describe_action("wait", {})
        assert label == "Wait"


# ---------------------------------------------------------------------------
# BrowserAgentTool._extract_coordinates
# ---------------------------------------------------------------------------


class TestExtractCoordinates:
    def test_args_coordinates_take_priority(self) -> None:
        args = {"coordinate_x": 100, "coordinate_y": 200}
        x, y = BrowserAgentTool._extract_coordinates(args, {"click_x": 999, "click_y": 888})
        assert x == 100
        assert y == 200

    def test_falls_back_to_metadata_click_xy(self) -> None:
        args: dict = {}
        meta = {"click_x": 300, "click_y": 400}
        x, y = BrowserAgentTool._extract_coordinates(args, meta)
        assert x == 300
        assert y == 400

    def test_falls_back_to_metadata_input_xy(self) -> None:
        args: dict = {}
        meta = {"input_x": 50, "input_y": 75}
        x, y = BrowserAgentTool._extract_coordinates(args, meta)
        assert x == 50
        assert y == 75

    def test_falls_back_to_metadata_generic_xy(self) -> None:
        args: dict = {}
        meta = {"x": 11, "y": 22}
        x, y = BrowserAgentTool._extract_coordinates(args, meta)
        assert x == 11
        assert y == 22

    def test_no_metadata_returns_none_none(self) -> None:
        x, y = BrowserAgentTool._extract_coordinates({}, None)
        assert x is None
        assert y is None

    def test_non_dict_metadata_returns_none_none(self) -> None:
        x, y = BrowserAgentTool._extract_coordinates({}, "not a dict")
        assert x is None
        assert y is None

    def test_partial_coords_in_args_uses_metadata(self) -> None:
        # Only coordinate_x present in args → falls through to metadata lookup
        args = {"coordinate_x": 10}
        meta = {"click_x": 20, "click_y": 30}
        x, y = BrowserAgentTool._extract_coordinates(args, meta)
        # coordinate_y is None so the condition fails; metadata used
        assert x == 20
        assert y == 30

    def test_float_coords_coerced_to_int(self) -> None:
        args: dict = {}
        meta = {"click_x": 1.9, "click_y": 2.1}
        x, y = BrowserAgentTool._extract_coordinates(args, meta)
        assert x == 1
        assert y == 2

    def test_bool_coords_not_coerced(self) -> None:
        args: dict = {}
        meta = {"click_x": True, "click_y": False}
        x, y = BrowserAgentTool._extract_coordinates(args, meta)
        assert x is None
        assert y is None

    def test_empty_metadata_returns_none_none(self) -> None:
        x, y = BrowserAgentTool._extract_coordinates({}, {})
        assert x is None
        assert y is None


# ---------------------------------------------------------------------------
# BrowserAgentTool._sanitize_task_prompt
# ---------------------------------------------------------------------------


class TestSanitizeTaskPrompt:
    def _tool(self) -> BrowserAgentTool:
        return _make_tool()

    def test_suffix_appended_to_task(self) -> None:
        tool = self._tool()
        result = tool._sanitize_task_prompt("Do something")
        assert result.startswith("Do something")

    def test_critical_instructions_present(self) -> None:
        tool = self._tool()
        result = tool._sanitize_task_prompt("task")
        assert "CRITICAL INSTRUCTIONS" in result

    def test_skip_video_sites_instruction(self) -> None:
        tool = self._tool()
        result = tool._sanitize_task_prompt("task")
        assert "SKIP video sites" in result

    def test_close_popups_instruction(self) -> None:
        tool = self._tool()
        result = tool._sanitize_task_prompt("task")
        assert "CLOSE popups" in result

    def test_deny_notifications_instruction(self) -> None:
        tool = self._tool()
        result = tool._sanitize_task_prompt("task")
        assert "DENY notification requests" in result

    def test_captcha_instruction(self) -> None:
        tool = self._tool()
        result = tool._sanitize_task_prompt("task")
        assert "CAPTCHA" in result

    def test_json_only_instruction(self) -> None:
        tool = self._tool()
        result = tool._sanitize_task_prompt("task")
        assert "valid JSON only" in result

    def test_original_task_preserved_verbatim(self) -> None:
        tool = self._tool()
        original = "Extract all product prices from the page"
        result = tool._sanitize_task_prompt(original)
        assert result.startswith(original)

    def test_empty_task_still_gets_suffix(self) -> None:
        tool = self._tool()
        result = tool._sanitize_task_prompt("")
        assert "CRITICAL INSTRUCTIONS" in result


# ---------------------------------------------------------------------------
# BrowserAgentTool._clean_llm_response
# ---------------------------------------------------------------------------


class TestCleanLlmResponse:
    def _tool(self) -> BrowserAgentTool:
        return _make_tool()

    def test_strips_json_code_fence(self) -> None:
        tool = self._tool()
        raw = '```json\n{"key": "value"}\n```'
        assert tool._clean_llm_response(raw) == '{"key": "value"}'

    def test_strips_plain_code_fence(self) -> None:
        tool = self._tool()
        raw = '```\n{"x": 1}\n```'
        assert tool._clean_llm_response(raw) == '{"x": 1}'

    def test_strips_leading_trailing_whitespace(self) -> None:
        tool = self._tool()
        raw = "   plain content   "
        assert tool._clean_llm_response(raw) == "plain content"

    def test_plain_text_returned_stripped(self) -> None:
        tool = self._tool()
        result = tool._clean_llm_response("  hello world  ")
        assert result == "hello world"

    def test_empty_string_returned_as_is(self) -> None:
        tool = self._tool()
        assert tool._clean_llm_response("") == ""

    def test_none_returned_as_is(self) -> None:
        tool = self._tool()
        assert tool._clean_llm_response(None) is None  # type: ignore[arg-type]

    def test_multiline_content_preserved(self) -> None:
        tool = self._tool()
        raw = "```json\nline1\nline2\n```"
        result = tool._clean_llm_response(raw)
        assert result == "line1\nline2"

    def test_no_fence_content_unchanged_modulo_strip(self) -> None:
        tool = self._tool()
        raw = '{"clean": true}'
        assert tool._clean_llm_response(raw) == raw

    def test_fence_without_newline(self) -> None:
        tool = self._tool()
        raw = '```json{"a":1}```'
        result = tool._clean_llm_response(raw)
        assert result == '{"a":1}'
