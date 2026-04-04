"""Tool dispatch helpers extracted from BaseAgent."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from app.domain.exceptions.base import ToolNotFoundException
from app.domain.models.event import BaseEvent, ToolStatus, ToolStreamEvent, WaitEvent
from app.domain.models.tool_result import ToolResult
from app.domain.services.agents.middleware import MiddlewareContext, MiddlewareSignal, ToolCallInfo
from app.domain.services.agents.tool_stream_parser import (
    content_type_for_function,
    extract_partial_content,
    is_streamable_function,
)

if TYPE_CHECKING:
    from app.domain.services.agents.base import BaseAgent

logger = logging.getLogger(__name__)

MAX_CONCURRENT_TOOLS = 5


@dataclass
class ToolDispatchResult:
    """Mutable dispatch state shared between the dispatcher and loop."""

    tool_responses: list[dict[str, Any]] = field(default_factory=list)
    awaiting_confirmation: bool = False


class ToolDispatcher:
    """Owns tool preparation and dispatch for a single agent turn."""

    def __init__(self, agent: BaseAgent) -> None:
        self._agent = agent

    def _append_tool_response(self, outcome: ToolDispatchResult, function_name: str, tool_call_id: str, result) -> None:
        outcome.tool_responses.append(
            {
                "role": "tool",
                "function_name": function_name,
                "tool_call_id": tool_call_id,
                "content": self._agent._serialize_tool_result_for_memory(result, function_name=function_name),
            }
        )

    async def dispatch(
        self,
        *,
        tool_calls: list[dict[str, Any]],
        mw_ctx: MiddlewareContext,
        outcome: ToolDispatchResult,
    ) -> AsyncGenerator[BaseEvent, None]:
        if self._agent._can_parallelize_tools(tool_calls):
            async for event in self._dispatch_parallel(tool_calls=tool_calls, mw_ctx=mw_ctx, outcome=outcome):
                yield event
            return

        async for event in self._dispatch_sequential(tool_calls=tool_calls, mw_ctx=mw_ctx, outcome=outcome):
            yield event

    async def _dispatch_parallel(
        self,
        *,
        tool_calls: list[dict[str, Any]],
        mw_ctx: MiddlewareContext,
        outcome: ToolDispatchResult,
    ) -> AsyncGenerator[BaseEvent, None]:
        agent = self._agent
        parsed_calls = []

        for tool_call in tool_calls[:MAX_CONCURRENT_TOOLS]:
            if not tool_call.get("function"):
                continue

            function_name = tool_call["function"]["name"]
            tool_call_id = tool_call.get("id") or str(uuid.uuid4())
            raw_function_args = tool_call["function"].get("arguments", "{}")
            try:
                function_args = agent._parse_tool_arguments(raw_function_args, function_name=function_name)
            except ValueError as parse_error:
                agent._recent_truncation_count += 1
                parse_result = agent._invalid_tool_args_result(
                    function_name=function_name,
                    raw_arguments=raw_function_args,
                    error=parse_error,
                )
                tool_name = function_name or "unknown_tool"
                with contextlib.suppress(Exception):
                    tool_name = agent.get_tool(function_name).name
                yield agent._create_tool_event(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    function_name=function_name,
                    function_args={},
                    status=ToolStatus.CALLED,
                    function_result=parse_result,
                )
                self._append_tool_response(outcome, function_name, tool_call_id, parse_result)
                continue

            try:
                tool = agent.get_tool(function_name)
            except ToolNotFoundException as tnf:
                logger.warning("Tool not found: %s — returning error result", function_name)
                not_found_result = ToolResult(success=False, message=str(tnf))
                yield agent._create_tool_event(
                    tool_call_id=tool_call_id,
                    tool_name=function_name,
                    function_name=function_name,
                    function_args=function_args,
                    status=ToolStatus.CALLED,
                    function_result=not_found_result,
                )
                self._append_tool_response(outcome, function_name, tool_call_id, not_found_result)
                continue

            tc_info = ToolCallInfo(call_id=tool_call_id, function_name=function_name, arguments=function_args)
            tc_result = await agent._pipeline.run_before_tool_call(mw_ctx, tc_info)
            if tc_result.signal == MiddlewareSignal.SKIP_TOOL:
                logger.info("Middleware before_tool_call SKIP: %s — %s", function_name, tc_result.message)
                skip_result = ToolResult(
                    success=False,
                    message=tc_result.message or f"Tool {function_name} skipped by middleware",
                )
                yield agent._create_tool_event(
                    tool_call_id=tool_call_id,
                    tool_name=tool.name,
                    function_name=function_name,
                    function_args=function_args,
                    status=ToolStatus.CALLED,
                    function_result=skip_result,
                )
                self._append_tool_response(outcome, function_name, tool_call_id, skip_result)
                continue

            security_assessment = agent._security_assessor.assess_action(function_name, function_args)
            confirmation_state = "awaiting_confirmation" if security_assessment.requires_confirmation else None
            if security_assessment.requires_confirmation:
                yield agent._create_tool_event(
                    tool_call_id=tool_call_id,
                    tool_name=tool.name,
                    function_name=function_name,
                    function_args=function_args,
                    status=ToolStatus.CALLING,
                    security_risk=security_assessment.risk_level.value,
                    security_reason=security_assessment.reason,
                    security_suggestions=security_assessment.suggestions,
                    confirmation_state=confirmation_state,
                )
                yield WaitEvent(wait_reason="user_input", suggest_user_takeover="none")
                outcome.awaiting_confirmation = True
                return

            await agent._cancel_token.check_cancelled()

            raw_args = tool_call["function"].get("arguments", "{}")
            if is_streamable_function(function_name):
                partial = extract_partial_content(function_name, raw_args)
                if partial:
                    yield ToolStreamEvent(
                        tool_call_id=tool_call_id,
                        tool_name=tool.name,
                        function_name=function_name,
                        partial_content=partial,
                        content_type=content_type_for_function(function_name),
                        is_final=True,
                    )

            yield agent._create_tool_event(
                tool_call_id=tool_call_id,
                tool_name=tool.name,
                function_name=function_name,
                function_args=function_args,
                status=ToolStatus.CALLING,
                security_risk=security_assessment.risk_level.value,
                security_reason=security_assessment.reason,
                security_suggestions=security_assessment.suggestions,
                confirmation_state=confirmation_state,
            )
            agent._turn_tools_called.append(function_name)
            parsed_calls.append(
                (
                    tool_call,
                    tool_call_id,
                    function_args,
                    tool,
                    security_assessment,
                    confirmation_state,
                )
            )

        semaphore = asyncio.Semaphore(MAX_CONCURRENT_TOOLS)
        tasks = []
        for tool_call, tool_call_id, function_args, tool, _, _ in parsed_calls:
            function_name = tool_call["function"]["name"]
            tasks.append(agent._execute_parallel_tool(semaphore, tool, function_name, function_args, tool_call_id))

        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, (asyncio.CancelledError, KeyboardInterrupt)):
                raise result

        if len(parsed_calls) != len(results):
            logger.error(
                "Parallel execution result count mismatch: %d calls vs %d results",
                len(parsed_calls),
                len(results),
            )

        for (tool_call, tool_call_id, function_args, tool, security_assessment, confirmation_state), result in zip(
            parsed_calls,
            results,
            strict=True,
        ):
            function_name = tool_call["function"]["name"]
            if isinstance(result, Exception):
                result = ToolResult(success=False, message=str(result))

            tc_info = ToolCallInfo(call_id=tool_call_id, function_name=function_name, arguments=function_args)
            await agent._pipeline.run_after_tool_call(mw_ctx, tc_info, result)

            yield agent._create_tool_event(
                tool_call_id=tool_call_id,
                tool_name=tool.name,
                function_name=function_name,
                function_args=function_args,
                status=ToolStatus.CALLED,
                function_result=result,
                security_risk=security_assessment.risk_level.value,
                security_reason=security_assessment.reason,
                security_suggestions=security_assessment.suggestions,
                confirmation_state=confirmation_state,
            )
            self._append_tool_response(outcome, function_name, tool_call_id, result)

    async def _dispatch_sequential(
        self,
        *,
        tool_calls: list[dict[str, Any]],
        mw_ctx: MiddlewareContext,
        outcome: ToolDispatchResult,
    ) -> AsyncGenerator[BaseEvent, None]:
        agent = self._agent

        for tool_call in tool_calls:
            if not tool_call.get("function"):
                continue

            function_name = tool_call["function"]["name"]
            tool_call_id = tool_call.get("id") or str(uuid.uuid4())
            raw_function_args = tool_call["function"].get("arguments", "{}")
            try:
                function_args = agent._parse_tool_arguments(raw_function_args, function_name=function_name)
            except ValueError as parse_error:
                agent._recent_truncation_count += 1
                parse_result = agent._invalid_tool_args_result(
                    function_name=function_name,
                    raw_arguments=raw_function_args,
                    error=parse_error,
                )
                tool_name = function_name or "unknown_tool"
                with contextlib.suppress(Exception):
                    tool_name = agent.get_tool(function_name).name
                yield agent._create_tool_event(
                    tool_call_id=tool_call_id,
                    tool_name=tool_name,
                    function_name=function_name,
                    function_args={},
                    status=ToolStatus.CALLED,
                    function_result=parse_result,
                )
                self._append_tool_response(outcome, function_name, tool_call_id, parse_result)
                continue

            try:
                tool = agent.get_tool(function_name)
            except ToolNotFoundException as tnf:
                logger.warning("Tool not found: %s — returning error result", function_name)
                not_found_result = ToolResult(success=False, message=str(tnf))
                yield agent._create_tool_event(
                    tool_call_id=tool_call_id,
                    tool_name=function_name,
                    function_name=function_name,
                    function_args=function_args,
                    status=ToolStatus.CALLED,
                    function_result=not_found_result,
                )
                self._append_tool_response(outcome, function_name, tool_call_id, not_found_result)
                continue

            tc_info = ToolCallInfo(call_id=tool_call_id, function_name=function_name, arguments=function_args)
            tc_result = await agent._pipeline.run_before_tool_call(mw_ctx, tc_info)
            if tc_result.signal == MiddlewareSignal.SKIP_TOOL:
                logger.info("Middleware before_tool_call SKIP: %s — %s", function_name, tc_result.message)
                skip_result = ToolResult(
                    success=False,
                    message=tc_result.message or f"Tool {function_name} skipped by middleware",
                )
                yield agent._create_tool_event(
                    tool_call_id=tool_call_id,
                    tool_name=tool.name,
                    function_name=function_name,
                    function_args=function_args,
                    status=ToolStatus.CALLED,
                    function_result=skip_result,
                )
                self._append_tool_response(outcome, function_name, tool_call_id, skip_result)
                continue

            security_assessment = agent._security_assessor.assess_action(function_name, function_args)
            confirmation_state = "awaiting_confirmation" if security_assessment.requires_confirmation else None
            if security_assessment.requires_confirmation:
                yield agent._create_tool_event(
                    tool_call_id=tool_call_id,
                    tool_name=tool.name,
                    function_name=function_name,
                    function_args=function_args,
                    status=ToolStatus.CALLING,
                    security_risk=security_assessment.risk_level.value,
                    security_reason=security_assessment.reason,
                    security_suggestions=security_assessment.suggestions,
                    confirmation_state=confirmation_state,
                )
                yield WaitEvent(wait_reason="user_input", suggest_user_takeover="none")
                outcome.awaiting_confirmation = True
                return

            await agent._cancel_token.check_cancelled()

            raw_args_seq = tool_call["function"].get("arguments", "{}")
            if is_streamable_function(function_name):
                partial = extract_partial_content(function_name, raw_args_seq)
                if partial:
                    yield ToolStreamEvent(
                        tool_call_id=tool_call_id,
                        tool_name=tool.name,
                        function_name=function_name,
                        partial_content=partial,
                        content_type=content_type_for_function(function_name),
                        is_final=True,
                    )

            yield agent._create_tool_event(
                tool_call_id=tool_call_id,
                tool_name=tool.name,
                function_name=function_name,
                function_args=function_args,
                status=ToolStatus.CALLING,
                security_risk=security_assessment.risk_level.value,
                security_reason=security_assessment.reason,
                security_suggestions=security_assessment.suggestions,
                confirmation_state=confirmation_state,
            )
            agent._turn_tools_called.append(function_name)

            await agent._cancel_token.check_cancelled()

            flags = agent._resolve_feature_flags()
            if flags.get("live_shell_streaming") and function_name == "shell_exec" and hasattr(tool, "sandbox"):
                from app.domain.services.tools.shell_output_poller import ShellOutputPoller

                session_id = function_args.get("id", "")
                poll_interval = flags.get("live_shell_poll_interval_ms", 500)
                max_polls = flags.get("live_shell_max_polls", 600)
                poller = ShellOutputPoller(
                    sandbox=tool.sandbox,
                    session_id=session_id,
                    tool_call_id=tool_call_id,
                    tool_name=tool.name,
                    function_name=function_name,
                    poll_interval_ms=int(poll_interval) if poll_interval else 500,
                    max_polls=int(max_polls) if max_polls else 600,
                )
                poll_task = asyncio.create_task(poller.start_polling())
                exec_task = asyncio.create_task(agent.invoke_tool(tool, function_name, function_args))
                try:
                    while not exec_task.done():
                        await asyncio.sleep(0.3)
                        async for ev in poller.drain_events():
                            yield ev
                    result = exec_task.result()
                finally:
                    poller.stop()
                    if not poll_task.done():
                        await poll_task
                    async for ev in poller.drain_events():
                        yield ev
            elif getattr(tool, "supports_progress", False) and hasattr(tool, "drain_progress_events"):
                tool._active_tool_call_id = tool_call_id
                tool._active_function_name = function_name
                exec_task = asyncio.create_task(agent.invoke_tool(tool, function_name, function_args))
                try:
                    while not exec_task.done():
                        await asyncio.sleep(0.3)
                        async for ev in tool.drain_progress_events():
                            yield ev
                    result = exec_task.result()
                finally:
                    async for ev in tool.drain_progress_events():
                        yield ev
            else:
                result = await agent.invoke_tool(tool, function_name, function_args)

            await agent._pipeline.run_after_tool_call(mw_ctx, tc_info, result)

            yield agent._create_tool_event(
                tool_call_id=tool_call_id,
                tool_name=tool.name,
                function_name=function_name,
                function_args=function_args,
                status=ToolStatus.CALLED,
                function_result=result,
                security_risk=security_assessment.risk_level.value,
                security_reason=security_assessment.reason,
                security_suggestions=security_assessment.suggestions,
                confirmation_state=confirmation_state,
            )
            self._append_tool_response(outcome, function_name, tool_call_id, result)
