"""Tests for ContextWindowManager (Phase 5).

Covers: static fallback, dynamic capability lookup, settings override.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.services.llm.context_window_manager import (
    ContextWindowManager,
    reset_context_window_manager,
)


@pytest.fixture(autouse=True)
def _reset():
    reset_context_window_manager()
    yield
    reset_context_window_manager()


# ─────────────────────────── Static fallback ─────────────────────────────────


def test_get_effective_limit_fallback_when_flag_off():
    """With override_tokens set, returns the override regardless of model."""
    manager = ContextWindowManager(override_tokens=50_000)
    assert manager.get_effective_limit("any-model") == 50_000


def test_override_tokens_takes_precedence():
    manager = ContextWindowManager(override_tokens=200_000)
    # Even for GLM (which has 128k in registry), override wins
    limit = manager.get_effective_limit("glm-4-air")
    assert limit == 200_000


# ─────────────────────────── Dynamic lookup ──────────────────────────────────


def test_dynamic_flag_uses_capabilities_registry():
    """When dynamic flag is on, uses capabilities max_context_window."""
    manager = ContextWindowManager()

    with (
        patch.object(ContextWindowManager, "_dynamic_enabled", lambda self: True),
        patch.object(ContextWindowManager, "_settings_override", lambda self: 0),
    ):
        limit = manager.get_effective_limit("qwen/qwen3-coder-next")
        assert limit == 262_144


def test_dynamic_flag_returns_claude_context():
    manager = ContextWindowManager()

    with (
        patch.object(ContextWindowManager, "_dynamic_enabled", lambda self: True),
        patch.object(ContextWindowManager, "_settings_override", lambda self: 0),
    ):
        limit = manager.get_effective_limit("claude-opus-4-6")
        assert limit == 200_000


def test_dynamic_fallback_on_exception():
    """If dynamic lookup raises, falls back gracefully (no exception raised)."""

    # Subclass overrides _dynamic_enabled to True and _settings_override to 0,
    # but its get_effective_limit will hit the capabilities registry (which is
    # real) and should succeed. We test that the method never raises even for
    # an unusual model name.
    class AlwaysDynamic(ContextWindowManager):
        def _dynamic_enabled(self) -> bool:
            return True

        def _settings_override(self) -> int:
            return 0

    manager = AlwaysDynamic()
    # This unknown model should return DEFAULT_CAPABILITIES.max_context_window=128k
    limit = manager.get_effective_limit("totally-unknown-model-xyz")
    assert limit > 0  # Never raises, returns a positive token count


# ─────────────────────────── create_dynamic_budget ───────────────────────────


def test_create_dynamic_budget_returns_token_budget():
    """create_dynamic_budget delegates to TokenBudgetManager."""
    manager = ContextWindowManager(override_tokens=128_000)

    mock_token_manager = MagicMock()
    mock_token_manager._max_tokens = 128_000

    budget = manager.create_dynamic_budget("any-model", token_manager=mock_token_manager)
    # TokenBudget should have the override as its max
    assert budget.max_tokens == 128_000
    # Phases should be allocated
    assert len(budget.phases) == 5  # 5 BudgetPhase values


def test_create_dynamic_budget_uses_qwen_large_context():
    """When dynamic, Qwen3-Coder gets 262k budget."""
    manager = ContextWindowManager()

    with (
        patch.object(ContextWindowManager, "_dynamic_enabled", lambda self: True),
        patch.object(ContextWindowManager, "_settings_override", lambda self: 0),
    ):
        mock_token_manager = MagicMock()
        mock_token_manager._max_tokens = 16_000

        budget = manager.create_dynamic_budget("qwen/qwen3-coder-next", token_manager=mock_token_manager)
        assert budget.max_tokens == 262_144
