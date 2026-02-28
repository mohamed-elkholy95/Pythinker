"""Dynamic context window manager (domain layer).

Replaces static 128k token budget assumptions with model-aware allocation.
Reads the actual ``max_context_window`` from the ``ProviderCapabilities``
registry (Phase 3) and creates a ``TokenBudget`` scaled to that value.

When ``feature_llm_dynamic_context=False`` (default), the manager returns
the same hard-coded value as before — zero behaviour change.

Usage::

    manager = ContextWindowManager()
    # Dynamic (Phase 5 flag=True):
    limit = manager.get_effective_limit("qwen/qwen3-coder-next")  # → 262144
    budget = manager.create_dynamic_budget("qwen/qwen3-coder-next", token_manager)

    # Static fallback (flag=False):
    limit = manager.get_effective_limit("qwen/qwen3-coder-next")  # → settings.max_tokens
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from app.domain.services.agents.token_budget_manager import TokenBudget

# Default assumed context window when dynamic detection is off or fails.
_STATIC_FALLBACK_TOKENS = 128_000


class ContextWindowManager:
    """Resolve the effective context window for a model and create budgets.

    Args:
        override_tokens: Hard override (0 = auto-detect from settings/caps).
    """

    def __init__(self, override_tokens: int = 0) -> None:
        self._override = override_tokens

    def get_effective_limit(self, model_name: str, api_base: str | None = None) -> int:
        """Return the effective context window for *model_name*.

        Priority:
        1. ``llm_context_window_override`` from settings (> 0).
        2. ``feature_llm_dynamic_context=True`` → capabilities registry.
        3. ``settings.max_tokens`` (static fallback).
        4. Module-level ``_STATIC_FALLBACK_TOKENS`` (last resort).

        Args:
            model_name: Full model identifier (e.g. ``"qwen/qwen3-coder-next"``).
            api_base: Optional provider base URL for capability override.

        Returns:
            Token count for the context window.
        """
        # 1. Explicit hard override (set_override or settings)
        override = self._override or self._settings_override()
        if override > 0:
            logger.debug("Context window override=%d for model=%s", override, model_name)
            return override

        # 2. Dynamic detection via capabilities registry
        if self._dynamic_enabled():
            try:
                from app.domain.external.llm_capabilities import get_capabilities

                caps = get_capabilities(model_name, api_base)
                limit = caps.max_context_window
                logger.debug(
                    "Dynamic context window: model=%s → %d tokens", model_name, limit
                )
                return limit
            except Exception as exc:
                logger.warning("Dynamic context detection failed: %s — using fallback", exc)

        # 3. Settings value
        try:
            from app.core.config import get_settings

            settings = get_settings()
            return getattr(settings, "max_tokens", _STATIC_FALLBACK_TOKENS)
        except Exception as exc:
            logger.debug("get_effective_limit: settings fallback failed: %s", exc)

        # 4. Last resort
        return _STATIC_FALLBACK_TOKENS

    def create_dynamic_budget(
        self,
        model_name: str,
        token_manager: Any,
        api_base: str | None = None,
    ) -> TokenBudget:
        """Create a ``TokenBudget`` scaled to the model's actual context window.

        Args:
            model_name: Model identifier.
            token_manager: Existing ``TokenManager`` instance (provides limits).
            api_base: Optional base URL for capability override.

        Returns:
            ``TokenBudget`` with per-phase allocations proportional to the
            model's actual ``max_context_window``.
        """
        from app.domain.services.agents.token_budget_manager import TokenBudgetManager

        limit = self.get_effective_limit(model_name, api_base)
        mgr = TokenBudgetManager(token_manager=token_manager)
        return mgr.create_budget(max_tokens=limit)

    # ─────────── Private ─────────────────────────────────────────────────────

    def _settings_override(self) -> int:
        """Read ``llm_context_window_override`` from settings (0 = off)."""
        try:
            from app.core.config import get_settings

            return getattr(get_settings(), "llm_context_window_override", 0)
        except Exception:
            return 0

    def _dynamic_enabled(self) -> bool:
        """Return True when ``feature_llm_dynamic_context`` flag is on."""
        try:
            from app.core.config import get_settings

            return bool(getattr(get_settings(), "feature_llm_dynamic_context", False))
        except Exception:
            return False


# ─────────────────────────── Singleton ───────────────────────────────────────

_manager_instance: ContextWindowManager | None = None


def get_context_window_manager() -> ContextWindowManager:
    """Return the process-level singleton ContextWindowManager."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = ContextWindowManager()
    return _manager_instance


def reset_context_window_manager() -> None:
    """Reset the singleton (for testing)."""
    global _manager_instance
    _manager_instance = None
