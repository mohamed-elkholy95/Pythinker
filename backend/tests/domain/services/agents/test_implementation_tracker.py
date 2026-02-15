"""Unit tests for Implementation Tracker

Tests code completeness validation and multi-file analysis.

Context7 validated: pytest patterns, parameterized tests, AST testing.
"""

import pytest

from app.domain.services.agents.implementation_tracker import (
    ImplementationConfig,
    ImplementationStatus,
    ImplementationTracker,
    IncompleteReason,
    get_implementation_tracker,
)


class TestImplementationConfig:
    """Test ImplementationConfig validation."""

    def test_default_config(self):
        """Test default configuration values."""
        config = ImplementationConfig()
        assert config.check_todos is True
        assert config.check_fixmes is True
        assert config.check_placeholders is True
        assert config.check_imports is True
        assert config.check_empty_functions is True
        assert config.min_function_lines == 2
        assert config.severity_threshold == "medium"

    def test_custom_config(self):
        """Test custom configuration."""
        config = ImplementationConfig(
            check_todos=False,
            check_fixmes=False,
            check_empty_functions=False,
            severity_threshold="high",
        )
        assert config.check_todos is False
        assert config.check_fixmes is False
        assert config.check_empty_functions is False
        assert config.severity_threshold == "high"


class TestNotImplementedErrorDetection:
    """Test AST-based NotImplementedError detection."""

    def test_detects_not_implemented_error(self):
        """Test detects raise NotImplementedError()."""
        code = """
def incomplete_function():
    raise NotImplementedError("TODO: implement this")
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        assert status.status == ImplementationStatus.ERROR
        assert len(status.issues) == 1
        assert status.issues[0].reason == IncompleteReason.NOT_IMPLEMENTED_ERROR
        assert status.issues[0].severity == "high"

    def test_ignores_other_exceptions(self):
        """Test ignores other exception types."""
        code = """
def valid_function():
    if error:
        raise ValueError("valid error")
    return 42
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        # Should not detect ValueError as incomplete
        not_impl_issues = [i for i in status.issues if i.reason == IncompleteReason.NOT_IMPLEMENTED_ERROR]
        assert len(not_impl_issues) == 0


class TestEmptyFunctionDetection:
    """Test empty function body detection."""

    def test_detects_pass_only_function(self):
        """Test detects function with only pass."""
        code = """
def empty_function():
    pass
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        pass_issues = [i for i in status.issues if i.reason == IncompleteReason.PASS_ONLY]
        assert len(pass_issues) == 1
        assert pass_issues[0].severity == "medium"

    def test_detects_ellipsis_only_function(self):
        """Test detects function with only ellipsis."""
        code = """
def stub_function():
    ...
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        ellipsis_issues = [i for i in status.issues if i.reason == IncompleteReason.ELLIPSIS_ONLY]
        assert len(ellipsis_issues) == 1
        assert ellipsis_issues[0].severity == "medium"

    def test_ignores_decorated_stubs(self):
        """Test ignores decorated functions (might be intentional stubs)."""
        code = """
@abstractmethod
def stub_function():
    pass
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        # Decorated functions are ignored
        empty_issues = [
            i for i in status.issues if i.reason in (IncompleteReason.PASS_ONLY, IncompleteReason.ELLIPSIS_ONLY)
        ]
        assert len(empty_issues) == 0

    def test_detects_complete_function(self):
        """Test recognizes complete functions."""
        code = """
def complete_function():
    result = 42
    return result
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        assert status.total_functions == 1
        assert status.complete_functions == 1


class TestTODOMarkerDetection:
    """Test TODO/FIXME/placeholder marker detection."""

    def test_detects_todo_marker(self):
        """Test detects # TODO comments."""
        code = """
def function():
    # TODO: implement this
    pass
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        todo_issues = [i for i in status.issues if i.reason == IncompleteReason.TODO_MARKER]
        assert len(todo_issues) == 1
        assert todo_issues[0].severity == "low"

    def test_detects_fixme_marker(self):
        """Test detects # FIXME comments."""
        code = """
def function():
    # FIXME: this is broken
    return 42
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        fixme_issues = [i for i in status.issues if i.reason == IncompleteReason.FIXME_MARKER]
        assert len(fixme_issues) == 1
        assert fixme_issues[0].severity == "medium"

    def test_detects_placeholder_comment(self):
        """Test detects placeholder comments."""
        code = """
def function():
    # placeholder - to be implemented
    pass
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        placeholder_issues = [i for i in status.issues if i.reason == IncompleteReason.PLACEHOLDER_COMMENT]
        assert len(placeholder_issues) == 1

    def test_detects_multiple_markers(self):
        """Test detects multiple TODO/FIXME markers."""
        code = """
def function():
    # TODO: implement step 1
    pass
    # TODO: implement step 2
    # FIXME: fix bug
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        todo_count = sum(1 for i in status.issues if i.reason == IncompleteReason.TODO_MARKER)
        fixme_count = sum(1 for i in status.issues if i.reason == IncompleteReason.FIXME_MARKER)

        assert todo_count == 2
        assert fixme_count == 1

    def test_case_insensitive_detection(self):
        """Test marker detection is case-insensitive."""
        code = """
def function():
    # todo: lowercase todo
    # TODO: uppercase TODO
    # fixme: lowercase fixme
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        todo_count = sum(1 for i in status.issues if i.reason == IncompleteReason.TODO_MARKER)
        fixme_count = sum(1 for i in status.issues if i.reason == IncompleteReason.FIXME_MARKER)

        assert todo_count == 2
        assert fixme_count == 1


class TestCompletenessScoring:
    """Test completeness score calculation."""

    def test_perfect_score_for_complete_code(self):
        """Test complete code gets 1.0 score."""
        code = """
def complete_function():
    return 42

class CompleteClass:
    def method(self):
        return "done"
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        assert status.completeness_score == 1.0
        assert status.status == ImplementationStatus.COMPLETE

    def test_score_decreases_with_low_severity_issues(self):
        """Test low severity issues decrease score by 0.1 each."""
        code = """
def function():
    # TODO: add validation
    return 42
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        # 1 TODO (low severity, -0.1) = 0.9 score
        assert status.completeness_score == 0.9

    def test_score_decreases_with_medium_severity_issues(self):
        """Test medium severity issues decrease score by 0.3 each."""
        code = """
def function():
    # FIXME: this is broken
    pass
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        # 1 FIXME (medium, -0.3) + 1 pass-only (medium, -0.3) = 0.4 score
        assert status.completeness_score == pytest.approx(0.4, abs=0.01)

    def test_score_decreases_with_high_severity_issues(self):
        """Test high severity issues decrease score by 0.5 each."""
        code = """
def function():
    raise NotImplementedError()
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        # 1 NotImplementedError (high, -0.5) = 0.5 score
        assert status.completeness_score == 0.5

    def test_score_capped_at_zero(self):
        """Test score cannot go below 0.0."""
        code = """
def func1():
    raise NotImplementedError()

def func2():
    raise NotImplementedError()

def func3():
    raise NotImplementedError()
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        # 3 high severity issues = 1.5 penalty, but capped at 0.0
        assert status.completeness_score == 0.0


class TestStatusClassification:
    """Test implementation status classification."""

    def test_complete_status_at_90_percent(self):
        """Test COMPLETE status at >= 0.9 score."""
        code = """
def function():
    # TODO: minor improvement
    return 42
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        # Score = 0.9 (1 TODO)
        assert status.status == ImplementationStatus.COMPLETE

    def test_partial_status_at_60_to_90_percent(self):
        """Test PARTIAL status at 0.6-0.9 score."""
        code = """
def function():
    # TODO: item 1
    # TODO: item 2
    # TODO: item 3
    return 42
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        # Score = 0.7 (3 TODOs = -0.3)
        assert status.status == ImplementationStatus.PARTIAL

    def test_incomplete_status_at_30_to_60_percent(self):
        """Test INCOMPLETE status at 0.3-0.6 score."""
        code = """
def function():
    # FIXME: major issue
    # TODO: task 1
    # TODO: task 2
    pass
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        # Score ~= 0.4-0.5 range
        assert status.status == ImplementationStatus.INCOMPLETE

    def test_placeholder_status_below_30_percent(self):
        """Test PLACEHOLDER status at < 0.3 score."""
        code = """
def func1():
    pass

def func2():
    pass

def func3():
    pass
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        # Score ~= 0.1 (3 pass-only = -0.9)
        assert status.status == ImplementationStatus.PLACEHOLDER

    def test_error_status_with_high_severity(self):
        """Test ERROR status when high-severity issues present."""
        code = """
def function():
    raise NotImplementedError()
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", code)

        assert status.status == ImplementationStatus.ERROR


class TestMultiFileAnalysis:
    """Test multi-file tracking and aggregation."""

    def test_aggregates_multiple_files(self):
        """Test aggregates analysis across multiple files."""
        files = {
            "complete.py": "def func():\n    return 42",
            "partial.py": "def func():\n    # TODO: finish\n    pass",
            "incomplete.py": "def func():\n    raise NotImplementedError()",
        }

        tracker = ImplementationTracker()
        report = tracker.track_multiple(files)

        assert report.files_analyzed == 3
        assert report.total_issues > 0

    def test_overall_status_is_worst_case(self):
        """Test overall status is worst-case across files."""
        files = {
            "complete.py": "def func():\n    return 42",
            "error.py": "def func():\n    raise NotImplementedError()",
        }

        tracker = ImplementationTracker()
        report = tracker.track_multiple(files)

        # Worst case is ERROR
        assert report.overall_status == ImplementationStatus.ERROR

    def test_overall_completeness_is_average(self):
        """Test overall completeness is average score."""
        files = {
            "file1.py": "def func():\n    return 42",  # 100% complete
            "file2.py": "def func():\n    # TODO: fix\n    return 42",  # 90% complete
        }

        tracker = ImplementationTracker()
        report = tracker.track_multiple(files)

        # Average = (1.0 + 0.9) / 2 = 0.95
        assert report.completeness_score == pytest.approx(0.95, abs=0.01)

    def test_high_priority_issues_extracted(self):
        """Test high-priority issues are extracted."""
        files = {
            "file1.py": "def func():\n    raise NotImplementedError()",
            "file2.py": "def func():\n    # TODO: minor\n    return 42",
        }

        tracker = ImplementationTracker()
        report = tracker.track_multiple(files)

        # Should have 1 high-priority issue (NotImplementedError)
        assert len(report.high_priority_issues) == 1
        assert report.high_priority_issues[0].severity == "high"


class TestCompletionChecklist:
    """Test completion checklist generation."""

    def test_generates_checklist_for_incomplete_files(self):
        """Test checklist includes incomplete files."""
        files = {
            "complete.py": "def func():\n    return 42",
            "partial.py": "def func():\n    # TODO: finish\n    pass",
        }

        tracker = ImplementationTracker()
        report = tracker.track_multiple(files)

        checklist = report.completion_checklist

        # Should have item for partial.py, not complete.py
        assert any("partial.py" in item for item in checklist)
        assert not any("complete.py" in item and "complete (0 issues" not in item for item in checklist)

    def test_includes_high_priority_suggestions(self):
        """Test checklist includes high-priority suggestions."""
        files = {
            "error.py": "def func():\n    raise NotImplementedError('implement me')",
        }

        tracker = ImplementationTracker()
        report = tracker.track_multiple(files)

        checklist = report.completion_checklist

        # Should have suggestion for NotImplementedError
        checklist_text = "\n".join(checklist)
        assert "Implement" in checklist_text or "implement" in checklist_text

    def test_limits_suggestions_per_file(self):
        """Test checklist limits suggestions per file."""
        # Create file with many issues
        code = "\n".join([f"def func{i}():\n    raise NotImplementedError()\n" for i in range(10)])

        files = {"many_issues.py": code}

        tracker = ImplementationTracker()
        report = tracker.track_multiple(files)

        checklist = report.completion_checklist

        # Should limit to top 3 suggestions per file (plus file-level item)
        # Count lines that start with "  -" (suggestions)
        suggestion_count = sum(1 for item in checklist if item.strip().startswith("- Line"))
        assert suggestion_count <= 3


class TestSyntaxErrorHandling:
    """Test handling of syntax errors."""

    def test_reports_syntax_error_as_high_severity(self):
        """Test syntax errors are reported as high severity."""
        invalid_code = """
def function()
    # Missing colon
    return 42
"""
        tracker = ImplementationTracker()
        status = tracker.track_file("test.py", invalid_code)

        # Should have at least one issue
        assert len(status.issues) > 0
        # Should report error
        assert any(i.severity == "high" for i in status.issues)


class TestConfigurationOptions:
    """Test configuration options."""

    def test_disable_todo_checks(self):
        """Test can disable TODO checks."""
        code = """
def function():
    # TODO: implement this
    return 42
"""
        config = ImplementationConfig(check_todos=False)
        tracker = ImplementationTracker(config)
        status = tracker.track_file("test.py", code)

        todo_issues = [i for i in status.issues if i.reason == IncompleteReason.TODO_MARKER]
        assert len(todo_issues) == 0

    def test_disable_fixme_checks(self):
        """Test can disable FIXME checks."""
        code = """
def function():
    # FIXME: fix this
    return 42
"""
        config = ImplementationConfig(check_fixmes=False)
        tracker = ImplementationTracker(config)
        status = tracker.track_file("test.py", code)

        fixme_issues = [i for i in status.issues if i.reason == IncompleteReason.FIXME_MARKER]
        assert len(fixme_issues) == 0

    def test_disable_empty_function_checks(self):
        """Test can disable empty function checks."""
        code = """
def stub():
    pass
"""
        config = ImplementationConfig(check_empty_functions=False)
        tracker = ImplementationTracker(config)
        status = tracker.track_file("test.py", code)

        empty_issues = [
            i for i in status.issues if i.reason in (IncompleteReason.PASS_ONLY, IncompleteReason.ELLIPSIS_ONLY)
        ]
        assert len(empty_issues) == 0


class TestSingletonFactory:
    """Test singleton factory pattern."""

    def test_returns_same_instance(self):
        """Test factory returns same instance on multiple calls."""
        instance1 = get_implementation_tracker()
        instance2 = get_implementation_tracker()

        assert instance1 is instance2

    def test_config_only_used_on_first_call(self):
        """Test config is only applied on first factory call."""
        config1 = ImplementationConfig(check_todos=False)
        instance1 = get_implementation_tracker(config1)

        # Second call with different config should return same instance
        config2 = ImplementationConfig(check_todos=True)
        instance2 = get_implementation_tracker(config2)

        assert instance1 is instance2
        # Config from first call is preserved
        assert instance1.config.check_todos is False


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
