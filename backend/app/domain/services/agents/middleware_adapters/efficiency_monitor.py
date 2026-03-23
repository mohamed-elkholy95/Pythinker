"""Middleware adapter for ToolEfficiencyMonitor.

Also enforces a per-step browser navigation budget to prevent the agent from
endlessly visiting URLs.  The budget is generous enough for research tasks
(6 unique URLs per step) but stops the 8-10 sequential navigation loops
observed in production (each costing ~6s = 50+ seconds wasted).
"""

from __future__ import annotations

import logging

from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.base_middleware import BaseMiddleware
from app.domain.services.agents.middleware import (
    MiddlewareContext,
    MiddlewareResult,
    MiddlewareSignal,
    ToolCallInfo,
)
from app.domain.services.agents.tool_efficiency_monitor import ToolEfficiencyMonitor

logger = logging.getLogger(__name__)

# Max browser navigations per execution step.  After this limit the agent
# is told to synthesize what it has.  Research tasks typically need 3-5 URLs;
# 6 gives headroom without allowing runaway browsing loops.
_MAX_BROWSER_NAVIGATIONS_PER_STEP = 6
_BROWSER_NAV_TOOLS = frozenset({"browser_navigate", "browser_get_content", "search"})


class EfficiencyMonitorMiddleware(BaseMiddleware):
    """Detects analysis paralysis and enforces browser navigation budgets."""

    def __init__(
        self,
        monitor: ToolEfficiencyMonitor | None = None,
        research_mode: str | None = None,
    ) -> None:
        self._monitor = monitor or ToolEfficiencyMonitor(research_mode=research_mode)
        # Per-step browser navigation counter.  Resets when the step changes
        # (detected via ctx.metadata["current_step_index"]).
        self._browser_nav_count = 0
        self._browser_nav_urls: set[str] = set()
        self._current_step_index: int = -1

    @property
    def name(self) -> str:
        return "efficiency_monitor"

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        """Enforce browser navigation budget before expensive browser calls."""
        # Reset counter when step changes
        step_idx = ctx.metadata.get("current_step_index", 0)
        if step_idx != self._current_step_index:
            self._current_step_index = step_idx
            self._browser_nav_count = 0
            self._browser_nav_urls.clear()

        if tool_call.function_name not in _BROWSER_NAV_TOOLS:
            return MiddlewareResult.ok()

        # Check for duplicate URL visits (same URL already visited this step)
        url = (tool_call.arguments or {}).get("url", "")
        if url and url in self._browser_nav_urls:
            logger.info(
                "Browser budget: skipping duplicate URL visit: %s",
                url[:80],
            )
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=(
                    "Already visited this URL in the current step. "
                    "Use the content you already have instead of revisiting."
                ),
            )

        # Check navigation budget
        if self._browser_nav_count >= _MAX_BROWSER_NAVIGATIONS_PER_STEP:
            logger.info(
                "Browser navigation budget exhausted (%d/%d) — blocking %s",
                self._browser_nav_count,
                _MAX_BROWSER_NAVIGATIONS_PER_STEP,
                tool_call.function_name,
            )
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=(
                    f"Browser navigation budget reached ({_MAX_BROWSER_NAVIGATIONS_PER_STEP} "
                    f"pages visited this step). You have enough information — synthesize "
                    f"your findings and produce output instead of visiting more pages."
                ),
            )

        return MiddlewareResult.ok()

    async def after_tool_call(
        self, ctx: MiddlewareContext, tool_call: ToolCallInfo, result: ToolResult
    ) -> MiddlewareResult:
        """Record tool call for efficiency tracking and browser budget."""
        self._monitor.record(tool_call.function_name)

        # Track browser navigations for budget enforcement
        if tool_call.function_name in _BROWSER_NAV_TOOLS:
            self._browser_nav_count += 1
            url = (tool_call.arguments or {}).get("url", "")
            if url:
                self._browser_nav_urls.add(url)

        return MiddlewareResult.ok()

    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        """Check efficiency and inject nudge if imbalanced."""
        signal = self._monitor.check_efficiency()

        if signal.hard_stop:
            return MiddlewareResult(
                signal=MiddlewareSignal.FORCE,
                message=signal.nudge_message or "Analysis paralysis detected — force-advancing.",
            )

        if not signal.is_balanced and signal.nudge_message:
            return MiddlewareResult(
                signal=MiddlewareSignal.INJECT,
                message=signal.nudge_message,
            )

        return MiddlewareResult.ok()
