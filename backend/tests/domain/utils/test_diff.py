"""Tests for domain diff utility."""

import pytest

from app.domain.utils.diff import build_unified_diff


@pytest.mark.unit
class TestBuildUnifiedDiff:
    """Tests for build_unified_diff function."""

    def test_identical_content_returns_empty(self) -> None:
        assert build_unified_diff("hello", "hello", "file.py") == ""

    def test_both_none_returns_empty(self) -> None:
        assert build_unified_diff(None, None, "file.py") == ""

    def test_added_content(self) -> None:
        diff = build_unified_diff(None, "new content\n", "file.py")
        assert "+new content" in diff
        assert "a/file.py" in diff
        assert "b/file.py" in diff

    def test_removed_content(self) -> None:
        diff = build_unified_diff("old content\n", None, "file.py")
        assert "-old content" in diff

    def test_modified_content(self) -> None:
        diff = build_unified_diff("line1\nline2\n", "line1\nline2_changed\n", "test.py")
        assert "-line2" in diff
        assert "+line2_changed" in diff

    def test_path_included(self) -> None:
        diff = build_unified_diff("a\n", "b\n", "src/main.py")
        assert "a/src/main.py" in diff
        assert "b/src/main.py" in diff

    def test_context_lines_parameter(self) -> None:
        before = "\n".join(f"line{i}" for i in range(20)) + "\n"
        after = before.replace("line10", "changed10")
        diff_default = build_unified_diff(before, after, "f.py", context_lines=3)
        diff_wide = build_unified_diff(before, after, "f.py", context_lines=10)
        # More context = longer diff
        assert len(diff_wide) >= len(diff_default)

    def test_truncation(self) -> None:
        before = "\n".join(f"line{i}" for i in range(100)) + "\n"
        after = "\n".join(f"changed{i}" for i in range(100)) + "\n"
        diff = build_unified_diff(before, after, "big.py", max_chars=100)
        assert "... (diff truncated)" in diff
        assert len(diff) <= 200  # max_chars + truncation notice

    def test_no_truncation_when_small(self) -> None:
        diff = build_unified_diff("a\n", "b\n", "small.py", max_chars=20000)
        assert "truncated" not in diff

    def test_multiline_diff(self) -> None:
        before = "line1\nline2\nline3\n"
        after = "line1\nline2_mod\nline3\nline4\n"
        diff = build_unified_diff(before, after, "f.py")
        assert "-line2" in diff
        assert "+line2_mod" in diff
        assert "+line4" in diff
