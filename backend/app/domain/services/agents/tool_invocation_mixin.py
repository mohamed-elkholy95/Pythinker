"""Tool invocation and serialization mixin for BaseAgent.

Extracted from base.py to keep BaseAgent focused on orchestration.
All methods use ``self`` naturally via Python MRO — no interface changes.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
import uuid
from typing import Any, ClassVar

from app.domain.models.event import (
    CouponItem,
    DealItem,
    DealToolContent,
    SearchToolContent,
    ToolEvent,
    ToolStatus,
)
from app.domain.models.search import SearchResultItem
from app.domain.models.tool_call import ToolCallEnvelope
from app.domain.models.tool_name import ToolName
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.security_assessor import ActionSecurityRisk
from app.domain.services.tools.base import BaseTool
from app.domain.services.tools.command_formatter import CommandFormatter
from app.domain.services.tools.dynamic_toolset import get_toolset_manager
from app.domain.services.tools.tool_profiler import get_tool_profiler
from app.domain.services.tools.tool_tracing import get_tool_tracer

logger = logging.getLogger(__name__)

# ── Tool timeout configuration ────────────────────────────────────────────────

_LONG_TIMEOUT_TOOLS: frozenset[str] = frozenset(
    {
        "wide_research",
        "info_search_web",
        "deal_scraper_search",
        "deal_scraper_compare",
        "deal_scraper_recommend",
    }
)
_DEFAULT_TOOL_TIMEOUT: float = 120.0
_LONG_TOOL_TIMEOUT: float = 300.0


def _resolve_tool_timeout(function_name: str) -> float:
    """Return timeout in seconds based on tool type."""
    if function_name.startswith("browser_"):
        return _LONG_TOOL_TIMEOUT
    if function_name in _LONG_TIMEOUT_TOOLS:
        return _LONG_TOOL_TIMEOUT
    return _DEFAULT_TOOL_TIMEOUT


def _extract_url_from_args(arguments: dict) -> str | None:
    """Extract URL from tool call arguments.

    Checks common URL parameter names used across tools.
    """
    for key in ("url", "target_url", "page_url", "query"):
        val = arguments.get(key)
        if val and isinstance(val, str) and val.startswith(("http://", "https://")):
            return val
    return None


def _extract_search_result_urls(result: ToolResult | None) -> list[str]:
    """Extract URL candidates from common search tool payload shapes."""
    if result is None or result.data is None:
        return []

    data = result.data
    if hasattr(data, "model_dump"):
        with contextlib.suppress(Exception):
            data = data.model_dump()

    raw_results: Any = None
    if isinstance(data, dict):
        raw_results = data.get("results")
    else:
        with contextlib.suppress(AttributeError):
            raw_results = data.results

    if not isinstance(raw_results, list):
        return []

    urls: list[str] = []
    seen: set[str] = set()
    for item in raw_results:
        candidate: str | None = None
        if isinstance(item, dict):
            value = item.get("link") or item.get("url")
            if isinstance(value, str):
                candidate = value
        else:
            value = getattr(item, "link", None) or getattr(item, "url", None)
            if isinstance(value, str):
                candidate = value

        if candidate and candidate.startswith(("http://", "https://")) and candidate not in seen:
            seen.add(candidate)
            urls.append(candidate)

    return urls


# ── Mixin class ───────────────────────────────────────────────────────────────


class ToolInvocationMixin:
    """Mixin providing tool invocation and result serialization for BaseAgent."""

    # Tool result compaction limits for memory writes.
    _TOOL_RESULT_MEMORY_MAX_CHARS: ClassVar[int] = 4000
    _TOOL_RESULT_MESSAGE_PREVIEW_CHARS: ClassVar[int] = 1000
    _TOOL_RESULT_DATA_PREVIEW_CHARS: ClassVar[int] = 2500
    # Max search results to keep in LLM context (rest is compacted).
    _SEARCH_RESULT_MAX_FOR_LLM: ClassVar[int] = 5

    # ── Tool usage recording ─────────────────────────────────────────────────

    def _record_tool_usage(self, tool_name: str, success: bool, duration_ms: float) -> None:
        """Record tool usage for dynamic toolset prioritization."""
        try:
            manager = get_toolset_manager()
            manager.record_tool_usage(tool_name, success, duration_ms)
        except Exception as e:
            logger.debug(f"Failed to record tool usage for {tool_name}: {e}")

    # ── Tool event creation ──────────────────────────────────────────────────

    def _create_tool_event(
        self,
        tool_call_id: str,
        tool_name: str,
        function_name: str,
        function_args: dict[str, Any],
        status: ToolStatus,
        **kwargs,
    ) -> ToolEvent:
        """Create ToolEvent with command formatting applied."""
        try:
            display_command, command_category, command_summary = CommandFormatter.format_tool_call(
                tool_name=tool_name,
                function_name=function_name,
                function_args=function_args,
            )
        except Exception as e:
            logger.debug(f"Failed to format command: {e}")
            display_command = f"{function_name}(...)"
            command_category = "other"
            command_summary = function_name

        tool_content = kwargs.pop("tool_content", None)
        search_functions = ToolName.search_tools()
        search_panel_max = 20
        if tool_content is None and status == ToolStatus.CALLED and function_name in search_functions:
            function_result = kwargs.get("function_result")
            if (
                function_result
                and hasattr(function_result, "success")
                and function_result.success
                and hasattr(function_result, "data")
                and function_result.data
            ):
                data = function_result.data
                results_list: list[SearchResultItem] = []

                if hasattr(data, "results") and data.results:
                    results_list = [
                        SearchResultItem(
                            title=r.title or "No title",
                            link=r.link or "",
                            snippet=r.snippet or "",
                        )
                        for r in data.results[:search_panel_max]
                    ]
                elif isinstance(data, dict) and data.get("sources"):
                    results_list = [
                        SearchResultItem(
                            title=s.get("title", "No title"),
                            link=s.get("url", s.get("link", "")),
                            snippet=s.get("snippet", ""),
                        )
                        for s in data["sources"][:search_panel_max]
                    ]

                if results_list:
                    tool_content = SearchToolContent(results=results_list)
                    logger.info(f"SearchToolContent created with {len(results_list)} results for {function_name}")

        deal_functions = {"deal_search", "deal_compare_prices", "deal_find_coupons"}
        if tool_content is None and status == ToolStatus.CALLED and function_name in deal_functions:
            function_result = kwargs.get("function_result")
            if (
                function_result
                and hasattr(function_result, "success")
                and function_result.success
                and hasattr(function_result, "data")
                and function_result.data is not None
            ):
                data = function_result.data
                raw_deals = data.get("deals", []) if isinstance(data, dict) else []
                deal_items = [
                    DealItem(
                        store=d.get("store", d.get("store_name", "")),
                        price=d.get("price"),
                        original_price=d.get("original_price"),
                        discount_percent=d.get("discount_percent", d.get("discount", None)),
                        product_name=d.get("title", d.get("product_name", "")),
                        url=d.get("url", d.get("product_url", "")),
                        score=d.get("score"),
                        in_stock=d.get("in_stock"),
                        coupon_code=d.get("coupon_code"),
                        image_url=d.get("image_url"),
                    )
                    for d in raw_deals[:10]
                ]
                raw_coupons = data.get("coupons", []) if isinstance(data, dict) else []
                coupon_items = [
                    CouponItem(
                        code=c.get("code", ""),
                        description=c.get("description", ""),
                        store=c.get("store_name", c.get("store", "")),
                        expiry=c.get("expiry_date", c.get("expiry")),
                        verified=bool(c.get("verified", False)),
                        source=c.get("source", ""),
                    )
                    for c in raw_coupons[:10]
                ]
                best_idx: int | None = None
                if deal_items:
                    scored = [(i, d.score or 0) for i, d in enumerate(deal_items)]
                    best_idx = max(scored, key=lambda x: x[1])[0] if any(s > 0 for _, s in scored) else 0
                query_str = function_args.get("query", function_args.get("product", ""))
                searched_stores: list[str] = data.get("searched_stores", []) if isinstance(data, dict) else []
                store_errors: list[dict[str, str]] = data.get("store_errors", []) if isinstance(data, dict) else []
                empty_reason = data.get("empty_reason") if isinstance(data, dict) else None
                stores_attempted = data.get("stores_attempted") if isinstance(data, dict) else None
                stores_with_results = data.get("stores_with_results") if isinstance(data, dict) else None
                tool_content = DealToolContent(
                    deals=deal_items,
                    coupons=coupon_items,
                    query=query_str,
                    best_deal_index=best_idx,
                    searched_stores=searched_stores,
                    store_errors=store_errors,
                    empty_reason=empty_reason if isinstance(empty_reason, str) else None,
                    stores_attempted=stores_attempted if isinstance(stores_attempted, int) else None,
                    stores_with_results=stores_with_results if isinstance(stores_with_results, int) else None,
                )
                logger.info(
                    f"DealToolContent created with {len(deal_items)} deals, "
                    f"{len(coupon_items)} coupons, {len(searched_stores)} stores for {function_name}"
                )

        final_args = function_args
        if status == ToolStatus.CALLED:
            function_result = kwargs.get("function_result")
            if (
                function_result
                and hasattr(function_result, "data")
                and isinstance(function_result.data, dict)
                and {"resolved_x", "resolved_y"}.issubset(function_result.data)
            ):
                final_args = {
                    **function_args,
                    "coordinate_x": function_result.data["resolved_x"],
                    "coordinate_y": function_result.data["resolved_y"],
                }

        return ToolEvent(
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            function_name=function_name,
            function_args=final_args,
            status=status,
            display_command=display_command,
            command_category=command_category,
            command_summary=command_summary,
            tool_content=tool_content,
            **kwargs,
        )

    # ── Core tool invocation ─────────────────────────────────────────────────

    async def invoke_tool(
        self,
        tool: BaseTool,
        function_name: str,
        arguments: dict[str, Any],
        skip_security: bool = False,
    ) -> ToolResult:
        """Invoke specified tool, with retry mechanism and exponential backoff."""
        # REL-009: Check sandbox health before tool execution.
        session_id = getattr(self, "_session_id", None)
        if session_id and hasattr(tool, "sandbox"):
            try:
                from app.core.sandbox_manager import SandboxState, get_sandbox_manager

                manager = get_sandbox_manager()
                managed = manager._sandboxes.get(session_id)
                if managed and managed.state == SandboxState.FAILED:
                    from app.domain.exceptions.base import SandboxCrashError

                    raise SandboxCrashError(
                        f"Sandbox for session {session_id} is in FAILED state — cannot execute tool '{function_name}'"
                    )
            except ImportError:
                pass

        profiler = get_tool_profiler()
        tool_tracer = None
        flags = self._resolve_feature_flags()
        if flags.get("tool_tracing"):
            tool_tracer = get_tool_tracer()
        start_time = time.perf_counter()

        tool_call_id = str(uuid.uuid4())
        envelope = ToolCallEnvelope(
            tool_call_id=tool_call_id,
            tool_name=tool.name,
            function_name=function_name,
            arguments=arguments,
        )

        log_start = self._log.tool_started(function_name, tool_call_id, arguments)

        validation_result = self._hallucination_detector.validate_tool_call(
            tool_name=function_name,
            parameters=arguments,
        )

        self._total_tool_calls += 1

        if not validation_result.is_valid:
            logger.warning(
                f"Tool hallucination detected: {validation_result.error_message}",
                extra={
                    "function_name": function_name,
                    "error_type": validation_result.error_type,
                    "suggestions": validation_result.suggestions,
                    "session_id": getattr(self, "_session_id", None),
                    "agent_id": getattr(self, "_agent_id", None),
                },
            )
            correction_message = validation_result.error_message or "Tool validation failed"
            if validation_result.suggestions:
                correction_message += f" Suggestions: {', '.join(validation_result.suggestions)}"

            self._total_hallucinations += 1

            try:
                from app.core.config import get_settings

                _settings = get_settings()
                if (
                    getattr(_settings, "feature_hallucination_escalation_enabled", False)
                    and not self._hallucination_escalated
                    and self._total_tool_calls >= getattr(_settings, "hallucination_escalation_min_samples", 10)
                ):
                    rate = self._total_hallucinations / max(1, self._total_tool_calls)
                    threshold = getattr(_settings, "hallucination_escalation_threshold", 0.15)
                    if rate >= threshold:
                        self._hallucination_escalated = True
                        logger.warning(
                            "Hallucination rate escalation triggered: rate=%.2f "
                            "(threshold=%.2f, calls=%d, hallucinations=%d)",
                            rate,
                            threshold,
                            self._total_tool_calls,
                            self._total_hallucinations,
                        )
            except Exception:
                logger.debug(
                    "Hallucination escalation check failed (non-critical)",
                    exc_info=True,
                )

            return ToolResult(success=False, message=correction_message)

        if not skip_security:
            security_assessment = self._security_assessor.assess_action(function_name, arguments)
            if security_assessment.blocked:
                self._log.security_event("blocked", function_name, security_assessment.reason)
                envelope.mark_blocked(security_assessment.reason)
                return ToolResult(success=False, message=f"Action blocked for security: {security_assessment.reason}")

            if security_assessment.risk_level == ActionSecurityRisk.HIGH:
                self._log.security_event("high_risk", function_name, security_assessment.reason)

        if self._circuit_breaker and not self._circuit_breaker.can_execute(function_name):
            msg = f"Tool '{function_name}' circuit is open — skipping to avoid cascading failures"
            logger.warning(msg)
            envelope.mark_failed(msg)
            return ToolResult(success=False, message=msg)

        retries = 0
        current_interval = self.retry_interval
        last_error = ""
        result: ToolResult | None = None
        envelope.mark_started()

        _trace_ctx_for_tool = getattr(self, "_trace_ctx", None)

        if flags.get("hitl_enabled"):
            try:
                from app.domain.services.flows.hitl_policy import get_hitl_policy

                _hitl_assessment = get_hitl_policy().assess(function_name, arguments)
                if _hitl_assessment.requires_approval:
                    logger.warning(
                        "HITL interrupt: tool=%s risk=%s level=%s — returning requires_approval",
                        function_name,
                        _hitl_assessment.reason,
                        _hitl_assessment.risk_level,
                    )
                    return ToolResult(
                        success=False,
                        message=(
                            f"[HITL] This action requires human approval before execution. "
                            f"Risk: {_hitl_assessment.reason} (level={_hitl_assessment.risk_level}). "
                            "Please confirm or cancel the action."
                        ),
                    )
            except Exception as _hitl_err:
                logger.debug("HITL policy check failed (non-critical): %s", _hitl_err)

        _guard_url: str | None = None
        if self._url_failure_guard is not None:
            _guard_url = _extract_url_from_args(arguments)
            if _guard_url:
                _guard_decision = self._url_failure_guard.check_url(_guard_url)
                try:
                    from app.core.prometheus_metrics import url_guard_actions_total, url_guard_escalations_total

                    url_guard_actions_total.inc({"tier": str(_guard_decision.tier), "action": _guard_decision.action})
                    if _guard_decision.action in ("warn", "block"):
                        url_guard_escalations_total.inc({"tier": str(_guard_decision.tier)})
                except Exception:
                    logger.debug("URL guard metrics emission failed (non-critical)", exc_info=True)
                if _guard_decision.action == "block":
                    logger.warning(
                        "URL guard BLOCKED %s (tier=%d): %s",
                        _guard_url,
                        _guard_decision.tier,
                        _guard_decision.message,
                    )
                    return ToolResult(success=False, message=_guard_decision.message)
                if _guard_decision.action == "warn" and _guard_decision.message:
                    logger.info(
                        "URL guard WARNING for %s (tier=%d)",
                        _guard_url,
                        _guard_decision.tier,
                    )
                    self._efficiency_nudges.append(
                        {
                            "message": _guard_decision.message,
                            "read_count": 0,
                            "action_count": 0,
                            "confidence": 0.90,
                            "hard_stop": False,
                        }
                    )

        while retries <= self.max_retries:
            try:
                await self._cancel_token.check_cancelled()

                if flags.get("tool_tracing") and _trace_ctx_for_tool:
                    with _trace_ctx_for_tool.span(
                        f"tool:{function_name}",
                        "tool_execution",
                        {
                            "tool.name": function_name,
                            "agent.id": getattr(self, "_agent_id", ""),
                            "attempt": retries,
                        },
                    ) as _tool_span:
                        result = await asyncio.wait_for(
                            tool.invoke_function(function_name, **arguments),
                            timeout=_resolve_tool_timeout(function_name),
                        )
                        try:
                            _tool_span.set_attribute("tool.success", result.success)
                            _tool_span.set_attribute("tool.result_size", len(str(result.message or "")))
                        except Exception as _span_err:
                            logger.debug("Tool span attribute set failed (non-critical): %s", _span_err)
                else:
                    result = await asyncio.wait_for(
                        tool.invoke_function(function_name, **arguments),
                        timeout=_resolve_tool_timeout(function_name),
                    )
            except (asyncio.CancelledError, KeyboardInterrupt, SystemExit):
                raise
            except TimeoutError:
                _timeout_used = _resolve_tool_timeout(function_name)
                last_error = f"Tool execution timed out after {_timeout_used:.0f}s"
                self._log.tool_failed(function_name, tool_call_id, last_error, log_start)
                network_tools = {"info_search_web", "browser_get_content", "browser_navigate", "mcp_call_tool"}
                if function_name in network_tools and retries < self.max_retries:
                    retries += 1
                    logger.info(f"Recoverable timeout for {function_name}, retrying ({retries}/{self.max_retries})")
                    await asyncio.sleep(current_interval)
                    current_interval *= self.retry_backoff
                    continue
                envelope.mark_failed(last_error)
                break
            except Exception as e:
                last_error = str(e)
                retries += 1
                if retries <= self.max_retries:
                    await asyncio.sleep(current_interval)
                    current_interval *= self.retry_backoff
                    continue
                self._log.tool_failed(function_name, tool_call_id, last_error, log_start)
                envelope.mark_failed(last_error)
                break

            try:
                duration_ms = (time.perf_counter() - start_time) * 1000
                profiler.record_execution(
                    tool_name=function_name,
                    duration_ms=duration_ms,
                    success=result.success if result else False,
                    error=result.message if result and not result.success else None,
                )

                if tool_tracer:
                    tool_tracer.trace_execution(
                        tool_name=function_name,
                        arguments=arguments,
                        result=result,
                        duration_ms=duration_ms,
                    )

                self._record_tool_usage(
                    function_name, success=result.success if result else False, duration_ms=duration_ms
                )

                result_preview = str(result.message)[:500] if result else ""
                self._stuck_detector.track_tool_action(
                    tool_name=function_name,
                    tool_args=arguments,
                    success=result.success if result else False,
                    result=result_preview,
                    error=result.message if result and not result.success else None,
                )

                try:
                    self._efficiency_monitor.record(function_name)
                    signal = self._efficiency_monitor.check_efficiency()

                    if not signal.is_balanced and signal.nudge_message:
                        logger.info(
                            f"Tool efficiency nudge (hard_stop={signal.hard_stop}): {signal.nudge_message[:80]}... "
                            f"(reads={signal.read_count}, actions={signal.action_count}, "
                            f"confidence={signal.confidence})"
                        )

                        self._metrics.increment(
                            "pythinker_tool_efficiency_nudges_total",
                            labels={
                                "threshold": "hard_stop" if signal.hard_stop else "soft",
                                "read_count": str(signal.read_count),
                                "action_count": str(signal.action_count),
                            },
                        )

                        self._efficiency_nudges.append(
                            {
                                "message": signal.nudge_message,
                                "read_count": signal.read_count,
                                "action_count": signal.action_count,
                                "confidence": signal.confidence,
                                "hard_stop": signal.hard_stop,
                            }
                        )
                except Exception as e:
                    logger.debug(f"Tool efficiency monitoring failed for {function_name}: {e}")

                if self._url_failure_guard and result:
                    try:
                        if result.success and "search" in function_name:
                            discovered_urls = _extract_search_result_urls(result)
                            if discovered_urls:
                                self._url_failure_guard.record_search_results(discovered_urls)
                        if _guard_url and not result.success:
                            self._url_failure_guard.record_failure(
                                _guard_url,
                                result.message[:200] if result.message else "Unknown error",
                                function_name,
                            )
                            _msg_lower = (result.message or "").lower()
                            if (
                                "404" in _msg_lower or "not found" in _msg_lower
                            ) and not self._url_failure_guard.is_url_from_search_results(_guard_url):
                                self._url_failure_guard.record_guessed_url_failure(_guard_url)
                        from app.core.prometheus_metrics import url_guard_tracked_urls

                        metrics = self._url_failure_guard.get_metrics()
                        url_guard_tracked_urls.set(value=float(metrics.get("tracked_urls", 0)))
                    except Exception as _guard_err:
                        logger.debug("URL failure guard post-execution handling failed: %s", _guard_err)

                try:
                    from app.domain.services.agents.task_state_manager import get_task_state_manager

                    task_state_manager = getattr(self, "_task_state_manager", None) or get_task_state_manager()
                    await task_state_manager.record_action(
                        function_name=function_name,
                        success=result.success if result else False,
                        result=result.data
                        if result and result.data is not None
                        else result.message
                        if result
                        else None,
                        error=result.message if result and not result.success else None,
                    )
                except Exception as e:
                    logger.debug(f"Task state recording failed for {function_name}: {e}")

                envelope.mark_completed(
                    success=result.success if result else False,
                    message=result.message if result else None,
                )
                self._log.tool_completed(
                    function_name,
                    tool_call_id,
                    log_start,
                    success=result.success if result else False,
                    message=result.message if result else None,
                )
            except Exception as e:
                logger.warning(f"Post-execution tracking failed for {function_name}: {e}")

            if self._circuit_breaker and result and result.success:
                self._circuit_breaker.record_success(function_name)

            return result

        # Retry loop exhausted — record failure metrics
        if self._circuit_breaker:
            self._circuit_breaker.record_failure(function_name)
        duration_ms = (time.perf_counter() - start_time) * 1000
        profiler.record_execution(
            tool_name=function_name, duration_ms=duration_ms, success=False, error=last_error[:200]
        )

        if tool_tracer:
            tool_tracer.trace_execution(
                tool_name=function_name,
                arguments=arguments,
                result=None,
                duration_ms=duration_ms,
                error=last_error[:200],
            )

        self._stuck_detector.track_tool_action(
            tool_name=function_name,
            tool_args=arguments,
            success=False,
            error=last_error[:200],
        )

        try:
            self._efficiency_monitor.record(function_name)
            signal = self._efficiency_monitor.check_efficiency()

            if not signal.is_balanced and signal.nudge_message:
                logger.info(
                    f"Tool efficiency nudge after failure (hard_stop={signal.hard_stop}): "
                    f"(reads={signal.read_count}, actions={signal.action_count})"
                )
                self._metrics.increment(
                    "pythinker_tool_efficiency_nudges_total",
                    labels={
                        "threshold": "hard_stop" if signal.hard_stop else "soft",
                        "read_count": str(signal.read_count),
                        "action_count": str(signal.action_count),
                    },
                )
                self._efficiency_nudges.append(
                    {
                        "message": signal.nudge_message,
                        "read_count": signal.read_count,
                        "action_count": signal.action_count,
                        "confidence": signal.confidence,
                        "hard_stop": signal.hard_stop,
                    }
                )
        except Exception as e:
            logger.debug(f"Tool efficiency monitoring failed for {function_name}: {e}")

        if self._url_failure_guard and _guard_url:
            try:
                self._url_failure_guard.record_failure(_guard_url, last_error[:200], function_name)
                from app.core.prometheus_metrics import url_guard_tracked_urls

                metrics = self._url_failure_guard.get_metrics()
                url_guard_tracked_urls.set(value=float(metrics.get("tracked_urls", 0)))
            except Exception as _guard_err:
                logger.debug("URL failure guard recording failed (retry exhausted): %s", _guard_err)

        try:
            from app.domain.services.agents.task_state_manager import get_task_state_manager

            task_state_manager = getattr(self, "_task_state_manager", None) or get_task_state_manager()
            await task_state_manager.record_action(
                function_name=function_name,
                success=False,
                result=None,
                error=last_error[:200],
            )
        except Exception as e:
            logger.debug(f"Task state recording failed for {function_name} error path: {e}")

        return ToolResult(success=False, message=last_error)

    # ── Result serialization helpers ─────────────────────────────────────────

    @staticmethod
    def _truncate_text(content: str, max_chars: int) -> str:
        """Truncate text with a compact marker."""
        if len(content) <= max_chars:
            return content
        truncated_chars = len(content) - max_chars
        return f"{content[:max_chars]}\n\n... [truncated {truncated_chars:,} chars]"

    def _tool_data_preview(self, data: Any, max_chars: int) -> str:
        """Create a bounded preview string for tool result data."""
        if hasattr(data, "model_dump"):
            data = data.model_dump()

        if isinstance(data, str):
            return self._truncate_text(data, max_chars)

        try:
            serialized = json.dumps(data, ensure_ascii=False, default=str)
        except Exception:
            serialized = str(data)

        return self._truncate_text(serialized, max_chars)

    @staticmethod
    def _sanitize_search_result_html(result: ToolResult) -> ToolResult:
        """Strip noisy HTML from search result content before serialization."""
        if result is None or result.data is None:
            return result

        html_noise_tags = re.compile(
            r"<(script|style|nav|footer|header|aside|iframe|noscript|svg|form)\b[^>]*>.*?</\1>",
            re.DOTALL | re.IGNORECASE,
        )
        all_tags = re.compile(r"<[^>]+>")

        def _clean_html_content(text: str) -> str:
            if not isinstance(text, str) or len(text) < 2000:
                return text
            if not re.search(r"<(?:script|nav|footer|style|div|span)\b", text, re.IGNORECASE):
                return text
            cleaned = html_noise_tags.sub("", text)
            cleaned = all_tags.sub(" ", cleaned)
            cleaned = re.sub(r"\s+", " ", cleaned).strip()
            if not cleaned or len(cleaned) < 50:
                return "[Page content was primarily HTML markup with no meaningful text]"
            return cleaned

        data = result.data
        modified = False

        if isinstance(data, dict):
            results_list = data.get("results")
            if isinstance(results_list, list):
                new_results = []
                for item in results_list:
                    if isinstance(item, dict):
                        for key in ("snippet", "content", "text", "description"):
                            if key in item and isinstance(item[key], str):
                                cleaned = _clean_html_content(item[key])
                                if cleaned != item[key]:
                                    item = {**item, key: cleaned}
                                    modified = True
                        new_results.append(item)
                    else:
                        new_results.append(item)
                if modified:
                    return ToolResult(
                        success=result.success,
                        message=result.message,
                        data={**data, "results": new_results},
                    )

        if hasattr(data, "results") and not isinstance(data, dict):
            for item in getattr(data, "results", []) or []:
                for key in ("snippet", "content", "text", "description"):
                    val = getattr(item, key, None)
                    if isinstance(val, str):
                        cleaned = _clean_html_content(val)
                        if cleaned != val:
                            try:
                                setattr(item, key, cleaned)
                                modified = True
                            except (AttributeError, TypeError):
                                pass

        if result.message and isinstance(result.message, str) and len(result.message) > 2000:
            cleaned_msg = _clean_html_content(result.message)
            if cleaned_msg != result.message:
                return ToolResult(
                    success=result.success,
                    message=cleaned_msg,
                    data=result.data,
                )

        return result

    def _serialize_tool_result_for_memory(self, result: ToolResult, function_name: str = "") -> str:
        """Serialize tool results with size guardrails to avoid memory bloat."""
        if function_name and ("search" in function_name.lower() or function_name in ToolName._SEARCH):
            result = self._sanitize_search_result_html(result)

        raw = result.model_dump_json() if hasattr(result, "model_dump_json") else str(result)
        if len(raw) <= self._TOOL_RESULT_MEMORY_MAX_CHARS:
            return raw

        if self._tool_result_store and self._tool_result_store.should_offload(raw):
            result_id, preview = self._tool_result_store.store(raw, function_name)
            return ToolResult(
                success=result.success,
                message="Tool output stored externally.",
                data={
                    "_stored_externally": True,
                    "_result_ref": result_id,
                    "_original_size_chars": len(raw),
                    "_preview": preview,
                },
            ).model_dump_json()

        compacted_data: dict[str, Any] = {
            "_compacted": True,
            "_original_size_chars": len(raw),
        }
        if result.data is not None:
            compacted_data["_preview"] = self._tool_data_preview(result.data, self._TOOL_RESULT_DATA_PREVIEW_CHARS)

        compacted = ToolResult(
            success=result.success,
            message=self._truncate_text(
                result.message or "Tool output compacted for memory.",
                self._TOOL_RESULT_MESSAGE_PREVIEW_CHARS,
            ),
            data=compacted_data,
        ).model_dump_json()

        if len(compacted) <= self._TOOL_RESULT_MEMORY_MAX_CHARS:
            return compacted

        return ToolResult(
            success=result.success,
            message=self._truncate_text(
                result.message or "Tool output omitted from memory to control context size.",
                1000,
            ),
            data={
                "_compacted": True,
                "_original_size_chars": len(raw),
            },
        ).model_dump_json()

    def _truncate_args_for_logging(self, arguments: dict[str, Any], max_len: int = 100) -> dict[str, str]:
        """Truncate large argument values for logging to prevent log bloat."""
        truncated = {}
        for key, value in arguments.items():
            str_value = str(value)
            if len(str_value) > max_len:
                truncated[key] = f"{str_value[:max_len]}... (truncated, {len(str_value)} chars total)"
            else:
                truncated[key] = str_value
        return truncated

    def _parse_tool_arguments(self, raw_arguments: Any, *, function_name: str) -> dict[str, Any]:
        """Parse tool-call arguments using strict JSON object semantics."""
        if raw_arguments is None:
            return {}

        if isinstance(raw_arguments, dict):
            return raw_arguments

        if not isinstance(raw_arguments, str):
            raise ValueError(f"expected JSON object string, got {type(raw_arguments).__name__}")

        stripped = raw_arguments.strip()
        if not stripped or stripped.lower() == "null":
            return {}

        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError as exc:
            raise ValueError(f"invalid JSON: {exc.msg}") from exc

        if parsed is None:
            return {}
        if parsed == []:
            return {}
        if not isinstance(parsed, dict):
            raise ValueError(f"expected JSON object for tool '{function_name}', got {type(parsed).__name__}")
        return parsed

    def _tool_requires_arguments(self, function_name: str) -> bool:
        """Return True when the tool schema declares required parameters."""
        for tool_def in self.get_available_tools() or []:
            func = tool_def.get("function", {})
            if func.get("name") != function_name:
                continue
            params = func.get("parameters", {}) or {}
            required = params.get("required", []) or []
            return bool(required)
        return False

    def _invalid_tool_args_result(self, *, function_name: str, raw_arguments: Any, error: ValueError) -> ToolResult:
        """Create a deterministic error result for malformed tool-call arguments."""
        raw_preview = self._truncate_text(str(raw_arguments), 240)
        logger.warning(
            "Skipping malformed tool call '%s': %s (raw_args=%s)",
            function_name,
            error,
            raw_preview,
        )
        return ToolResult.error(
            f"Invalid JSON arguments for tool '{function_name}'. Please resend this tool call with a valid JSON object."
        )

    def _to_tool_call(self, tc: dict) -> Any:
        """Convert an LLM tool_call dict to a ParallelToolExecutor ToolCall."""
        from app.domain.services.agents.parallel_executor import ToolCall as ToolCallParallel

        return ToolCallParallel(
            id=tc.get("id", ""),
            tool_name=tc.get("function", {}).get("name", ""),
            arguments=tc.get("function", {}).get("arguments", {}),
        )
