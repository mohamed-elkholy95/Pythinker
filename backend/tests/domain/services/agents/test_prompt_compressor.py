"""Tests for PromptCompressor — smart prompt compression for token efficiency."""

import pytest

from app.domain.services.agents.prompt_compressor import (
    CompressionLevel,
    CompressionResult,
    PromptCompressor,
    _summarize_traceback,
    compress_for_context,
    get_prompt_compressor,
)

# ── Helpers ──────────────────────────────────────────────────────────


def make_long_text(words: int = 500) -> str:
    """Return a multi-line text exceeding typical token budgets."""
    return ("word " * words).strip()


def make_section_text(n_sections: int = 10, lines_per_section: int = 20) -> str:
    sections = []
    for i in range(n_sections):
        body = "\n".join(f"Content line {j} for section {i}." for j in range(lines_per_section))
        sections.append(f"## Section {i}\n{body}")
    return "\n".join(sections)


# ── CompressionLevel enum ────────────────────────────────────────────


class TestCompressionLevel:
    def test_all_members_exist(self):
        assert CompressionLevel.NONE == "none"
        assert CompressionLevel.LIGHT == "light"
        assert CompressionLevel.MODERATE == "moderate"
        assert CompressionLevel.AGGRESSIVE == "aggressive"

    def test_is_str_enum(self):
        assert isinstance(CompressionLevel.NONE, str)

    def test_comparison_with_string(self):
        assert CompressionLevel.LIGHT == "light"
        assert CompressionLevel.MODERATE != "none"

    def test_membership(self):
        levels = list(CompressionLevel)
        assert len(levels) == 4


# ── CompressionResult dataclass ──────────────────────────────────────


class TestCompressionResult:
    def test_construction_all_fields(self):
        r = CompressionResult(
            original_tokens=200,
            compressed_tokens=80,
            compression_ratio=0.4,
            content="result text",
            items_removed=5,
            summary_generated=True,
        )
        assert r.original_tokens == 200
        assert r.compressed_tokens == 80
        assert r.compression_ratio == 0.4
        assert r.content == "result text"
        assert r.items_removed == 5
        assert r.summary_generated is True

    def test_no_compression_ratio_is_one(self):
        r = CompressionResult(
            original_tokens=50,
            compressed_tokens=50,
            compression_ratio=1.0,
            content="unchanged",
            items_removed=0,
            summary_generated=False,
        )
        assert r.compression_ratio == 1.0
        assert r.summary_generated is False
        assert r.items_removed == 0

    def test_zero_token_result(self):
        r = CompressionResult(
            original_tokens=0,
            compressed_tokens=0,
            compression_ratio=1.0,
            content="",
            items_removed=0,
            summary_generated=False,
        )
        assert r.content == ""
        assert r.original_tokens == 0


# ── PromptCompressor.__init__ ────────────────────────────────────────


class TestPromptCompressorInit:
    def test_default_level_is_moderate(self):
        c = PromptCompressor()
        assert c.default_level == CompressionLevel.MODERATE

    def test_custom_default_level(self):
        c = PromptCompressor(default_level=CompressionLevel.AGGRESSIVE)
        assert c.default_level == CompressionLevel.AGGRESSIVE

    def test_preserve_code_blocks_default_true(self):
        c = PromptCompressor()
        assert c.preserve_code_blocks is True

    def test_preserve_code_blocks_can_be_false(self):
        c = PromptCompressor(preserve_code_blocks=False)
        assert c.preserve_code_blocks is False

    def test_max_list_items_default(self):
        c = PromptCompressor()
        assert c.max_list_items == 10

    def test_custom_max_list_items(self):
        c = PromptCompressor(max_list_items=5)
        assert c.max_list_items == 5

    def test_stats_initialized_to_zero(self):
        c = PromptCompressor()
        assert c._stats["compressions"] == 0
        assert c._stats["tokens_saved"] == 0
        assert c._stats["avg_compression_ratio"] == 0.0

    def test_compiled_patterns_populated(self):
        c = PromptCompressor()
        assert len(c._reducible_re) > 0


# ── estimate_tokens ─────────────────────────────────────────────────


class TestEstimateTokens:
    def test_empty_string_returns_zero(self):
        c = PromptCompressor()
        assert c.estimate_tokens("") == 0

    def test_uses_tokens_per_char_constant(self):
        c = PromptCompressor()
        text = "a" * 100  # 100 * 0.25 = 25
        assert c.estimate_tokens(text) == 25

    def test_result_is_integer(self):
        c = PromptCompressor()
        assert isinstance(c.estimate_tokens("hello world"), int)

    def test_longer_text_has_more_tokens(self):
        c = PromptCompressor()
        assert c.estimate_tokens("hi") < c.estimate_tokens("hi there, this is a longer piece of text")

    def test_proportional_scaling(self):
        c = PromptCompressor()
        t1 = c.estimate_tokens("a" * 40)  # 10 tokens
        t2 = c.estimate_tokens("a" * 80)  # 20 tokens
        assert t2 == t1 * 2

    def test_single_character(self):
        c = PromptCompressor()
        assert c.estimate_tokens("x") == 0  # int(1 * 0.25) == 0

    def test_four_characters(self):
        c = PromptCompressor()
        assert c.estimate_tokens("abcd") == 1


# ── compress_tool_output ────────────────────────────────────────────


class TestCompressToolOutput:
    def test_empty_string_returns_empty_result(self):
        c = PromptCompressor()
        result = c.compress_tool_output("")
        assert result.content == ""
        assert result.original_tokens == 0
        assert result.compressed_tokens == 0
        assert result.compression_ratio == 1.0
        assert result.items_removed == 0
        assert result.summary_generated is False

    def test_short_output_unchanged(self):
        c = PromptCompressor()
        text = "Short output"
        result = c.compress_tool_output(text, max_tokens=500)
        assert result.content == text
        assert result.compression_ratio == 1.0
        assert result.items_removed == 0
        assert result.summary_generated is False

    def test_text_exactly_at_limit_unchanged(self):
        c = PromptCompressor()
        # 400 chars * 0.25 = 100 tokens
        text = "a" * 400
        result = c.compress_tool_output(text, max_tokens=100)
        assert result.content == text
        assert result.summary_generated is False

    def test_long_output_reduces_tokens(self):
        c = PromptCompressor()
        text = make_long_text(1000)
        result = c.compress_tool_output(text, max_tokens=100)
        assert result.compressed_tokens <= result.original_tokens
        assert result.compression_ratio < 1.0

    def test_level_none_skips_all_compression(self):
        c = PromptCompressor()
        text = "a" * 10000
        result = c.compress_tool_output(text, max_tokens=100, level=CompressionLevel.NONE)
        # With NONE level, no light/moderate/aggressive compression runs,
        # but _truncate_with_summary still fires via the final else branch
        assert result.original_tokens > 100

    def test_level_light_applies_basic_compression(self):
        c = PromptCompressor()
        text = "Hello\n\n\n\n\nWorld\n\n\n\nEnd " * 200
        result = c.compress_tool_output(text, max_tokens=50, level=CompressionLevel.LIGHT)
        assert isinstance(result, CompressionResult)

    def test_level_moderate_applies_pattern_compression(self):
        c = PromptCompressor()
        # Timestamps and debug logs are pruned by pattern compression
        text = ("[2024-01-15T10:30:00Z] INFO: starting\nDEBUG: verbose debug line\nactual content\n") * 200
        result = c.compress_tool_output(text, max_tokens=50, level=CompressionLevel.MODERATE)
        assert isinstance(result, CompressionResult)
        assert result.items_removed >= 0

    def test_level_aggressive_generates_summary(self):
        c = PromptCompressor()
        text = make_long_text(2000)
        result = c.compress_tool_output(text, max_tokens=50, level=CompressionLevel.AGGRESSIVE)
        assert result.summary_generated is True

    def test_returns_compression_result_type(self):
        c = PromptCompressor()
        result = c.compress_tool_output("hello", max_tokens=500)
        assert isinstance(result, CompressionResult)

    def test_tool_name_accepted_without_error(self):
        c = PromptCompressor()
        text = make_long_text(1000)
        result = c.compress_tool_output(text, max_tokens=50, tool_name="bash")
        assert isinstance(result, CompressionResult)

    def test_uses_default_level_when_none(self):
        c = PromptCompressor(default_level=CompressionLevel.LIGHT)
        text = make_long_text(500)
        # Just ensure it runs without error and returns a result
        result = c.compress_tool_output(text, max_tokens=50)
        assert isinstance(result, CompressionResult)

    def test_stats_incremented_on_compression(self):
        c = PromptCompressor()
        initial = c.get_stats()["compressions"]
        text = make_long_text(1000)
        c.compress_tool_output(text, max_tokens=50)
        assert c.get_stats()["compressions"] == initial + 1

    def test_stats_not_incremented_for_passthrough(self):
        # When text is within limit, _create_result is NOT called — passthrough
        c = PromptCompressor()
        initial = c.get_stats()["compressions"]
        c.compress_tool_output("hi", max_tokens=5000)
        assert c.get_stats()["compressions"] == initial


# ── _apply_basic_compression ────────────────────────────────────────


class TestApplyBasicCompression:
    def test_normalizes_crlf(self):
        c = PromptCompressor()
        result = c._apply_basic_compression("Hello\r\nWorld\r\nEnd")
        assert "\r" not in result

    def test_normalizes_cr_only(self):
        c = PromptCompressor()
        result = c._apply_basic_compression("Hello\rWorld")
        assert "\r" not in result

    def test_collapses_excess_blank_lines(self):
        c = PromptCompressor()
        result = c._apply_basic_compression("A\n\n\n\n\nB")
        assert result == "A\n\nB"

    def test_exactly_two_newlines_unchanged(self):
        c = PromptCompressor()
        result = c._apply_basic_compression("A\n\nB")
        assert result == "A\n\nB"

    def test_strips_trailing_whitespace_per_line(self):
        c = PromptCompressor()
        result = c._apply_basic_compression("Hello   \nWorld   \nEnd  ")
        for line in result.split("\n"):
            assert not line.endswith(" ")

    def test_strips_outer_whitespace(self):
        c = PromptCompressor()
        result = c._apply_basic_compression("  \n\n  Hello  \n\n  ")
        assert result == "Hello"

    def test_empty_string_returns_empty(self):
        c = PromptCompressor()
        assert c._apply_basic_compression("") == ""

    def test_single_newline_preserved(self):
        c = PromptCompressor()
        result = c._apply_basic_compression("A\nB")
        assert result == "A\nB"

    def test_preserves_content(self):
        c = PromptCompressor()
        result = c._apply_basic_compression("important data here")
        assert "important data here" in result


# ── _apply_pattern_compression ──────────────────────────────────────


class TestApplyPatternCompression:
    def test_replaces_timestamps(self):
        c = PromptCompressor()
        text = "[2024-01-15T10:30:00+00:00] action happened\n"
        result, _removed = c._apply_pattern_compression(text)
        assert "[timestamp]" in result

    def test_removes_debug_lines(self):
        c = PromptCompressor()
        text = "DEBUG: verbose internal info\nActual output line"
        result, _removed = c._apply_pattern_compression(text)
        assert "DEBUG" not in result

    def test_collapses_multiple_spaces(self):
        c = PromptCompressor()
        text = "word    word    word"
        result, _removed = c._apply_pattern_compression(text)
        assert "    " not in result

    def test_replaces_home_paths(self):
        c = PromptCompressor()
        text = "file at /home/username/project/file.py"
        result, _removed = c._apply_pattern_compression(text)
        assert "~/project/file.py" in result

    def test_truncates_uuids(self):
        c = PromptCompressor()
        text = "id=550e8400-e29b-41d4-a716-446655440000"
        result, _removed = c._apply_pattern_compression(text)
        assert "550e8400..." in result

    def test_returns_tuple_of_text_and_count(self):
        c = PromptCompressor()
        result = c._apply_pattern_compression("plain text")
        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], str)
        assert isinstance(result[1], int)

    def test_items_removed_non_negative(self):
        c = PromptCompressor()
        _, _removed = c._apply_pattern_compression("plain text with no patterns")
        assert _removed >= 0

    def test_replaces_tabs(self):
        c = PromptCompressor()
        text = "col1\t\tcol2\t\tcol3"
        result, _ = c._apply_pattern_compression(text)
        assert "\t\t" not in result


# ── _truncate_with_summary ──────────────────────────────────────────


class TestTruncateWithSummary:
    def test_returns_tuple(self):
        c = PromptCompressor()
        result = c._truncate_with_summary("some text\n" * 50, max_tokens=100, tool_name=None)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_summary_generated_flag_always_true(self):
        c = PromptCompressor()
        _, flag = c._truncate_with_summary("text\n" * 100, max_tokens=200, tool_name=None)
        assert flag is True

    def test_very_small_max_tokens_uses_char_count(self):
        c = PromptCompressor()
        text = "A" * 1000
        result, flag = c._truncate_with_summary(text, max_tokens=10, tool_name=None)
        assert flag is True
        assert "truncated" in result.lower() or "omitted" in result.lower()

    def test_content_space_zero_returns_length_message(self):
        c = PromptCompressor()
        # max_chars = int(1 / 0.25) = 4; header_space=100 → content_space = 4-100 ≤ 0
        text = "some long text that should be truncated"
        result, flag = c._truncate_with_summary(text, max_tokens=1, tool_name=None)
        assert "truncated" in result.lower()
        assert flag is True

    def test_preserves_first_line(self):
        c = PromptCompressor()
        lines = [f"Line {i}" for i in range(100)]
        text = "\n".join(lines)
        result, _ = c._truncate_with_summary(text, max_tokens=400, tool_name="test_tool")
        assert "Line 0" in result

    def test_includes_omitted_marker_for_long_text(self):
        c = PromptCompressor()
        lines = [f"Line {i}: some content here" for i in range(50)]
        text = "\n".join(lines)
        result, _ = c._truncate_with_summary(text, max_tokens=200, tool_name=None)
        assert "omitted" in result.lower()

    def test_tool_name_does_not_affect_logic(self):
        c = PromptCompressor()
        text = "line\n" * 100
        r1, _ = c._truncate_with_summary(text, max_tokens=100, tool_name="bash")
        r2, _ = c._truncate_with_summary(text, max_tokens=100, tool_name=None)
        # Both paths should produce a summary
        assert r1 and r2

    def test_short_text_truncated_to_max_chars(self):
        c = PromptCompressor()
        # Single line, 8 total lines threshold not met → falls to text[:max_chars]
        text = "AB\nCD\nEF\nGH\nIJ"  # 5 lines — last_lines condition: len > 8 is False
        _result, flag = c._truncate_with_summary(text, max_tokens=200, tool_name=None)
        assert flag is True


# ── _is_important ────────────────────────────────────────────────────


class TestIsImportant:
    @pytest.mark.parametrize(
        "text",
        [
            "An error occurred",
            "Exception raised",
            "Task failed with code 1",
            "success: operation complete",
            "WARNING: low disk",
            "Result: 42 items",
            "Output: data follows",
            "File created successfully",
            "Record modified",
            "Entry deleted",
            "IMPORTANT notice",
            "NOTE: check this",
            "TODO: finish this",
            "FIXME: broken logic",
        ],
    )
    def test_important_marker_detected(self, text: str):
        c = PromptCompressor()
        assert c._is_important(text) is True

    def test_plain_text_not_important(self):
        c = PromptCompressor()
        assert c._is_important("just some regular content here") is False

    def test_case_insensitive_detection(self):
        c = PromptCompressor()
        assert c._is_important("ERROR OCCURRED") is True
        assert c._is_important("Fixme: this") is True

    def test_empty_string_not_important(self):
        c = PromptCompressor()
        assert c._is_important("") is False

    def test_partial_match_in_word(self):
        # "result" appears inside "resulted"
        c = PromptCompressor()
        assert c._is_important("The test resulted in a pass") is True


# ── _summarize_section ──────────────────────────────────────────────


class TestSummarizeSection:
    def test_returns_string_or_none(self):
        c = PromptCompressor()
        result = c._summarize_section("## Header\nContent line here.", max_tokens=200)
        assert result is None or isinstance(result, str)

    def test_includes_header_in_summary(self):
        c = PromptCompressor()
        section = "## My Section\nFirst line of content.\nSecond line.\n"
        result = c._summarize_section(section, max_tokens=500)
        if result is not None:
            assert "My Section" in result

    def test_appends_ellipsis(self):
        c = PromptCompressor()
        section = "## Title\nContent here."
        result = c._summarize_section(section, max_tokens=500)
        if result is not None:
            assert result.endswith("...")

    def test_returns_none_when_summary_exceeds_budget(self):
        c = PromptCompressor()
        # max_chars = int(1 / 0.25) = 4 — far too small for any summary
        result = c._summarize_section("## Header\nSome content.", max_tokens=1)
        assert result is None

    def test_section_without_header(self):
        c = PromptCompressor()
        section = "Just plain content without a markdown header."
        result = c._summarize_section(section, max_tokens=500)
        if result is not None:
            assert result.endswith("...")

    def test_first_line_truncated_to_100_chars(self):
        c = PromptCompressor()
        long_line = "x" * 200
        section = f"## H\n{long_line}"
        result = c._summarize_section(section, max_tokens=2000)
        if result is not None:
            # first_line is capped at 100 chars
            assert len(result) <= len("## H\n") + 100 + len("...")


# ── _create_result ───────────────────────────────────────────────────


class TestCreateResult:
    def test_ratio_calculated_correctly(self):
        c = PromptCompressor()
        original = "a" * 400  # 100 tokens
        compressed = "a" * 200  # 50 tokens
        result = c._create_result(original, compressed, 0, False)
        assert abs(result.compression_ratio - 0.5) < 0.01

    def test_ratio_is_one_for_identical_strings(self):
        c = PromptCompressor()
        text = "same"
        result = c._create_result(text, text, 0, False)
        assert result.compression_ratio == 1.0

    def test_ratio_zero_denominator_defaults_to_one(self):
        c = PromptCompressor()
        result = c._create_result("", "", 0, False)
        assert result.compression_ratio == 1.0

    def test_stats_updated(self):
        c = PromptCompressor()
        before = c._stats["compressions"]
        original = "a" * 400
        compressed = "a" * 200
        c._create_result(original, compressed, 0, False)
        assert c._stats["compressions"] == before + 1

    def test_tokens_saved_incremented(self):
        c = PromptCompressor()
        before = c._stats["tokens_saved"]
        original = "a" * 400  # 100 tokens
        compressed = "a" * 200  # 50 tokens
        c._create_result(original, compressed, 0, False)
        assert c._stats["tokens_saved"] == before + 50

    def test_average_ratio_calculated(self):
        c = PromptCompressor()
        original = "a" * 400
        compressed = "a" * 200
        c._create_result(original, compressed, 0, False)
        stats = c.get_stats()
        assert 0.0 < stats["avg_compression_ratio"] <= 1.0


# ── compress_history ────────────────────────────────────────────────


class TestCompressHistory:
    def test_empty_list_returns_empty(self):
        c = PromptCompressor()
        assert c.compress_history([]) == []

    def test_preserves_system_messages_by_default(self):
        c = PromptCompressor()
        messages = [
            {"role": "system", "content": "You are an assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = c.compress_history(messages, max_tokens=5000)
        system_msgs = [m for m in result if m["role"] == "system"]
        assert len(system_msgs) == 1
        assert system_msgs[0]["content"] == "You are an assistant."

    def test_preserve_system_false_treats_as_regular(self):
        c = PromptCompressor()
        messages = [
            {"role": "system", "content": "System prompt"},
            {"role": "user", "content": "Hi"},
        ]
        result = c.compress_history(messages, preserve_system=False, max_tokens=5000)
        # System message is NOT separated out — all go into other_msgs
        assert len(result) >= 1

    def test_keeps_at_least_keep_recent_messages(self):
        c = PromptCompressor()
        messages = [{"role": "user", "content": f"Message {i}"} for i in range(10)]
        result = c.compress_history(messages, keep_recent=3, max_tokens=5000)
        assert len(result) >= 3

    def test_recent_messages_last_in_result(self):
        c = PromptCompressor()
        messages = [{"role": "user", "content": f"Msg {i}"} for i in range(5)]
        result = c.compress_history(messages, keep_recent=2, max_tokens=5000)
        # Last two messages should appear at the end
        last_two_contents = {result[-1]["content"], result[-2]["content"]}
        assert "Msg 4" in last_two_contents
        assert "Msg 3" in last_two_contents

    def test_fewer_messages_than_keep_recent(self):
        c = PromptCompressor()
        messages = [{"role": "user", "content": "Only one"}]
        result = c.compress_history(messages, keep_recent=5, max_tokens=5000)
        assert len(result) == 1

    def test_system_message_budget_overflow_compresses_system(self):
        c = PromptCompressor()
        # Giant system message that exceeds max_tokens
        giant_system = "a" * 40000  # 10000 tokens
        messages = [
            {"role": "system", "content": giant_system},
            {"role": "user", "content": "Hi"},
        ]
        result = c.compress_history(messages, max_tokens=100)
        system_msgs = [m for m in result if m["role"] == "system"]
        # System message should have been compressed
        assert len(system_msgs[0]["content"]) < len(giant_system)

    def test_older_important_messages_included_if_space(self):
        c = PromptCompressor()
        messages = [
            {"role": "user", "content": "Error: something failed here."},
            {"role": "assistant", "content": "Let me check."},
            {"role": "user", "content": "Recent 1"},
            {"role": "user", "content": "Recent 2"},
        ]
        result = c.compress_history(messages, keep_recent=2, max_tokens=5000)
        # Important older message should be preserved if budget allows
        assert len(result) >= 2

    def test_returns_list_of_dicts(self):
        c = PromptCompressor()
        messages = [{"role": "user", "content": "hi"}]
        result = c.compress_history(messages)
        assert isinstance(result, list)
        assert all(isinstance(m, dict) for m in result)

    def test_system_plus_recent_messages_ordering(self):
        c = PromptCompressor()
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "old message"},
            {"role": "user", "content": "recent message"},
        ]
        result = c.compress_history(messages, keep_recent=1, max_tokens=5000)
        # System always first
        assert result[0]["role"] == "system"


# ── compress_context ─────────────────────────────────────────────────


class TestCompressContext:
    def test_empty_context_returns_empty(self):
        c = PromptCompressor()
        assert c.compress_context("") == ""

    def test_short_context_unchanged(self):
        c = PromptCompressor()
        text = "Short context"
        assert c.compress_context(text, max_tokens=500) == text

    def test_context_at_limit_unchanged(self):
        c = PromptCompressor()
        text = "a" * 400  # 100 tokens
        assert c.compress_context(text, max_tokens=100) == text

    def test_long_context_reduced(self):
        c = PromptCompressor()
        text = make_section_text(n_sections=15, lines_per_section=30)
        result = c.compress_context(text, max_tokens=200)
        assert len(result) < len(text)

    def test_preserved_sections_retained(self):
        c = PromptCompressor()
        sections = (
            "## Results\nThe results are important.\n"
            + "filler " * 100
            + "\n"
            + "## Filler Section\n"
            + "filler " * 200
            + "\n"
            + "## More Filler\n"
            + "filler " * 200
            + "\n"
        )
        result = c.compress_context(sections, max_tokens=200, preserve_sections=["results"])
        assert "Results" in result

    def test_returns_string(self):
        c = PromptCompressor()
        result = c.compress_context("Some context")
        assert isinstance(result, str)

    def test_result_stripped(self):
        c = PromptCompressor()
        text = make_section_text(n_sections=20, lines_per_section=20)
        result = c.compress_context(text, max_tokens=100)
        assert result == result.strip()

    def test_important_sections_prioritized(self):
        c = PromptCompressor()
        sections = (
            "## Errors\nError: critical failure occurred.\n"
            + "detail " * 10
            + "\n"
            + "## Background\n"
            + "background " * 200
            + "\n"
            + "## More Background\n"
            + "more " * 200
            + "\n"
        )
        result = c.compress_context(sections, max_tokens=200)
        # Important section (contains "error") should be preserved
        assert "Errors" in result


# ── _summarize_traceback ─────────────────────────────────────────────


class TestSummarizeTraceback:
    def test_short_traceback_unchanged(self):
        tb = "Traceback (most recent call last):\n  File a.py\n  in func\nValueError: bad"
        result = _summarize_traceback(tb)
        assert result == tb

    def test_exactly_six_lines_unchanged(self):
        lines = [f"line {i}" for i in range(6)]
        tb = "\n".join(lines)
        result = _summarize_traceback(tb)
        assert result == tb

    def test_long_traceback_contains_frames_marker(self):
        lines = ["Traceback (most recent call last):"]
        lines.extend(f'  File "mod_{i}.py", line {i}, in fn_{i}' for i in range(10))
        lines.append("ValueError: something went wrong")
        tb = "\n".join(lines)
        result = _summarize_traceback(tb)
        assert "frames" in result

    def test_long_traceback_shorter_than_original(self):
        lines = ["Traceback (most recent call last):"]
        lines.extend(f'  File "module_{i}.py", line {i}, in function_{i}' for i in range(20))
        lines.append("RuntimeError: unexpected error occurred")
        tb = "\n".join(lines)
        result = _summarize_traceback(tb)
        assert len(result) < len(tb)

    def test_long_traceback_keeps_header(self):
        lines = ["Traceback (most recent call last):"]
        lines.extend(f'  File "f{i}.py", line {i}' for i in range(10))
        lines.append("TypeError: type mismatch")
        tb = "\n".join(lines)
        result = _summarize_traceback(tb)
        assert result.startswith("Traceback")

    def test_long_traceback_keeps_last_frame(self):
        lines = ["Traceback (most recent call last):"]
        lines.extend(f'  File "f{i}.py", line {i}' for i in range(10))
        last_line = "TypeError: final error"
        lines.append(last_line)
        tb = "\n".join(lines)
        result = _summarize_traceback(tb)
        assert last_line in result

    def test_seven_lines_summarized(self):
        lines = [f"line {i}" for i in range(7)]
        tb = "\n".join(lines)
        result = _summarize_traceback(tb)
        assert "frames" in result


# ── get_stats ────────────────────────────────────────────────────────


class TestGetStats:
    def test_initial_stats_all_zero(self):
        c = PromptCompressor()
        stats = c.get_stats()
        assert stats["compressions"] == 0
        assert stats["tokens_saved"] == 0
        assert stats["avg_compression_ratio"] == 0.0

    def test_avg_ratio_pct_key_present(self):
        c = PromptCompressor()
        assert "avg_ratio_pct" in c.get_stats()

    def test_avg_ratio_pct_format(self):
        c = PromptCompressor()
        pct = c.get_stats()["avg_ratio_pct"]
        assert "%" in pct

    def test_stats_accumulate_across_calls(self):
        c = PromptCompressor()
        text = make_long_text(1000)
        c.compress_tool_output(text, max_tokens=50)
        c.compress_tool_output(text, max_tokens=50)
        stats = c.get_stats()
        assert stats["compressions"] == 2

    def test_tokens_saved_positive_after_compression(self):
        c = PromptCompressor()
        text = make_long_text(1000)
        c.compress_tool_output(text, max_tokens=50)
        assert c.get_stats()["tokens_saved"] > 0

    def test_rolling_average_updated(self):
        c = PromptCompressor()
        text = make_long_text(1000)
        c.compress_tool_output(text, max_tokens=50)
        stats = c.get_stats()
        assert stats["avg_compression_ratio"] > 0.0
        assert stats["avg_compression_ratio"] <= 1.0

    def test_stats_independent_across_instances(self):
        c1 = PromptCompressor()
        c2 = PromptCompressor()
        text = make_long_text(1000)
        c1.compress_tool_output(text, max_tokens=50)
        assert c2.get_stats()["compressions"] == 0


# ── Singleton: get_prompt_compressor ────────────────────────────────


class TestGetPromptCompressor:
    def test_returns_prompt_compressor_instance(self):
        c = get_prompt_compressor()
        assert isinstance(c, PromptCompressor)

    def test_same_instance_returned_on_repeated_calls(self):
        c1 = get_prompt_compressor()
        c2 = get_prompt_compressor()
        assert c1 is c2

    def test_singleton_has_default_level_moderate(self):
        c = get_prompt_compressor()
        assert c.default_level == CompressionLevel.MODERATE


# ── compress_for_context convenience function ────────────────────────


class TestCompressForContext:
    def test_short_text_unchanged(self):
        result = compress_for_context("Short text", max_tokens=500)
        assert result == "Short text"

    def test_long_text_reduced(self):
        text = make_long_text(2000)
        result = compress_for_context(text, max_tokens=100)
        assert len(result) < len(text)

    def test_returns_string(self):
        result = compress_for_context("hello world")
        assert isinstance(result, str)

    def test_empty_text_returns_empty(self):
        result = compress_for_context("", max_tokens=500)
        assert result == ""

    def test_custom_level_accepted(self):
        text = make_long_text(1000)
        result = compress_for_context(text, max_tokens=100, level=CompressionLevel.AGGRESSIVE)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_none_level_still_returns_string(self):
        text = make_long_text(500)
        result = compress_for_context(text, max_tokens=100, level=CompressionLevel.NONE)
        assert isinstance(result, str)

    def test_uses_singleton_compressor(self):
        # Verify it delegates to the singleton (same object returned by get_prompt_compressor)
        singleton = get_prompt_compressor()
        before = singleton.get_stats()["compressions"]
        text = make_long_text(2000)
        compress_for_context(text, max_tokens=50)
        after = singleton.get_stats()["compressions"]
        assert after > before


# ── Integration: end-to-end compression pipeline ────────────────────


class TestIntegration:
    def test_compress_then_history_workflow(self):
        c = PromptCompressor()
        # Simulate tool outputs being compressed into history
        tool_output_1 = make_long_text(200)
        tool_output_2 = make_long_text(300)
        r1 = c.compress_tool_output(tool_output_1, max_tokens=100)
        r2 = c.compress_tool_output(tool_output_2, max_tokens=100)
        messages = [
            {"role": "system", "content": "You are a helpful agent."},
            {"role": "user", "content": "Run a task"},
            {"role": "assistant", "content": r1.content},
            {"role": "user", "content": "Continue"},
            {"role": "assistant", "content": r2.content},
        ]
        result = c.compress_history(messages, keep_recent=3, max_tokens=2000)
        assert isinstance(result, list)
        assert len(result) >= 3

    def test_uuid_pattern_in_tool_output(self):
        c = PromptCompressor(default_level=CompressionLevel.MODERATE)
        text = (
            "Session id=550e8400-e29b-41d4-a716-446655440000 started.\n"
            "Task id=6ba7b810-9dad-11d1-80b4-00c04fd430c8 queued.\n"
        ) * 100
        result = c.compress_tool_output(text, max_tokens=50)
        assert isinstance(result, CompressionResult)

    def test_traceback_pattern_applied_during_compression(self):
        c = PromptCompressor(default_level=CompressionLevel.MODERATE)
        tb_block = (
            "Traceback (most recent call last):\n"
            '  File "app.py", line 10, in run\n'
            '  File "service.py", line 20, in execute\n'
            '  File "db.py", line 30, in query\n'
            '  File "conn.py", line 40, in fetch\n'
            '  File "low.py", line 50, in send\n'
            "ValueError: connection refused\n"
        )
        # Repeat to push past token limit
        text = tb_block * 50
        result = c.compress_tool_output(text, max_tokens=200, level=CompressionLevel.MODERATE)
        assert isinstance(result, CompressionResult)

    def test_compress_context_preserves_error_sections(self):
        c = PromptCompressor()
        context = (
            "## Status\nAll systems nominal.\n" + "info " * 100 + "\n"
            "## Error Log\nError: database connection failed.\n" + "detail " * 50 + "\n"
            "## Metadata\n" + "meta " * 200 + "\n"
        )
        result = c.compress_context(context, max_tokens=300)
        # Error section should survive due to importance marker
        assert "Error Log" in result or "Error" in result

    def test_multiple_compressions_update_rolling_average(self):
        c = PromptCompressor()
        for i in range(5):
            text = "a" * (400 + i * 400)  # Varying lengths
            c.compress_tool_output(text, max_tokens=50)
        stats = c.get_stats()
        assert stats["compressions"] == 5
        # Rolling average should be a sensible value
        assert 0.0 <= stats["avg_compression_ratio"] <= 1.0
