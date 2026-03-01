"""Tests for TokenBudgetManager policies and compression context preservation."""

from app.domain.services.agents.token_budget_manager import BudgetAction, TokenBudgetManager


class TestBudgetPolicy:
    """Threshold policy mapping for token budget enforcement."""

    def _make_manager(self):
        from unittest.mock import MagicMock

        token_manager = MagicMock()
        token_manager.count_messages_tokens.return_value = 0
        return TokenBudgetManager(token_manager)

    def test_enforce_budget_policy_thresholds(self):
        mgr = self._make_manager()
        assert mgr.enforce_budget_policy(0.10) == BudgetAction.NORMAL
        assert mgr.enforce_budget_policy(0.90) == BudgetAction.REDUCE_VERBOSITY
        assert mgr.enforce_budget_policy(0.95) == BudgetAction.FORCE_CONCLUDE
        assert mgr.enforce_budget_policy(0.98) == BudgetAction.FORCE_HARD_STOP_NUDGE
        assert mgr.enforce_budget_policy(0.99) == BudgetAction.HARD_STOP_TOOLS


class TestExtractFailureLessons:
    """Test _extract_failure_lessons method."""

    def _make_manager(self):
        """Create a TokenBudgetManager with a mock token manager."""
        from unittest.mock import MagicMock

        token_manager = MagicMock()
        token_manager.count_messages_tokens.return_value = 0
        return TokenBudgetManager(token_manager)

    def test_no_errors_returns_none(self):
        """Messages without errors should return None."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "File written successfully."},
            {"role": "tool", "content": "Search returned 5 results."},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is None

    def test_module_not_found_extracted(self):
        """ModuleNotFoundError should be extracted."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "Traceback:\nModuleNotFoundError: No module named 'plotly'"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        assert "plotly" in result
        assert "ModuleNotFoundError" in result

    def test_import_error_extracted(self):
        """ImportError should be extracted."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "ImportError: cannot import name 'Chart' from 'plotly'"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        assert "ImportError" in result

    def test_deduplication(self):
        """Same error appearing multiple times should be deduplicated."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "ModuleNotFoundError: No module named 'plotly'"},
            {"role": "tool", "content": "ModuleNotFoundError: No module named 'plotly'"},
            {"role": "tool", "content": "ModuleNotFoundError: No module named 'plotly'"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        # Count occurrences of "plotly" — should appear once (deduplicated)
        assert result.count("plotly") == 1

    def test_multiple_different_errors(self):
        """Different errors should all be extracted."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "ModuleNotFoundError: No module named 'plotly'"},
            {"role": "tool", "content": "FileNotFoundError: [Errno 2] No such file: '/tmp/data.csv'"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        assert "plotly" in result
        assert "FileNotFoundError" in result

    def test_non_tool_messages_ignored(self):
        """Only role=tool messages should be scanned."""
        mgr = self._make_manager()
        messages = [
            {"role": "user", "content": "ModuleNotFoundError: No module named 'plotly'"},
            {"role": "assistant", "content": "ImportError: something"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is None

    def test_size_guard_caps_output(self):
        """Output should be capped at 500 characters."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": f"ModuleNotFoundError: No module named 'pkg{i}'"} for i in range(50)
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        assert len(result) <= 500

    def test_compression_context_tag_present(self):
        """Output should contain the [COMPRESSION_CONTEXT] tag."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "ModuleNotFoundError: No module named 'plotly'"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        assert "[COMPRESSION_CONTEXT]" in result

    def test_permission_denied_extracted(self):
        """Permission denied errors should be extracted."""
        mgr = self._make_manager()
        messages = [
            {"role": "tool", "content": "Error: Permission denied: /etc/shadow"},
        ]
        result = mgr._extract_failure_lessons(messages)
        assert result is not None
        assert "Permission denied" in result
