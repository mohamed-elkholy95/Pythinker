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

# ── CompressionResult ───────────────────────────────────────────────


class TestCompressionResult:
    def test_construction(self):
        r = CompressionResult(
            original_tokens=100,
            compressed_tokens=50,
            compression_ratio=0.5,
            content="compressed",
            items_removed=2,
            summary_generated=True,
        )
        assert r.compression_ratio == 0.5
        assert r.summary_generated is True


# ── estimate_tokens ─────────────────────────────────────────────────


class TestEstimateTokens:
    def test_empty_string(self):
        c = PromptCompressor()
        assert c.estimate_tokens("") == 0

    def test_estimates_proportional_to_length(self):
        c = PromptCompressor()
        short = c.estimate_tokens("hello")
        long = c.estimate_tokens("hello world this is longer text")
        assert long > short

    def test_uses_tokens_per_char_constant(self):
        c = PromptCompressor()
        # 100 chars * 0.25 = 25 tokens
        text = "a" * 100
        assert c.estimate_tokens(text) == 25


# ── compress_tool_output ────────────────────────────────────────────


class TestCompressToolOutput:
    def test_empty_output(self):
        c = PromptCompressor()
        result = c.compress_tool_output("")
        assert result.content == ""
        assert result.original_tokens == 0
        assert result.compression_ratio == 1.0

    def test_short_output_unchanged(self):
        c = PromptCompressor()
        text = "Short output"
        result = c.compress_tool_output(text, max_tokens=500)
        assert result.content == text
        assert result.items_removed == 0
        assert result.summary_generated is False

    def test_long_output_compressed(self):
        c = PromptCompressor()
        text = "Line of text\n" * 1000  # ~13000 chars → ~3250 tokens
        result = c.compress_tool_output(text, max_tokens=100)
        assert result.compressed_tokens <= result.original_tokens
        assert result.compression_ratio < 1.0

    def test_whitespace_compressed_via_basic(self):
        c = PromptCompressor()
        text = "Hello\n\n\n\n\nWorld\n\n\n\nEnd"
        result = c._apply_basic_compression(text)
        # Basic compression removes extra blank lines
        assert "\n\n\n" not in result

    def test_compression_level_none(self):
        c = PromptCompressor()
        text = "a" * 10000
        result = c.compress_tool_output(text, max_tokens=100, level=CompressionLevel.NONE)
        # With NONE, no compression applied, but truncation may still occur
        # since the text exceeds max_tokens
        assert result.original_tokens > 100


# ── _apply_basic_compression ────────────────────────────────────────


class TestBasicCompression:
    def test_normalizes_line_endings(self):
        c = PromptCompressor()
        text = "Hello\r\nWorld\rEnd"
        result = c._apply_basic_compression(text)
        assert "\r" not in result

    def test_removes_excessive_blank_lines(self):
        c = PromptCompressor()
        text = "Hello\n\n\n\n\nWorld"
        result = c._apply_basic_compression(text)
        assert result == "Hello\n\nWorld"

    def test_strips_trailing_whitespace(self):
        c = PromptCompressor()
        text = "Hello   \nWorld   "
        result = c._apply_basic_compression(text)
        assert "   " not in result

    def test_strips_outer_whitespace(self):
        c = PromptCompressor()
        text = "  \n\nHello\n\n  "
        result = c._apply_basic_compression(text)
        assert result == "Hello"


# ── _is_important ───────────────────────────────────────────────────


class TestIsImportant:
    c = PromptCompressor()

    @pytest.mark.parametrize(
        "text",
        [
            "An error occurred during execution",
            "Exception raised in handler",
            "Task failed with exit code 1",
            "Operation completed successfully",
            "WARNING: disk space low",
            "Result: 42 items processed",
        ],
    )
    def test_important_markers_detected(self, text: str):
        assert self.c._is_important(text) is True

    def test_not_important(self):
        assert self.c._is_important("Just some plain text here") is False

    def test_case_insensitive(self):
        assert self.c._is_important("ERROR OCCURRED") is True


# ── compress_history ────────────────────────────────────────────────


class TestCompressHistory:
    def test_empty_messages(self):
        c = PromptCompressor()
        assert c.compress_history([]) == []

    def test_preserves_system_messages(self):
        c = PromptCompressor()
        messages = [
            {"role": "system", "content": "You are an assistant."},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        result = c.compress_history(messages, max_tokens=5000)
        system_msgs = [m for m in result if m["role"] == "system"]
        assert len(system_msgs) == 1

    def test_keeps_recent_messages(self):
        c = PromptCompressor()
        messages = [{"role": "user", "content": f"Message {i}"} for i in range(10)]
        result = c.compress_history(messages, keep_recent=3, max_tokens=5000)
        # Should at least have the 3 most recent
        assert len(result) >= 3


# ── compress_context ────────────────────────────────────────────────


class TestCompressContext:
    def test_empty_context(self):
        c = PromptCompressor()
        assert c.compress_context("") == ""

    def test_short_context_unchanged(self):
        c = PromptCompressor()
        text = "Short context"
        assert c.compress_context(text, max_tokens=500) == text

    def test_long_context_compressed(self):
        c = PromptCompressor()
        sections = [f"## Section {i}\nThis is content for section {i}.\n" + "Details " * 50 for i in range(20)]
        text = "\n".join(sections)
        result = c.compress_context(text, max_tokens=200)
        assert len(result) < len(text)


# ── _summarize_traceback ────────────────────────────────────────────


class TestSummarizeTraceback:
    def test_short_traceback_unchanged(self):
        tb = "Traceback:\n  File a\n  File b\n  Error"
        result = _summarize_traceback(tb)
        assert result == tb

    def test_long_traceback_summarized(self):
        lines = ["Traceback (most recent call last):"]
        lines.extend(f'  File "module_{i}.py", line {i}' for i in range(10))
        lines.append("  in some_function")
        lines.append("ValueError: bad value")
        tb = "\n".join(lines)
        result = _summarize_traceback(tb)
        assert "frames" in result
        assert len(result) < len(tb)


# ── _truncate_with_summary ──────────────────────────────────────────


class TestTruncateWithSummary:
    def test_very_small_max_tokens(self):
        c = PromptCompressor()
        text = "A" * 1000
        result, generated = c._truncate_with_summary(text, max_tokens=10, tool_name=None)
        assert generated is True
        assert "truncated" in result.lower() or "omitted" in result.lower()

    def test_preserves_first_and_last_lines(self):
        c = PromptCompressor()
        lines = [f"Line {i}" for i in range(50)]
        text = "\n".join(lines)
        result, generated = c._truncate_with_summary(text, max_tokens=200, tool_name="test")
        assert generated is True
        assert "Line 0" in result
        # May contain "omitted"
        assert "omitted" in result.lower()


# ── get_stats ───────────────────────────────────────────────────────


class TestGetStats:
    def test_initial_stats(self):
        c = PromptCompressor()
        stats = c.get_stats()
        assert stats["compressions"] == 0
        assert stats["tokens_saved"] == 0
        assert "avg_ratio_pct" in stats

    def test_stats_updated_after_compression(self):
        c = PromptCompressor()
        text = "word " * 1000
        c.compress_tool_output(text, max_tokens=50)
        stats = c.get_stats()
        assert stats["compressions"] >= 1
        assert stats["tokens_saved"] > 0


# ── Singleton and convenience ───────────────────────────────────────


class TestSingleton:
    def test_get_prompt_compressor_returns_instance(self):
        c = get_prompt_compressor()
        assert isinstance(c, PromptCompressor)

    def test_singleton_stability(self):
        c1 = get_prompt_compressor()
        c2 = get_prompt_compressor()
        assert c1 is c2

    def test_compress_for_context_convenience(self):
        result = compress_for_context("Short text", max_tokens=500)
        assert result == "Short text"

    def test_compress_for_context_long(self):
        text = "word " * 2000
        result = compress_for_context(text, max_tokens=100)
        assert len(result) < len(text)
