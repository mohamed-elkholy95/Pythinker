from app.domain.services.prompts.terminal_mastery import (
    TERMINAL_MASTERY_RULES,
    TOOL_PREFERENCE_HINTS,
)


def test_terminal_mastery_rules_non_empty():
    assert len(TERMINAL_MASTERY_RULES) > 200
    assert "ripgrep" in TERMINAL_MASTERY_RULES.lower() or "rg" in TERMINAL_MASTERY_RULES
    assert "jq" in TERMINAL_MASTERY_RULES
    assert "curl" in TERMINAL_MASTERY_RULES


def test_tool_preference_hints_non_empty():
    assert len(TOOL_PREFERENCE_HINTS) > 100
    assert "shell_exec" in TOOL_PREFERENCE_HINTS or "terminal" in TOOL_PREFERENCE_HINTS.lower()


def test_terminal_mastery_includes_pipe_guidance():
    assert "pipe" in TERMINAL_MASTERY_RULES.lower() or "|" in TERMINAL_MASTERY_RULES


def test_terminal_mastery_includes_error_handling():
    assert "pipefail" in TERMINAL_MASTERY_RULES or "set -e" in TERMINAL_MASTERY_RULES
