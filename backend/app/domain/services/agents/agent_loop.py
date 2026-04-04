"""Conversation loop helpers extracted from BaseAgent."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

from app.domain.models.event import BaseEvent, ErrorEvent, MessageEvent
from app.domain.models.tool_permission import PermissionTier
from app.domain.services.agents.middleware import MiddlewareContext, MiddlewareSignal
from app.domain.services.agents.tool_dispatcher import ToolDispatcher, ToolDispatchResult

if TYPE_CHECKING:
    from app.domain.services.agents.base import BaseAgent

logger = logging.getLogger(__name__)


class AgentLoop:
    """Owns the ask -> tool dispatch -> ask loop for a single agent turn."""

    def __init__(self, agent: BaseAgent, tool_dispatcher: ToolDispatcher) -> None:
        self._agent = agent
        self._tool_dispatcher = tool_dispatcher

    async def run(self, request: str, format: str | None = None) -> AsyncGenerator[BaseEvent, None]:
        agent = self._agent
        format = format or agent.format

        has_tools = bool(agent.get_available_tools())
        initial_format = None if has_tools else format
        message = await agent.ask(request, initial_format)

        iteration_budget = float(agent.max_iterations)
        iteration_spent = 0.0
        step_iteration_count = 0
        warning_emitted = False
        graceful_completion_requested = False

        agent._compression_cycles_this_step = 0
        agent._compression_guard_active = False
        agent._step_start_time = time.monotonic()
        agent._recent_truncation_count = 0
        agent._stuck_recovery_exhausted = False
        agent._consecutive_cap_hits = 0
        agent._set_context_cap_read_block(blocked=False, escalation=0)
        agent._json_nudge_sent = False

        from app.core.config import get_settings as get_middleware_settings

        mw_ctx = MiddlewareContext(
            agent_id=agent._agent_id,
            session_id=getattr(agent, "_session_id", ""),
            active_tier=getattr(agent, "_active_tier", PermissionTier.DANGER),
            active_phase=agent._active_phase,
            research_depth=getattr(agent, "_research_depth", None),
        )
        mw_ctx.step_start_time = time.monotonic()
        agent._mw_ctx = mw_ctx

        mw_settings = get_middleware_settings()
        mw_depth = getattr(agent, "_research_depth", None)
        if mw_depth == "QUICK":
            mw_ctx.wall_clock_budget = getattr(mw_settings, "step_budget_quick_seconds", 300.0)
        elif mw_depth == "DEEP":
            mw_ctx.wall_clock_budget = getattr(mw_settings, "step_budget_deep_seconds", 900.0)
        elif mw_depth == "STANDARD":
            mw_ctx.wall_clock_budget = getattr(mw_settings, "step_budget_standard_seconds", 600.0)
        else:
            mw_ctx.wall_clock_budget = getattr(mw_settings, "max_step_wall_clock_seconds", 600.0)

        await agent._pipeline.run_before_execution(mw_ctx)
        wall_clock_exceeded = False

        try:
            while iteration_spent < iteration_budget:
                if not message.get("tool_calls"):
                    break

                tool_calls = message["tool_calls"]
                wall_clock_pressure_active: str | None = None

                mw_ctx.elapsed_seconds = time.monotonic() - mw_ctx.step_start_time
                mw_ctx.iteration_count = int(iteration_spent)
                mw_ctx.step_iteration_count = step_iteration_count

                step_result = await agent._pipeline.run_before_step(mw_ctx)
                if step_result.signal == MiddlewareSignal.FORCE:
                    logger.warning("Middleware before_step FORCE: %s", step_result.message)
                    agent._stuck_recovery_exhausted = True
                    break
                if step_result.signal == MiddlewareSignal.INJECT:
                    logger.info("Middleware before_step INJECT: %s", step_result.message)
                    message = await agent.ask_with_messages([{"role": "user", "content": step_result.message}])
                    graceful_completion_requested = True
                    wall_clock_pressure_active = step_result.metadata.get("pressure_level")
                    continue

                for injected_message in mw_ctx.injected_messages:
                    await agent._add_to_memory([injected_message])
                mw_ctx.injected_messages.clear()

                iteration_cost = agent._calculate_iteration_cost(tool_calls)
                iteration_spent += iteration_cost
                step_iteration_count += 1

                if step_iteration_count >= agent.max_step_iterations:
                    logger.warning(
                        "Step iteration budget exhausted (%d/%d). Setting stuck_recovery_exhausted flag.",
                        step_iteration_count,
                        agent.max_step_iterations,
                    )
                    agent._stuck_recovery_exhausted = True
                    break

                if mw_ctx.wall_clock_budget > 0 and mw_ctx.elapsed_seconds > mw_ctx.wall_clock_budget:
                    logger.warning(
                        "Step wall-clock limit exceeded (%.0fs > %.0fs). Force-advancing.",
                        mw_ctx.elapsed_seconds,
                        mw_ctx.wall_clock_budget,
                    )
                    wall_clock_exceeded = True
                    agent._stuck_recovery_exhausted = True
                    break

                remaining_budget = iteration_budget - iteration_spent
                budget_ratio = iteration_spent / iteration_budget

                if budget_ratio >= agent.iteration_warning_threshold and not warning_emitted:
                    logger.warning(
                        "Approaching iteration limit: %.1f/%.1f (%.0f%% used)",
                        iteration_spent,
                        iteration_budget,
                        budget_ratio * 100,
                    )
                    warning_emitted = True

                if remaining_budget < 10 and not graceful_completion_requested:
                    logger.warning(
                        "Low iteration budget (%.1f remaining), requesting completion on next cycle",
                        remaining_budget,
                    )
                    graceful_completion_requested = True

                if wall_clock_pressure_active:
                    tool_calls = [
                        tc
                        for tc in tool_calls
                        if not agent._should_block_tool_at_pressure_level(
                            tc.get("function", {}).get("name", ""),
                            wall_clock_pressure_active,
                        )
                    ]

                dispatch_result = ToolDispatchResult()
                async for event in self._tool_dispatcher.dispatch(
                    tool_calls=tool_calls,
                    mw_ctx=mw_ctx,
                    outcome=dispatch_result,
                ):
                    yield event

                if dispatch_result.awaiting_confirmation:
                    return

                if mw_ctx.metadata.get("wall_clock_advisory_sent") and agent._step_start_time is not None:
                    now = time.monotonic()
                    elapsed = now - agent._step_start_time
                    tag = f"\n[Step time: {elapsed:.0f}s/{mw_ctx.wall_clock_budget:.0f}s]"
                    for tool_response in dispatch_result.tool_responses:
                        if tool_response.get("role") == "tool" and isinstance(tool_response.get("content"), str):
                            tool_response["content"] += tag

                if graceful_completion_requested:
                    dispatch_result.tool_responses.append(
                        {
                            "role": "system",
                            "content": (
                                "[SYSTEM: Approaching execution limit. Please complete the current task "
                                "and provide a summary of your findings. If the task is not complete, "
                                "summarize what was accomplished and what remains to be done.]"
                            ),
                        }
                    )
                    graceful_completion_requested = False

                if (
                    step_iteration_count >= getattr(agent, "_skill_enforcement_nudge_after", 3)
                    and getattr(agent, "_force_skill_invoke_first_turn", False)
                    and not getattr(agent, "_skill_invoked_this_step", False)
                    and not getattr(agent, "_skill_enforcement_nudge_sent", False)
                ):
                    try:
                        from app.core.config import get_settings as get_skill_settings
                        from app.domain.services.agents.execution import SKILL_ENFORCEMENT_NUDGE

                        skill_settings = get_skill_settings()
                        if getattr(skill_settings, "skill_enforcement_nudge_enabled", True):
                            dispatch_result.tool_responses.append({"role": "user", "content": SKILL_ENFORCEMENT_NUDGE})
                            agent._skill_enforcement_nudge_sent = True
                            agent.tool_choice = None
                            agent._force_skill_invoke_first_turn = False
                            logger.debug(
                                "Skill enforcement: nudge injected after %d iterations",
                                step_iteration_count,
                            )
                    except Exception:
                        logger.debug("Skill enforcement: nudge injection failed", exc_info=True)

                message = await agent.ask_with_messages(dispatch_result.tool_responses)
            else:
                logger.error(
                    "Iteration budget exhausted: %.1f/%.1f after processing tool calls",
                    iteration_spent,
                    iteration_budget,
                )
                yield ErrorEvent(
                    error=(
                        f"Task execution limit reached ({int(iteration_spent)} iterations). "
                        "The task was too complex to complete in a single run. "
                        "Consider breaking it into smaller sub-tasks or increasing the iteration limit."
                    ),
                    error_type="iteration_limit",
                    recoverable=True,
                    retry_hint="Try breaking your request into smaller, focused tasks.",
                )
        except Exception as exc:
            if hasattr(agent, "_mw_ctx") and agent._mw_ctx is not None:
                err_result = await agent._pipeline.run_on_error(agent._mw_ctx, exc)
                if err_result.signal == MiddlewareSignal.ABORT:
                    raise
                if not err_result.message:
                    raise
                logger.exception(
                    "Agent execution error handled by middleware (%s): %s",
                    err_result.signal,
                    err_result.message,
                )
            else:
                raise
        finally:
            if hasattr(agent, "_mw_ctx") and agent._mw_ctx is not None:
                await agent._pipeline.run_after_execution(agent._mw_ctx)
                agent._mw_ctx = None

        final_text = (message.get("content") or "").strip()
        if has_tools and format == "json_object":
            is_valid_json = False
            if final_text:
                try:
                    json.loads(final_text)
                    is_valid_json = True
                except (ValueError, TypeError):
                    pass

            if not is_valid_json and final_text and len(final_text) > 10:
                stripped = final_text.lstrip()
                if stripped.startswith("{") or stripped.startswith("["):
                    try:
                        parsed = json.loads(final_text)
                        if isinstance(parsed, dict):
                            logger.info("Post-tool response was already valid JSON (%d chars)", len(final_text))
                            is_valid_json = True
                    except (ValueError, TypeError):
                        pass

                if not is_valid_json:
                    embedded_json = (
                        agent._extract_embedded_json(final_text) if hasattr(agent, "_extract_embedded_json") else None
                    )
                    if embedded_json is not None:
                        logger.info(
                            "Extracted embedded JSON from %d-char mixed prose response",
                            len(final_text),
                        )
                        message["content"] = embedded_json
                        is_valid_json = True
                    else:
                        logger.info(
                            "Wrapping %d-char prose response as JSON (skipping re-enforcement LLM call)",
                            len(final_text),
                        )
                        salvage_summary = final_text[:500].split("\n")[0].strip()
                        final_text = json.dumps({"success": True, "result": salvage_summary, "attachments": []})
                        message["content"] = final_text
                        is_valid_json = True

            if not is_valid_json:
                logger.info("Re-enforcing JSON format on post-tool-loop response")
                message = await agent.ask_with_messages(
                    [
                        {
                            "role": "user",
                            "content": (
                                "Respond with ONLY a valid JSON object. "
                                'Example: {"success": true, "result": "brief summary", "attachments": []}. '
                                "No prose, no markdown fencing, no explanation."
                            ),
                        }
                    ],
                    format="json_object",
                )

        final_content = (message.get("content") or "").strip() or None
        if not final_content and not wall_clock_exceeded:
            logger.info("Attempting summarization recovery for empty final message")
            await agent._ensure_memory()
            for memory_message in agent.memory.messages:
                if memory_message.get("role") == "tool":
                    content = memory_message.get("content", "")
                    if isinstance(content, str) and len(content) > 300:
                        memory_message["content"] = content[:300] + "\n[... truncated for recovery ...]"
            recovery_message = await agent.ask_with_messages(
                [
                    {
                        "role": "user",
                        "content": (
                            "Respond with ONLY a JSON object summarizing what you accomplished. "
                            'Example: {"success": true, "result": "summary here", "attachments": []}. '
                            "No other text."
                        ),
                    }
                ],
                format="json_object",
            )
            recovery_content = (recovery_message.get("content") or "").strip()
            if recovery_content and len(recovery_content) > 10:
                try:
                    json.loads(recovery_content)
                    logger.info("Summarization recovery succeeded (%d chars)", len(recovery_content))
                    final_content = recovery_content
                except (ValueError, TypeError):
                    logger.info("Wrapping %d-char recovery prose as JSON", len(recovery_content))
                    final_content = json.dumps({"success": True, "result": recovery_content[:500], "attachments": []})

        if not final_content:
            stripped = (final_text or "").lstrip()
            if final_text and len(final_text) > 20:
                if stripped.startswith("{") or stripped.startswith("["):
                    try:
                        parsed = json.loads(final_text)
                        if isinstance(parsed, dict):
                            result = parsed.get("result") or parsed.get("summary") or parsed.get("content")
                            if result and isinstance(result, str) and len(result) > 10:
                                logger.info("Salvaging %d-char JSON response via result extraction", len(final_text))
                                final_content = final_text
                    except (ValueError, TypeError):
                        pass
                else:
                    logger.info(
                        "Salvaging %d-char prose response as step result (LLM wrote content instead of JSON)",
                        len(final_text),
                    )
                    salvage_summary = final_text[:300].split("\n")[0].strip()
                    final_content = json.dumps(
                        {
                            "success": True,
                            "result": salvage_summary,
                            "attachments": [],
                        }
                    )

            if not final_content and not wall_clock_exceeded:
                logger.info("Attempting summarization recovery for empty final message")
                recovery_message = await agent.ask_with_messages(
                    [
                        {
                            "role": "user",
                            "content": (
                                "You completed tool calls but did not provide a text response. "
                                "Respond with ONLY a JSON object: "
                                '{"success": true, "result": "<brief summary of what you accomplished>", "attachments": []}. '
                                "No markdown, no extra text."
                            ),
                        }
                    ],
                    format="json_object",
                )
                recovery_content = (recovery_message.get("content") or "").strip()
                if recovery_content and len(recovery_content) > 10:
                    try:
                        json.loads(recovery_content)
                        logger.info(
                            "Summarization recovery succeeded as JSON (%d chars)",
                            len(recovery_content),
                        )
                        final_content = recovery_content
                    except (ValueError, TypeError):
                        logger.info("Wrapping %d-char recovery prose as JSON", len(recovery_content))
                        final_content = json.dumps(
                            {
                                "success": True,
                                "result": recovery_content[:500],
                                "attachments": [],
                            }
                        )

                if not final_content:
                    logger.warning("Agent produced empty final message — yielding fallback")
                    fallback_error = (
                        "Step time limit exceeded. No result produced."
                        if wall_clock_exceeded
                        else "I was unable to produce a complete response. Please try again or rephrase your request."
                    )
                    final_content = json.dumps(
                        {
                            "success": False,
                            "result": None,
                            "attachments": [],
                            "error": fallback_error,
                        }
                    )

        yield MessageEvent(message=final_content)
        await agent.cleanup_background_tasks()
