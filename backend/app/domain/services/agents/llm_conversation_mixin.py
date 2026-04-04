"""LLM conversation and token management mixin for BaseAgent.

Extracted from base.py to keep BaseAgent focused on orchestration.
All methods use ``self`` naturally via Python MRO — no interface changes.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import AsyncGenerator
from typing import Any, ClassVar

from app.domain.models.event import BaseEvent, MessageEvent, StreamEvent
from app.domain.services.agents.error_handler import ErrorType, TokenLimitExceededError
from app.domain.services.agents.tool_dispatcher import MAX_CONCURRENT_TOOLS

logger = logging.getLogger(__name__)


class LlmConversationMixin:
    """LLM conversation loop, token budget enforcement, and context compaction.

    Depends on attributes set by BaseAgent.__init__:
        self.memory, self.llm, self.tool_choice, self._token_manager,
        self._token_budget, self._token_budget_manager, self._efficiency_nudges,
        self._url_failure_guard, self._efficiency_monitor, self._pipeline,
        self._mw_ctx, self._agent_id, self._repository, self._error_handler,
        self._stuck_recovery_exhausted, self._compression_guard_active,
        self._compression_cycles_this_step, self._consecutive_cap_hits,
        self._recent_truncation_count, self._truncation_retry_max_tokens,
        self._step_model_override, self._active_phase, self._scratchpad,
        self._background_tasks, self.max_retries, self.max_consecutive_truncations,
        self.max_compression_cycles_per_step
    """

    # ── ClassVars ────────────────────────────────────────────────────────────

    # Hard character cap for total conversation context.  If all messages
    # combined exceed this, aggressively truncate every tool result to 500 chars.
    # This is the last-resort safety valve against 60-80s LLM calls caused by
    # context window saturation (observed: 78.7s at ~80K chars).
    # Now configurable via settings: hard_context_char_cap / hard_context_char_cap_deep_research
    _HARD_CONTEXT_CHAR_CAP: ClassVar[int] = 50000  # Fallback if settings unavailable

    _TOKEN_BUDGET_FORCE_CONCLUDE_MESSAGE: ClassVar[str] = (
        "TOKEN BUDGET CRITICAL (95%+). You MUST conclude your current step and summarize results now. "
        "Do not start any new exploratory tool calls."
    )
    _TOKEN_BUDGET_HARD_STOP_MESSAGE: ClassVar[str] = (
        "TOKEN BUDGET EMERGENCY (99%+). Tool calls are now disabled. "
        "Provide the best possible final summary from gathered evidence."
    )

    # ── Token budget helpers ──────────────────────────────────────────────────

    def _current_token_usage_ratio(self) -> float:
        """Return current memory token usage ratio against effective limit."""
        if not self.memory:
            return 0.0
        token_count = self._token_manager.count_messages_tokens(self.memory.get_messages())
        effective_limit = max(1, self._token_manager._effective_limit)
        return token_count / effective_limit

    def _resolve_budget_action(self, usage_ratio: float):
        """Resolve token budget action with manager-aware fallback."""
        from app.domain.services.agents.token_budget_manager import BudgetAction

        manager = getattr(self, "_token_budget_manager", None)
        if manager and hasattr(manager, "enforce_budget_policy"):
            return manager.enforce_budget_policy(usage_ratio)

        if usage_ratio >= 0.99:
            return BudgetAction.HARD_STOP_TOOLS
        if usage_ratio >= 0.98:
            return BudgetAction.FORCE_HARD_STOP_NUDGE
        if usage_ratio >= 0.95:
            return BudgetAction.FORCE_CONCLUDE
        if usage_ratio >= 0.90:
            return BudgetAction.REDUCE_VERBOSITY
        return BudgetAction.NORMAL

    async def _inject_budget_notice_if_needed(self, notice: str) -> None:
        """Append a budget notice once to avoid repeated duplicate injections."""
        if not self.memory:
            return
        current_messages = self.memory.get_messages()
        if current_messages:
            last = current_messages[-1]
            if last.get("role") == "user" and last.get("content") == notice:
                return
        await self._add_to_memory([{"role": "user", "content": notice}])

    def _filter_read_tools(self, tools: list[dict[str, Any]] | None) -> list[dict[str, Any]] | None:
        """Drop read-only tools, keeping only action-capable tools."""
        if tools is None:
            return None
        filtered = [
            tool
            for tool in tools
            if not self._efficiency_monitor._is_read_tool(tool.get("function", {}).get("name", ""))
        ]
        return filtered or None

    def _set_context_cap_read_block(self, *, blocked: bool, escalation: int = 0) -> None:
        """Toggle read blocking on the efficiency monitor middleware.

        At escalation 3-4: blocks file_read/file_read_range only.
        At escalation 5+: blocks ALL read-only tools (search, browser, shell_view, etc.)
        to prevent any tool from re-flooding context.
        """
        from app.domain.services.agents.middleware_adapters.efficiency_monitor import (
            EfficiencyMonitorMiddleware,
        )

        for mw in self._pipeline.middleware:
            if isinstance(mw, EfficiencyMonitorMiddleware):
                mw._context_cap_file_read_blocked = blocked
                mw._context_cap_escalation = escalation
                break

    @property
    def _effective_context_char_cap(self) -> int:
        """Return the effective hard context cap, respecting per-flow settings."""
        try:
            from app.core.config import get_settings

            settings = get_settings()
            # If this agent is part of a deep_research flow, use the higher cap
            if getattr(self, "_is_deep_research", False):
                return getattr(settings, "hard_context_char_cap_deep_research", 100_000)
            return getattr(settings, "hard_context_char_cap", 50_000)
        except Exception:
            return self._HARD_CONTEXT_CHAR_CAP

    # ── Main LLM ask loop ────────────────────────────────────────────────────

    async def ask_with_messages(self, messages: list[dict[str, Any]], format: str | None = None) -> dict[str, Any]:
        await self._add_to_memory(messages)

        # Check and handle token limits before making LLM call
        await self._ensure_within_token_limit()

        # Hard safety valve: if total context still exceeds cap after budget
        # management, force-truncate all tool results to prevent 60s+ LLM calls.
        await self._ensure_memory()
        all_msgs = self.memory.get_messages()
        total_chars = sum(len(str(m.get("content", ""))) for m in all_msgs)
        _cap = self._effective_context_char_cap
        if total_chars > _cap:
            self._consecutive_cap_hits += 1
            _escalation = self._consecutive_cap_hits
            logger.warning(
                "Hard context cap hit (%d > %d chars, consecutive=%d), applying graduated truncation",
                total_chars,
                _cap,
                _escalation,
            )

            # Record metric for cap hit observability
            try:
                from app.core.prometheus_metrics import context_cap_hits_total

                context_cap_hits_total.inc({"escalation": str(min(_escalation, 5))})
            except Exception:
                logger.debug("context_cap_hits_total increment failed (non-fatal)", exc_info=True)

            # Graduated eviction: older tool results are truncated more
            # aggressively, recent ones are preserved with more context.
            # Target drops with each consecutive hit to break the growth cycle.
            _target_pct = max(0.60, 0.80 - 0.05 * (_escalation - 1))
            _target = int(_cap * _target_pct)
            tool_indices = [i for i, m in enumerate(all_msgs) if m.get("role") == "tool"]
            n_tools = len(tool_indices)
            trimmed = list(all_msgs)  # shallow copy

            # Scale limits by overshoot ratio: more aggressive when further over cap.
            # Floor drops with consecutive hits (0.3 → 0.2 → 0.1 min).
            _overshoot = total_chars / _cap  # e.g. 1.3 means 30% over
            _scale_floor = max(0.10, 0.30 - 0.10 * (_escalation - 1))
            _scale = max(_scale_floor, 1.0 / _overshoot)

            # Per-message floor also drops with escalation (100 → 60 → 30).
            _msg_floor = max(30, 100 - 20 * (_escalation - 1))

            for rank, idx in enumerate(tool_indices):
                m = trimmed[idx]
                content = m.get("content", "")
                if not isinstance(content, str):
                    continue
                # Determine limit based on recency (0.0 = oldest, 1.0 = newest)
                age_ratio = 0.0 if n_tools <= 1 else rank / (n_tools - 1)
                if age_ratio < 0.33:
                    limit = int(200 * _scale)  # oldest third: aggressive truncation
                elif age_ratio < 0.66:
                    limit = int(600 * _scale)  # middle third: moderate truncation
                else:
                    limit = int(1500 * _scale)  # newest third: preserve more context
                limit = max(limit, _msg_floor)
                if len(content) > limit:
                    trimmed[idx] = {**m, "content": content[:limit] + "\n[... truncated ...]"}
            self.memory.messages = trimmed

            # Verify we reached the target; if not, do a second pass
            _after = sum(len(str(m.get("content", ""))) for m in trimmed)
            if _after > _target and tool_indices:
                # Second-pass floor also tightens with escalation
                _second_floor = max(50, 150 - 25 * (_escalation - 1))
                for idx in tool_indices:
                    m = trimmed[idx]
                    content = m.get("content", "")
                    if isinstance(content, str) and len(content) > _second_floor:
                        trimmed[idx] = {**m, "content": content[:_second_floor] + "\n[... truncated ...]"}
                self.memory.messages = trimmed

            # Third pass (escalation 3+): also truncate older assistant messages.
            # Large step results in assistant messages contribute significantly
            # to context growth and are missed by tool-only truncation.
            if _escalation >= 3:
                _after = sum(len(str(m.get("content", ""))) for m in trimmed)
                if _after > _target:
                    assistant_indices = [
                        i
                        for i, m in enumerate(trimmed)
                        if m.get("role") == "assistant" and len(str(m.get("content", ""))) > 500
                    ]
                    # Preserve the most recent assistant message (current step output)
                    if assistant_indices:
                        _asst_limit = max(200, 800 - 150 * (_escalation - 2))
                        for idx in assistant_indices[:-1]:  # skip the last (newest)
                            m = trimmed[idx]
                            content = str(m.get("content", ""))
                            if len(content) > _asst_limit:
                                trimmed[idx] = {
                                    **m,
                                    "content": content[:_asst_limit] + "\n[... earlier output truncated ...]",
                                }
                        self.memory.messages = trimmed

            # Escalation 3+: block reads via middleware and inject nudge.
            if _escalation >= 3:
                logger.warning(
                    "Context cap hit %d consecutive times — blocking reads and injecting step-advance nudge",
                    _escalation,
                )
                # Activate read blocking on the efficiency monitor middleware.
                # Pass escalation level so the middleware can broaden the block
                # from file_read-only (3-4) to ALL read tools (5+).
                self._set_context_cap_read_block(blocked=True, escalation=_escalation)
                self._efficiency_nudges.append(
                    {
                        "message": (
                            "IMPORTANT: You have been operating near the context limit for too long. "
                            "Stop reading files and gathering more information. Immediately synthesize "
                            "what you have and produce your final output for this step."
                        ),
                        "confidence": 0.95,
                        "hard_stop": _escalation >= 5,
                    }
                )

            # Escalation 5+: hard circuit breaker — force step advancement.
            # The nudge alone relies on the LLM choosing to stop, which doesn't
            # reliably break the loop.  Setting _stuck_recovery_exhausted triggers
            # a real break in the execute() loop via plan_act.
            if _escalation >= 5:
                logger.warning(
                    "Context cap escalation %d >= 5: forcing step advancement via stuck_recovery_exhausted",
                    _escalation,
                )
                self._stuck_recovery_exhausted = True

                # Record metric for forced step advance observability
                try:
                    from app.core.prometheus_metrics import forced_step_advance_total

                    forced_step_advance_total.inc({"reason": "context_cap_escalation"})
                except Exception:
                    logger.debug("forced_step_advance_total increment failed (non-fatal)", exc_info=True)
        else:
            # Context is under cap — reset consecutive counter and unblock reads.
            # Use 75% threshold (not 90%) so trivial dips don't reset the counter
            # only for the next tool response to immediately re-flood context.
            if self._consecutive_cap_hits > 0 and total_chars < _cap * 0.75:
                self._consecutive_cap_hits = 0
                self._set_context_cap_read_block(blocked=False, escalation=0)

        # Inject efficiency nudges if any are pending (DeepCode Phase 2: Tool Efficiency Monitor)
        if self._efficiency_nudges:
            # Take the most severe nudge (hard_stop takes priority)
            nudge = max(self._efficiency_nudges, key=lambda n: (n.get("hard_stop", False), n["confidence"]))
            # Always use "user" role — many LLM APIs (e.g. GLM-5) reject mid-conversation system messages
            nudge_message = {
                "role": "user",
                "content": nudge["message"],
            }
            await self._add_to_memory([nudge_message])
            self._efficiency_nudges.clear()

        # Inject blocked-domains context from URL failure guard so the LLM
        # stops wasting cycles on domains that have been confirmed unreliable.
        # Only inject when the set of blocked domains changes (not every turn).
        if self._url_failure_guard is not None:
            _blocked_ctx = self._url_failure_guard.get_blocked_domains_context()
            if _blocked_ctx:
                _injected_set: set[str] = getattr(self, "_injected_blocked_domains", set())
                _current_blocked = frozenset(
                    d
                    for d, c in self._url_failure_guard._domain_failures.items()
                    if c >= self._url_failure_guard._domain_block_threshold
                )
                if _current_blocked != _injected_set:
                    await self._add_to_memory([{"role": "user", "content": _blocked_ctx}])
                    self._injected_blocked_domains = _current_blocked  # type: ignore[attr-defined]

            # Fix 2: Inject URL hallucination warning when the agent has
            # fabricated URLs that returned 404.  Instructs the model to
            # only use URLs from search results.
            _halluc_ctx = self._url_failure_guard.get_url_hallucination_context()
            if _halluc_ctx:
                _injected_halluc: set[str] = getattr(self, "_injected_halluc_domains", set())
                _current_halluc = frozenset(self._url_failure_guard._guessed_url_domains)
                if _current_halluc != _injected_halluc:
                    await self._add_to_memory([{"role": "user", "content": _halluc_ctx}])
                    self._injected_halluc_domains = _current_halluc  # type: ignore[attr-defined]

        response_format = None
        if format:
            response_format = {"type": format}

        from app.domain.services.agents.token_budget_manager import BudgetAction

        empty_response_count = 0
        max_empty_responses = 5
        # Safety valve: cap consecutive after_step INJECT retries to prevent
        # infinite text→inject→text loops when stuck detection fires on
        # stale tool-action history.
        after_step_inject_count = 0
        max_after_step_injects = 2

        for _retry in range(self.max_retries + max_empty_responses):
            usage_ratio = self._current_token_usage_ratio()
            budget_action = self._resolve_budget_action(usage_ratio)
            available_tools = self.get_available_tools()
            max_tokens_override: int | None = None

            if self._truncation_retry_max_tokens is not None:
                max_tokens_override = self._truncation_retry_max_tokens

            # Force text-only response after repeated truncations to escape
            # the empty-args loop (e.g. GLM-5 hitting output limits).
            if self._recent_truncation_count >= max(1, self.max_consecutive_truncations - 1):
                available_tools = []
                logger.warning(
                    "Forcing text-only response after %d consecutive truncations",
                    self._recent_truncation_count,
                )

            if budget_action == BudgetAction.REDUCE_VERBOSITY:
                llm_default_max = int(getattr(self.llm, "max_tokens", 2048) or 2048)
                reduced_limit = max(512, llm_default_max // 2)
                max_tokens_override = (
                    reduced_limit if max_tokens_override is None else min(max_tokens_override, reduced_limit)
                )
            elif budget_action == BudgetAction.FORCE_CONCLUDE:
                await self._inject_budget_notice_if_needed(self._TOKEN_BUDGET_FORCE_CONCLUDE_MESSAGE)
            elif budget_action == BudgetAction.FORCE_HARD_STOP_NUDGE:
                await self._inject_budget_notice_if_needed(self._TOKEN_BUDGET_FORCE_CONCLUDE_MESSAGE)
                available_tools = self._filter_read_tools(available_tools)
            elif budget_action == BudgetAction.HARD_STOP_TOOLS:
                await self._inject_budget_notice_if_needed(self._TOKEN_BUDGET_HARD_STOP_MESSAGE)
                available_tools = None
                self._active_phase = "summarizing"

            try:
                # Build message list for LLM — inject scratchpad transiently
                llm_messages = self.memory.get_messages()
                if self._scratchpad and not self._scratchpad.is_empty:
                    scratchpad_content = self._scratchpad.get_content()
                    if scratchpad_content:
                        # Insert scratchpad after system messages, before conversation.
                        # Uses "user" role for GLM-5 compatibility.
                        insert_idx = 0
                        for idx, m in enumerate(llm_messages):
                            if m.get("role") == "system":
                                insert_idx = idx + 1
                            else:
                                break
                        llm_messages = list(llm_messages)  # shallow copy to avoid mutating memory
                        llm_messages.insert(
                            insert_idx,
                            {"role": "user", "content": scratchpad_content},
                        )

                # ── Pre-call token validation ───────────────────────────
                # Prevent sending oversized payloads that cause LLM timeouts.
                # If token count exceeds 70% of the effective limit, force
                # emergency compaction BEFORE the call instead of timing out.
                _pre_call_tokens = self._token_manager.count_messages_tokens(llm_messages)
                _pre_call_limit = self._token_manager._effective_limit
                if _pre_call_tokens > _pre_call_limit * 0.70:
                    logger.warning(
                        "Pre-call token validation: %d tokens (%.0f%% of %d limit), forcing emergency compaction",
                        _pre_call_tokens,
                        (_pre_call_tokens / _pre_call_limit) * 100,
                        _pre_call_limit,
                    )
                    # Aggressively truncate all tool results except the last 2
                    _tool_idxs = [i for i, m in enumerate(llm_messages) if m.get("role") == "tool"]
                    _keep_n = 2
                    for tidx in _tool_idxs[:-_keep_n] if len(_tool_idxs) > _keep_n else []:
                        _tc = llm_messages[tidx].get("content", "")
                        if isinstance(_tc, str) and len(_tc) > 150:
                            llm_messages[tidx] = {
                                **llm_messages[tidx],
                                "content": _tc[:150] + "\n[...pre-call compacted...]",
                            }
                    # Persist the compacted state back to memory
                    self.memory.messages = llm_messages

                self._turn_iterations += 1
                self._turn_prompt_tokens += self._estimate_prompt_tokens(llm_messages, available_tools)
                message = await self.llm.ask(
                    llm_messages,
                    tools=available_tools,
                    response_format=response_format,
                    tool_choice=self.tool_choice,
                    model=self._step_model_override,  # DeepCode Phase 1: Adaptive model selection
                    max_tokens=max_tokens_override,
                )
            except TokenLimitExceededError as e:
                logger.warning(f"Token limit exceeded, trimming context: {e}")
                await self._handle_token_limit_exceeded()
                continue
            except Exception as e:
                error_context = self._error_handler.classify_error(e)
                if error_context.error_type == ErrorType.TOKEN_LIMIT:
                    await self._handle_token_limit_exceeded()
                    continue
                raise

            # Detect truncated responses via _finish_reason from LLM adapters
            is_truncated = message.get("_finish_reason") == "length" or message.get("_tool_args_truncated", False)

            # Also detect malformed/truncated tool-call arguments heuristically.
            # Some providers return finish_reason="stop" even when tool args are
            # cut off or malformed. Validate args strictly before execution.
            if not is_truncated and message.get("tool_calls"):
                for tc in message.get("tool_calls", []):
                    func = tc.get("function", {}) if isinstance(tc, dict) else {}
                    tool_name = func.get("name", "unknown")
                    raw_args = func.get("arguments", "")

                    try:
                        parsed_args = self._parse_tool_arguments(raw_args, function_name=tool_name)
                    except ValueError as parse_err:
                        logger.warning(
                            "Tool call '%s' has malformed args (%s) — treating as truncation",
                            tool_name,
                            parse_err,
                        )
                        is_truncated = True
                        break

                    if not parsed_args and self._tool_requires_arguments(tool_name):
                        logger.warning(
                            "Tool call '%s' has empty args despite required parameters — treating as truncation",
                            tool_name,
                        )
                        is_truncated = True
                        break

            if is_truncated and message.get("tool_calls"):
                # Truncated tool calls have malformed/empty JSON — drop and retry.
                # Tell the LLM to break content into smaller pieces to avoid
                # hitting the output limit again.
                self._recent_truncation_count += 1
                llm_default_max = int(getattr(self.llm, "max_tokens", 2048) or 2048)
                if self._truncation_retry_max_tokens is None:
                    self._truncation_retry_max_tokens = max(512, llm_default_max // 2)
                else:
                    self._truncation_retry_max_tokens = max(512, self._truncation_retry_max_tokens // 2)
                logger.warning(
                    "LLM response truncated with partial tool_calls (consecutive: %d) — requesting smaller output",
                    self._recent_truncation_count,
                )
                await self._add_to_memory(
                    [
                        {"role": "assistant", "content": message.get("content") or ""},
                        {
                            "role": "user",
                            "content": (
                                "Your previous response was cut off due to output length limits, "
                                "so the tool call arguments were lost. "
                                "Please break your work into SMALLER pieces:\n"
                                "- If writing a file, write it in sections using multiple smaller writes\n"
                                "- If the content is long, summarize first then write details separately\n"
                                "- Do NOT try to write the entire content in a single tool call\n"
                                "Continue with a smaller action now."
                            ),
                        },
                    ]
                )
                continue

            if is_truncated and message.get("content"):
                # Text-only truncation: request continuation instead of returning partial answer
                self._recent_truncation_count += 1
                if self._recent_truncation_count <= 2:
                    logger.warning(
                        "LLM response truncated (text-only, consecutive: %d) — requesting continuation",
                        self._recent_truncation_count,
                    )
                    await self._add_to_memory(
                        [
                            {"role": "assistant", "content": message["content"]},
                            {
                                "role": "user",
                                "content": "Your previous response was cut off. Please continue from where you stopped.",
                            },
                        ]
                    )
                    continue
                logger.warning("Final answer truncated after %d continuation attempts", self._recent_truncation_count)
                message["content"] = message["content"] + "\n\n[Note: Response may be incomplete due to length limits]"

            filtered_message = {}
            if message.get("role") == "assistant":
                if not message.get("content") and not message.get("tool_calls"):
                    empty_response_count += 1
                    if empty_response_count >= max_empty_responses:
                        logger.error(
                            f"Empty response from LLM after {empty_response_count} attempts, returning fallback"
                        )
                        return {
                            "role": "assistant",
                            "content": (
                                "I encountered difficulties completing this step. "
                                "The information gathered so far has been preserved. "
                                "Please try again or rephrase your request."
                            ),
                        }
                    logger.warning(
                        f"Assistant message has no content ({empty_response_count}/{max_empty_responses}), retry"
                    )
                    await self._add_to_memory(
                        [
                            {"role": "assistant", "content": ""},
                            {"role": "user", "content": "no thinking, please continue"},
                        ]
                    )
                    continue
                filtered_message = {
                    "role": "assistant",
                    "content": message.get("content"),
                }
                if message.get("tool_calls"):
                    tool_calls = message.get("tool_calls", [])
                    # Allow multiple tool calls for safe parallel tools
                    if self._can_parallelize_tools(tool_calls):
                        filtered_message["tool_calls"] = tool_calls[:MAX_CONCURRENT_TOOLS]
                    else:
                        filtered_message["tool_calls"] = tool_calls[:1]
            else:
                logger.warning(f"Unknown message role: {message.get('role')}")
                filtered_message = message

            self._turn_completion_tokens += self._estimate_completion_tokens(filtered_message)

            # ── Stuck detection via middleware pipeline ──
            # StuckDetectionMiddleware.after_step() calls track_response() and
            # handles recovery (INJECT) or exhaustion (FORCE).
            if hasattr(self, "_mw_ctx") and self._mw_ctx is not None:
                from app.domain.services.agents.middleware import (
                    MiddlewareSignal as _MwSig,
                )

                self._mw_ctx.metadata["last_response"] = filtered_message
                _after_result = await self._pipeline.run_after_step(self._mw_ctx)

                if _after_result.signal == _MwSig.FORCE:
                    self._stuck_recovery_exhausted = True
                    # Don't break — just set flag, let caller handle
                elif _after_result.signal == _MwSig.INJECT:
                    after_step_inject_count += 1
                    if after_step_inject_count > max_after_step_injects:
                        logger.warning(
                            "after_step INJECT cap reached (%d/%d) — forcing response through",
                            after_step_inject_count,
                            max_after_step_injects,
                        )
                        # Fall through to return the response instead of looping
                    else:
                        await self._add_to_memory(
                            [filtered_message, {"role": "user", "content": _after_result.message}]
                        )
                        continue

            await self._add_to_memory([filtered_message])
            empty_response_count = 0  # Reset on successful non-empty response
            self._recent_truncation_count = 0  # Reset truncation counter on success
            self._truncation_retry_max_tokens = None
            return filtered_message

        # Retry loop exhausted — return graceful fallback instead of crashing
        logger.error("LLM retry loop exhausted, returning fallback response")
        return {
            "role": "assistant",
            "content": (
                "I encountered difficulties completing this step. "
                "The information gathered so far has been preserved. "
                "Please try again or rephrase your request."
            ),
        }

    # ── Token limit enforcement ───────────────────────────────────────────────

    async def _ensure_within_token_limit(self) -> None:
        """Ensure memory is within token limits, trim if necessary.

        When feature_token_budget_manager is enabled and a TokenBudget is set,
        uses budget-aware sliding window compression. Otherwise falls back to
        the legacy two-stage strategy (proactive compaction + hard trim).
        """
        await self._ensure_memory()
        if self._compression_guard_active:
            # Guard already tripped for this step; avoid repeated compression loops.
            return
        current_messages = self.memory.get_messages()

        # ── Budget-aware path (Phase 2) ──────────────────────────────
        flags = self._resolve_feature_flags()
        if (
            flags.get("token_budget_manager")
            and self._token_budget is not None
            and self._token_budget_manager is not None
        ):
            from app.domain.services.agents.token_budget_manager import BudgetPhase

            phase = self._active_phase or "execution"
            budget_phase_map = {
                "planning": BudgetPhase.PLANNING,
                "executing": BudgetPhase.EXECUTION,
                "verifying": BudgetPhase.EXECUTION,
                "summarizing": BudgetPhase.SUMMARIZATION,
            }
            budget_phase = budget_phase_map.get(phase, BudgetPhase.EXECUTION)

            ok, reason = self._token_budget_manager.check_before_call(
                self._token_budget,
                budget_phase,
                current_messages,
            )
            if not ok:
                self._compression_cycles_this_step += 1
                if self._compression_cycles_this_step > self.max_compression_cycles_per_step:
                    self._trip_compression_guard(
                        stage_label="budget-aware",
                        current_messages=current_messages,
                    )
                    return
                logger.info("Token budget exceeded (%s), compressing to fit", reason)
                compressed = self._token_budget_manager.compress_to_fit(
                    self._token_budget,
                    budget_phase,
                    current_messages,
                )
                self.memory.messages = compressed
            return

        # ── Legacy path (reactive two-stage) ─────────────────────────
        # Stage 1: Proactive compaction before hitting the hard limit.
        # Uses configurable context_compression_trigger_pct (default 0.80) for
        # earlier triggering. Falls back to TokenManager early_warning (0.60).
        token_count = self._token_manager.count_messages_tokens(current_messages)
        try:
            from app.core.config import get_settings

            trigger_threshold = getattr(get_settings(), "context_compression_trigger_pct", 0.80)
        except Exception:
            trigger_threshold = self._token_manager.PRESSURE_THRESHOLDS["early_warning"]
        if token_count > self._token_manager._effective_limit * trigger_threshold:
            self._compression_cycles_this_step += 1
            if self._compression_cycles_this_step > self.max_compression_cycles_per_step:
                self._trip_compression_guard(
                    stage_label="legacy-stage-1",
                    current_messages=current_messages,
                )
                return
            # Use graduated compaction when enabled (preserves more info)
            flags = self._resolve_feature_flags()
            if flags.get("graduated_compaction") and self.memory.config.use_graduated_compaction:
                self.memory.graduated_compact()
            else:
                self.memory.smart_compact()
            current_messages = self.memory.get_messages()
            logger.debug(
                f"Proactive context compaction at {token_count} tokens "
                f"({token_count / self._token_manager._effective_limit:.0%} utilization)"
            )

        # Stage 2: Hard-limit trim if still over after compaction.
        if not self._token_manager.is_within_limit(current_messages):
            self._compression_cycles_this_step += 1
            if self._compression_cycles_this_step > self.max_compression_cycles_per_step:
                self._trip_compression_guard(
                    stage_label="legacy-stage-2",
                    current_messages=current_messages,
                )
                return
            logger.warning("Memory exceeds token limit, trimming...")
            # Capture the first user message before trimming — it contains the original
            # request and must survive trimming to prevent topic drift / hallucination.
            first_user_msg = next((m for m in current_messages if m.get("role") == "user"), None)
            trimmed_messages, tokens_removed = self._token_manager.trim_messages(
                current_messages, preserve_system=True, preserve_recent=6
            )
            # Re-inject first user message if it was lost during trimming
            if first_user_msg and not any(m is first_user_msg for m in trimmed_messages):
                # Insert after system messages, before the remaining conversation
                insert_idx = 0
                for i, m in enumerate(trimmed_messages):
                    if m.get("role") == "system":
                        insert_idx = i + 1
                    else:
                        break
                trimmed_messages.insert(insert_idx, first_user_msg)
                logger.info("Re-injected first user message after trimming to preserve topic anchor")
            self.memory.messages = trimmed_messages
            await self._repository.save_memory(self._agent_id, self.name, self.memory)
            logger.info(f"Trimmed memory, removed {tokens_removed} tokens")

        # Stage 3: Structured compaction (emergency LLM summary) when still over limit.
        current_messages = self.memory.get_messages()
        if not self._token_manager.is_within_limit(current_messages):
            flags_s3 = self._resolve_feature_flags()
            if flags_s3.get("structured_compaction"):
                self._compression_cycles_this_step += 1
                if self._compression_cycles_this_step <= self.max_compression_cycles_per_step:
                    from app.domain.services.agents.memory_manager import get_memory_manager

                    mm = get_memory_manager()
                    compacted_msgs, tokens_saved = await mm.structured_compact(
                        current_messages, self.llm, preserve_recent=6
                    )
                    if tokens_saved > 0:
                        self.memory.messages = compacted_msgs
                        await self._repository.save_memory(self._agent_id, self.name, self.memory)
                        logger.info("Structured compaction saved ~%d tokens", tokens_saved)

    async def _handle_token_limit_exceeded(self) -> None:
        """Handle token limit exceeded error by aggressively trimming context.

        Memory compaction and trimming are done synchronously (fast, in-memory),
        but the MongoDB save is done in the background to avoid blocking the retry loop.
        """
        await self._ensure_memory()

        # First compact verbose tool results (fast, in-memory)
        self.memory.smart_compact()

        # Then trim messages (fast, in-memory)
        all_messages = self.memory.get_messages()
        # Capture the first user message before trimming for topic preservation
        first_user_msg = next((m for m in all_messages if m.get("role") == "user"), None)
        trimmed_messages, tokens_removed = self._token_manager.trim_messages(
            all_messages,
            preserve_system=True,
            preserve_recent=4,  # More aggressive trim
        )
        # Re-inject first user message if lost during aggressive trimming
        if first_user_msg and not any(m is first_user_msg for m in trimmed_messages):
            insert_idx = 0
            for i, m in enumerate(trimmed_messages):
                if m.get("role") == "system":
                    insert_idx = i + 1
                else:
                    break
            trimmed_messages.insert(insert_idx, first_user_msg)
            logger.info("Re-injected first user message after aggressive trim to preserve topic anchor")
        self.memory.messages = trimmed_messages

        # Save to MongoDB in background (non-blocking) to avoid delaying retry
        # Snapshot messages to avoid race with main loop mutating self.memory
        from app.domain.models.memory import Memory

        memory_snapshot = Memory(messages=list(self.memory.messages))

        async def _save_background() -> None:
            try:
                await self._repository.save_memory(self._agent_id, self.name, memory_snapshot)
                logger.debug("Background memory save completed after token limit handling")
            except Exception as e:
                logger.warning(f"Background memory save failed after token limit handling: {e}")

        task = asyncio.create_task(_save_background())
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        logger.info(f"Handled token limit by trimming {tokens_removed} tokens (save in background)")

    # ── Compression guard ─────────────────────────────────────────────────────

    def _trip_compression_guard(self, stage_label: str, current_messages: list[dict[str, Any]]) -> None:
        """Latch compression guard and apply one-shot emergency trim.

        This prevents repeated compaction churn within the same step while still
        preserving a minimal anchored context for graceful completion.
        """
        if self._compression_guard_active:
            return
        self._compression_guard_active = True
        self._stuck_recovery_exhausted = True
        logger.warning(
            "Compression oscillation guard triggered (%d/%d cycles this step, %s). "
            "Applying emergency context trim and skipping further compression this step.",
            self._compression_cycles_this_step,
            self.max_compression_cycles_per_step,
            stage_label,
        )

        first_user_msg = next((m for m in current_messages if m.get("role") == "user"), None)
        trimmed_messages, _tokens_removed = self._token_manager.trim_messages(
            current_messages,
            preserve_system=True,
            preserve_recent=2,
        )
        if first_user_msg and not any(m is first_user_msg for m in trimmed_messages):
            insert_idx = 0
            for i, msg in enumerate(trimmed_messages):
                if msg.get("role") == "system":
                    insert_idx = i + 1
                else:
                    break
            trimmed_messages.insert(insert_idx, first_user_msg)
        self.memory.messages = trimmed_messages

    # ── Streaming ask ─────────────────────────────────────────────────────────

    async def ask_streaming(self, request: str, format: str | None = None) -> AsyncGenerator[BaseEvent, None]:
        """Execute a request with streaming LLM response.

        Yields StreamEvents as content chunks arrive, then MessageEvent for full response.
        Falls back to non-streaming if LLM doesn't support streaming.

        Args:
            request: The user request
            format: Optional response format

        Yields:
            StreamEvent for each content chunk, then MessageEvent with full content
        """
        # Add request to memory
        await self._add_to_memory([{"role": "user", "content": request}])
        await self._ensure_within_token_limit()

        # Inject efficiency nudges if any are pending (DeepCode Phase 2: Tool Efficiency Monitor)
        if self._efficiency_nudges:
            nudge = max(self._efficiency_nudges, key=lambda n: (n.get("hard_stop", False), n["confidence"]))
            # Always use "user" role — many LLM APIs (e.g. GLM-5) reject mid-conversation system messages
            nudge_message = {
                "role": "user",
                "content": nudge["message"],
            }
            await self._add_to_memory([nudge_message])
            self._efficiency_nudges.clear()

        # Check if LLM supports streaming
        if not hasattr(self.llm, "ask_stream"):
            # Fall back to non-streaming — use ask_with_messages([]) since
            # user message was already added to memory above
            response = await self.ask_with_messages([], format)
            yield MessageEvent(message=response.get("content", ""))
            return

        response_format = {"type": format} if format else None
        full_content = ""

        try:
            async for chunk in self.llm.ask_stream(
                self.memory.get_messages(),
                tools=None,  # Streaming typically used without tools
                response_format=response_format,
            ):
                full_content += chunk
                yield StreamEvent(content=chunk, is_final=False)

            # Yield final stream event and message
            yield StreamEvent(content="", is_final=True)

            # Save response to memory
            await self._add_to_memory([{"role": "assistant", "content": full_content}])

            yield MessageEvent(message=full_content)

        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            # Fall back to non-streaming on error
            response = await self.ask_with_messages([], format)
            yield MessageEvent(message=response.get("content", ""))
