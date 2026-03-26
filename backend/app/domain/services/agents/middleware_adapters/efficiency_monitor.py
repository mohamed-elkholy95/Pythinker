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
# Now configurable via settings.max_browser_navigations_per_step (default 6).
_BROWSER_NAV_TOOLS = frozenset({"browser_navigate", "browser_get_content", "search"})


def _get_browser_nav_budget() -> int:
    """Return the browser navigation budget from settings (cached per-process)."""
    try:
        from app.core.config import get_settings

        return getattr(get_settings(), "max_browser_navigations_per_step", 6)
    except Exception:
        return 6


_FILE_READ_TOOLS = frozenset({"file_read", "file_read_range"})


class EfficiencyMonitorMiddleware(BaseMiddleware):
    """Detects analysis paralysis and enforces browser navigation budgets."""

    def __init__(
        self,
        monitor: ToolEfficiencyMonitor | None = None,
        research_mode: str | None = None,
    ) -> None:
        self._monitor = monitor or ToolEfficiencyMonitor(research_mode=research_mode)
        # Per-step browser navigation counter.  Resets when step_iteration_count
        # drops (indicating a new step started in the plan_act flow).
        self._browser_nav_count = 0
        self._browser_nav_urls: set[str] = set()
        self._browser_nav_signatures: set[str] = set()
        self._duplicate_skip_count = 0
        self._last_step_iteration: int = -1
        # Context-cap escalation: set by BaseAgent when consecutive hard-cap
        # hits reach the threshold.  When True, read calls are blocked
        # to stop the "bathtub problem" (reads add context faster than
        # truncation can remove it).
        # At escalation 3-4: only file_read/file_read_range are blocked.
        # At escalation 5+: ALL read-only tools are blocked (search, browser, etc.)
        self._context_cap_file_read_blocked: bool = False
        self._context_cap_escalation: int = 0

    @property
    def name(self) -> str:
        return "efficiency_monitor"

    def on_step_boundary(self) -> None:
        """Lifecycle hook: reset all per-step state at step boundaries."""
        self.reset_browser_budget()

    def reset_browser_budget(self) -> None:
        """Reset browser navigation budget and efficiency state for a new step."""
        self._browser_nav_count = 0
        self._browser_nav_urls.clear()
        self._browser_nav_signatures.clear()
        self._duplicate_skip_count = 0
        self._last_step_iteration = -1
        # Also reset the efficiency monitor's read/write counters so
        # analysis-paralysis state from a prior step doesn't bleed over.
        self._monitor.reset()

    @staticmethod
    def _browser_signature(tool_call: ToolCallInfo) -> str | None:
        """Normalize duplicate-detection keys for browser/search calls."""
        arguments = tool_call.arguments or {}
        url = str(arguments.get("url", "") or "").strip()
        if url:
            return f"url:{url}"

        if tool_call.function_name == "search":
            query = str(arguments.get("query") or arguments.get("q") or arguments.get("text") or "").strip().lower()
            if query:
                return "query:" + " ".join(query.split())

        return None

    async def before_tool_call(self, ctx: MiddlewareContext, tool_call: ToolCallInfo) -> MiddlewareResult:
        """Enforce browser navigation budget before expensive browser calls."""
        # Detect new step: step_iteration_count resets to 0 when plan_act starts
        # a new step.  If it drops below our last seen value, a new step began.
        if ctx.step_iteration_count < self._last_step_iteration:
            self.reset_browser_budget()
        self._last_step_iteration = ctx.step_iteration_count

        # Block reads when context cap escalation is active.
        # This stops the "bathtub problem" where reads add context faster
        # than graduated truncation can remove it.
        # Escalation 3-4: block file_read only.
        # Escalation 5+: block ALL read-only tools (search, browser, shell_view, etc.)
        if self._context_cap_file_read_blocked:
            from app.domain.models.tool_name import ToolName

            _is_file_read = tool_call.function_name in _FILE_READ_TOOLS
            _is_any_read = self._context_cap_escalation >= 5 and ToolName.is_read_tool(tool_call.function_name)
            if _is_file_read or _is_any_read:
                logger.info(
                    "Context cap escalation (%d): blocking %s to prevent further context growth",
                    self._context_cap_escalation,
                    tool_call.function_name,
                )
                return MiddlewareResult(
                    signal=MiddlewareSignal.SKIP_TOOL,
                    message=(
                        "Context size is critically high. Stop reading files and gathering "
                        "information. Produce your output immediately using the information "
                        "you already have."
                    ),
                )

        if tool_call.function_name not in _BROWSER_NAV_TOOLS:
            return MiddlewareResult.ok()

        # Check for duplicate URL visits (same URL already visited this step)
        url = (tool_call.arguments or {}).get("url", "")
        if url and url in self._browser_nav_urls:
            self._duplicate_skip_count += 1
            self._monitor.record(tool_call.function_name)
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

        signature = self._browser_signature(tool_call)
        if signature and signature in self._browser_nav_signatures:
            self._duplicate_skip_count += 1
            self._monitor.record(tool_call.function_name)
            logger.info("Browser budget: skipping duplicate navigation/search signature: %s", signature[:80])
            duplicate_message = (
                "Already used this search in the current step. Use the results you already gathered instead of "
                "repeating the same query."
                if signature.startswith("query:")
                else "Already visited this target in the current step. Use the content you already have instead "
                "of repeating the same navigation."
            )
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=duplicate_message,
            )

        # Check navigation budget
        if self._browser_nav_count >= _get_browser_nav_budget():
            logger.info(
                "Browser navigation budget exhausted (%d/%d) — blocking %s",
                self._browser_nav_count,
                _get_browser_nav_budget(),
                tool_call.function_name,
            )
            return MiddlewareResult(
                signal=MiddlewareSignal.SKIP_TOOL,
                message=(
                    f"Browser navigation budget reached ({_get_browser_nav_budget()} "
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
            signature = self._browser_signature(tool_call)
            if signature:
                self._browser_nav_signatures.add(signature)
            self._duplicate_skip_count = 0

        return MiddlewareResult.ok()

    async def before_step(self, ctx: MiddlewareContext) -> MiddlewareResult:
        """Check efficiency and inject nudge if imbalanced."""
        # Defensive reset: if step_iteration_count dropped, a new step started
        # but our reset_browser_budget() wasn't called (e.g. caller forgot).
        if ctx.step_iteration_count < self._last_step_iteration:
            self.reset_browser_budget()
            self._last_step_iteration = ctx.step_iteration_count

        # Don't FORCE on the very first iteration of a step — give the LLM
        # at least one full iteration to produce tool calls before blocking.
        if self._duplicate_skip_count >= 3 and ctx.step_iteration_count > 0:
            return MiddlewareResult(
                signal=MiddlewareSignal.FORCE,
                message=(
                    "Repeated duplicate browser/search attempts detected. Stop retrying the same URL or query and "
                    "synthesize what you already have."
                ),
            )

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
