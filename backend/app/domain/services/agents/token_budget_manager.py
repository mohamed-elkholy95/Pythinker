"""Proactive token budget management with phase-level allocation.

Instead of reactively catching ``TokenLimitExceededError``, this module
pre-allocates token budgets per execution phase and provides graceful
degradation when budgets are exceeded.

Usage:
    budget_mgr = TokenBudgetManager(token_manager)
    budget = budget_mgr.create_budget(max_tokens=128000)

    # Before each LLM call:
    ok, reason = budget_mgr.check_before_call(budget, phase, messages, tools)
    if not ok:
        messages = budget_mgr.compress_to_fit(budget, phase, messages, target)

    # At phase transitions:
    budget_mgr.rebalance(budget, completed_phase, next_phase)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from app.domain.services.agents.token_manager import TokenManager

logger = logging.getLogger(__name__)


class BudgetPhase(str, Enum):
    """Execution phases with distinct token allocation budgets."""

    SYSTEM_PROMPT = "system_prompt"
    PLANNING = "planning"
    EXECUTION = "execution"
    MEMORY_CONTEXT = "memory_context"
    SUMMARIZATION = "summarization"


class BudgetAction(str, Enum):
    """Actions enforced as overall budget usage approaches exhaustion."""

    NORMAL = "normal"
    REDUCE_VERBOSITY = "reduce_verbosity"
    FORCE_CONCLUDE = "force_conclude"
    FORCE_HARD_STOP_NUDGE = "force_hard_stop_nudge"
    HARD_STOP_TOOLS = "hard_stop_tools"


@dataclass
class PhaseAllocation:
    """Token allocation for a single phase."""

    phase: BudgetPhase
    fraction: float  # Fraction of total budget (0.0-1.0)
    allocated_tokens: int = 0
    used_tokens: int = 0

    @property
    def remaining(self) -> int:
        return max(0, self.allocated_tokens - self.used_tokens)

    @property
    def usage_ratio(self) -> float:
        if self.allocated_tokens == 0:
            return 0.0
        return self.used_tokens / self.allocated_tokens

    @property
    def is_exceeded(self) -> bool:
        return self.used_tokens > self.allocated_tokens


@dataclass
class TokenBudget:
    """Complete token budget across all phases.

    Tracks allocation and usage per phase, enabling proactive context
    management instead of reactive overflow handling.
    """

    max_tokens: int
    safety_margin: int = 2048
    phases: dict[BudgetPhase, PhaseAllocation] = field(default_factory=dict)

    @property
    def effective_limit(self) -> int:
        return self.max_tokens - self.safety_margin

    @property
    def total_allocated(self) -> int:
        return sum(p.allocated_tokens for p in self.phases.values())

    @property
    def total_used(self) -> int:
        return sum(p.used_tokens for p in self.phases.values())

    @property
    def total_remaining(self) -> int:
        return max(0, self.effective_limit - self.total_used)

    @property
    def overall_usage_ratio(self) -> float:
        if self.effective_limit == 0:
            return 0.0
        return self.total_used / self.effective_limit

    def record_usage(self, phase: BudgetPhase, tokens: int) -> None:
        """Record token usage for a phase."""
        if phase in self.phases:
            self.phases[phase].used_tokens += tokens

    def get_phase_remaining(self, phase: BudgetPhase) -> int:
        """Get remaining tokens for a specific phase."""
        alloc = self.phases.get(phase)
        if alloc is None:
            return 0
        return alloc.remaining


class TokenBudgetManager:
    """Proactive phase-level token budget allocation and management.

    Default allocations:
    - System prompt: 15% (fixed overhead)
    - Planning: 15% (plan generation + pre-planning search context)
    - Execution: 45% (tool calls + responses)
    - Memory context: 10% (retrieved memories, step context)
    - Summarization: 15% (final synthesis)
    """

    DEFAULT_ALLOCATIONS: ClassVar[dict[BudgetPhase, float]] = {
        BudgetPhase.SYSTEM_PROMPT: 0.15,
        BudgetPhase.PLANNING: 0.15,
        BudgetPhase.EXECUTION: 0.45,
        BudgetPhase.MEMORY_CONTEXT: 0.10,
        BudgetPhase.SUMMARIZATION: 0.15,
    }

    # Minimum tokens per phase (floor to prevent starvation)
    MIN_PHASE_TOKENS = 1000

    # Threshold above which we trigger compression (fraction of phase budget)
    COMPRESSION_TRIGGER_RATIO = 0.85

    def __init__(
        self,
        token_manager: TokenManager,
        allocations: dict[BudgetPhase, float] | None = None,
    ) -> None:
        self._token_manager = token_manager
        self._allocations = allocations or self.DEFAULT_ALLOCATIONS

    def create_budget(self, max_tokens: int | None = None) -> TokenBudget:
        """Create a new token budget with phase allocations.

        Args:
            max_tokens: Total context window size. If None, uses the
                token manager's configured limit.

        Returns:
            Initialized TokenBudget with per-phase allocations.
        """
        if max_tokens is None:
            max_tokens = self._token_manager._max_tokens

        budget = TokenBudget(max_tokens=max_tokens)
        effective = budget.effective_limit

        for phase, fraction in self._allocations.items():
            allocated = max(self.MIN_PHASE_TOKENS, int(effective * fraction))
            budget.phases[phase] = PhaseAllocation(
                phase=phase,
                fraction=fraction,
                allocated_tokens=allocated,
            )

        logger.debug(
            "Created token budget: max=%d, effective=%d, phases=%s",
            max_tokens,
            effective,
            {p.value: a.allocated_tokens for p, a in budget.phases.items()},
        )
        return budget

    def create_dynamic_budget(
        self,
        model_name: str,
        api_base: str | None = None,
    ) -> TokenBudget:
        """Create a ``TokenBudget`` scaled to the model's actual context window.

        Delegates to ``ContextWindowManager`` which reads the capabilities
        registry (Phase 3) when ``feature_llm_dynamic_context=True``.
        Falls back to ``create_budget(max_tokens=None)`` when the flag is off.

        Args:
            model_name: Full model identifier (e.g. ``"qwen/qwen3-coder-next"``).
            api_base: Optional base URL for capability override.

        Returns:
            ``TokenBudget`` with per-phase allocations scaled to the model's
            actual context window.
        """
        try:
            from app.domain.services.llm.context_window_manager import get_context_window_manager

            manager = get_context_window_manager()
            limit = manager.get_effective_limit(model_name, api_base)
            return self.create_budget(max_tokens=limit)
        except Exception as exc:
            logger.warning("create_dynamic_budget fallback (model=%s): %s", model_name, exc)
            return self.create_budget()

    def enforce_budget_policy(self, usage_pct: float) -> BudgetAction:
        """Map overall usage ratio to an enforcement action.

        Thresholds:
        - 90%: reduce verbosity
        - 95%: force conclude
        - 98%: force hard-stop nudge semantics
        - 99%: hard-stop all tool calls
        """
        if usage_pct >= 0.99:
            return BudgetAction.HARD_STOP_TOOLS
        if usage_pct >= 0.98:
            return BudgetAction.FORCE_HARD_STOP_NUDGE
        if usage_pct >= 0.95:
            return BudgetAction.FORCE_CONCLUDE
        if usage_pct >= 0.90:
            return BudgetAction.REDUCE_VERBOSITY
        return BudgetAction.NORMAL

    def check_before_call(
        self,
        budget: TokenBudget,
        phase: BudgetPhase,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
    ) -> tuple[bool, str]:
        """Pre-flight check: can this LLM call fit within the phase budget?

        Args:
            budget: Current token budget.
            phase: Active execution phase.
            messages: Messages to be sent.
            tools: Tool definitions (counted toward token usage).

        Returns:
            Tuple of (can_proceed, reason). If False, the caller should
            compress messages before proceeding.
        """
        message_tokens = self._token_manager.count_messages_tokens(messages)
        tool_tokens = self._estimate_tool_tokens(tools) if tools else 0
        total_needed = message_tokens + tool_tokens

        phase_alloc = budget.phases.get(phase)
        if phase_alloc is None:
            return True, "Phase not budgeted"

        # Check phase-level budget
        if total_needed > phase_alloc.remaining:
            return False, (
                f"Phase {phase.value} budget exceeded: "
                f"need {total_needed}, remaining {phase_alloc.remaining} "
                f"(allocated {phase_alloc.allocated_tokens})"
            )

        # Check global budget
        if total_needed > budget.total_remaining:
            return False, (f"Global budget exceeded: need {total_needed}, remaining {budget.total_remaining}")

        # Warn if approaching limit
        if phase_alloc.allocated_tokens > 0:
            projected_usage = (phase_alloc.used_tokens + total_needed) / phase_alloc.allocated_tokens
            if projected_usage > self.COMPRESSION_TRIGGER_RATIO:
                logger.info(
                    "Phase %s approaching budget limit: %.1f%% after this call",
                    phase.value,
                    projected_usage * 100,
                )

        return True, "OK"

    def compress_to_fit(
        self,
        budget: TokenBudget,
        phase: BudgetPhase,
        messages: list[dict[str, Any]],
        target_tokens: int | None = None,
    ) -> list[dict[str, Any]]:
        """Graceful degradation: compress messages to fit within budget.

        Three-stage strategy:
        1. Summarize verbose tool outputs (preserve key results)
        2. Truncate long content (rule-based, preserve structure)
        3. Drop low-priority messages (oldest non-system, non-recent)

        Args:
            budget: Current token budget.
            phase: Active execution phase.
            messages: Messages to compress.
            target_tokens: Target token count. If None, uses phase remaining.

        Returns:
            Compressed message list fitting within budget.
        """
        phase_alloc = budget.phases.get(phase)
        if target_tokens is None and phase_alloc is not None:
            target_tokens = phase_alloc.remaining
        if target_tokens is None:
            target_tokens = budget.total_remaining

        current_tokens = self._token_manager.count_messages_tokens(messages)

        if current_tokens <= target_tokens:
            return messages  # Already fits

        logger.info(
            "Compressing messages: current=%d, target=%d, phase=%s",
            current_tokens,
            target_tokens,
            phase.value,
        )

        # Extract failure lessons BEFORE any truncation (feature-gated)
        lessons: str | None = None
        try:
            from app.core.config import get_settings as _get_settings

            _s = _get_settings()
            if getattr(_s, "feature_compression_context_preservation_enabled", False):
                lessons = self._extract_failure_lessons(messages)
        except Exception:
            logger.debug("Failed to check compression context preservation flag", exc_info=True)

        # Stage 1: Summarize verbose tool outputs
        compressed = self._summarize_tool_outputs(messages, target_tokens)
        if self._token_manager.count_messages_tokens(compressed) <= target_tokens:
            return self._inject_lessons(compressed, lessons)

        # Stage 2: Truncate long content
        compressed = self._truncate_long_content(compressed, target_tokens)
        if self._token_manager.count_messages_tokens(compressed) <= target_tokens:
            return self._inject_lessons(compressed, lessons)

        # Stage 3: Drop low-priority messages
        compressed, _ = self._token_manager.trim_messages(
            compressed,
            preserve_recent=4,
        )

        return self._inject_lessons(compressed, lessons)

    @staticmethod
    def _inject_lessons(messages: list[dict], lessons: str | None) -> list[dict]:
        """Inject failure lessons as a system message after the first system message."""
        if not lessons:
            return messages
        insert_idx = next(
            (i + 1 for i, m in enumerate(messages) if m.get("role") == "system"),
            0,
        )
        messages.insert(insert_idx, {"role": "system", "content": lessons})
        return messages

    def rebalance(
        self,
        budget: TokenBudget,
        completed_phase: BudgetPhase,
        next_phase: BudgetPhase,
    ) -> None:
        """Redistribute unused tokens from a completed phase to the next.

        Called at phase transitions (e.g., planning → execution).
        Reclaims unused budget from the completed phase and adds it
        to the next phase.
        """
        completed_alloc = budget.phases.get(completed_phase)
        next_alloc = budget.phases.get(next_phase)

        if completed_alloc is None or next_alloc is None:
            return

        unused = completed_alloc.remaining
        if unused > 0:
            next_alloc.allocated_tokens += unused
            logger.info(
                "Rebalanced %d tokens from %s to %s (new allocation: %d)",
                unused,
                completed_phase.value,
                next_phase.value,
                next_alloc.allocated_tokens,
            )

    def get_budget_summary(self, budget: TokenBudget) -> dict[str, Any]:
        """Return a human-readable summary of the current budget state."""
        return {
            "max_tokens": budget.max_tokens,
            "effective_limit": budget.effective_limit,
            "total_used": budget.total_used,
            "total_remaining": budget.total_remaining,
            "overall_usage_ratio": round(budget.overall_usage_ratio, 3),
            "phases": {
                phase.value: {
                    "allocated": alloc.allocated_tokens,
                    "used": alloc.used_tokens,
                    "remaining": alloc.remaining,
                    "usage_ratio": round(alloc.usage_ratio, 3),
                }
                for phase, alloc in budget.phases.items()
            },
        }

    # ── Private helpers ─────────────────────────────────────────────

    def _estimate_tool_tokens(self, tools: list[dict[str, Any]]) -> int:
        """Estimate token overhead from tool definitions."""
        if not tools:
            return 0
        # Rough estimate: ~50 tokens per tool definition on average
        return len(tools) * 50

    def _summarize_tool_outputs(
        self,
        messages: list[dict[str, Any]],
        target_tokens: int,
    ) -> list[dict[str, Any]]:
        """Stage 1: Collapse verbose tool outputs to key results.

        Preserves the last 4 tool results intact; summarizes older ones
        by truncating to the first 500 characters + a continuation marker.
        """
        result = []
        tool_results = [(i, msg) for i, msg in enumerate(messages) if msg.get("role") == "tool"]
        # Keep the last 4 tool results intact
        recent_tool_indices = {idx for idx, _ in tool_results[-4:]}

        for i, msg in enumerate(messages):
            if msg.get("role") == "tool" and i not in recent_tool_indices:
                content = msg.get("content", "")
                if isinstance(content, str) and len(content) > 500:
                    summarized = dict(msg)
                    summarized["content"] = content[:500] + "\n\n[... truncated for context budget ...]"
                    result.append(summarized)
                    continue
            result.append(msg)

        return result

    def _truncate_long_content(
        self,
        messages: list[dict[str, Any]],
        target_tokens: int,
    ) -> list[dict[str, Any]]:
        """Stage 2: Rule-based truncation of all long content.

        Limits any single message content to 2000 characters, except
        system messages and the most recent user message.
        """
        result = []
        max_content_chars = 2000

        for i, msg in enumerate(messages):
            role = msg.get("role", "")
            content = msg.get("content", "")

            # Never truncate system messages or the last user message
            if role == "system":
                result.append(msg)
                continue

            # Check if this is the last user message
            is_last_user = role == "user" and not any(m.get("role") == "user" for m in messages[i + 1 :])
            if is_last_user:
                result.append(msg)
                continue

            if isinstance(content, str) and len(content) > max_content_chars:
                truncated = dict(msg)
                truncated["content"] = content[:max_content_chars] + "\n[... truncated ...]"
                result.append(truncated)
            else:
                result.append(msg)

        return result

    # ── Error patterns for lesson extraction ─────────────────────────
    _ERROR_PATTERNS: ClassVar[list[re.Pattern]] = [
        re.compile(r"(ModuleNotFoundError): No module named '([^']+)'"),
        re.compile(r"(ImportError): (.{1,80})"),
        re.compile(r"(FileNotFoundError): (.{1,80})"),
        re.compile(r"(PermissionError|Permission denied): (.{1,80})"),
        re.compile(r"(SyntaxError): (.{1,80})"),
        re.compile(r"(exit code \d+)"),
    ]

    _MAX_LESSON_CHARS: ClassVar[int] = 500

    def _extract_failure_lessons(
        self,
        messages: list[dict[str, Any]],
    ) -> str | None:
        """Extract compact failure lessons from tool result messages.

        Scans role=tool messages for error patterns, deduplicates, and
        returns a compact string suitable for injection as a system message
        that will survive subsequent compression stages.

        Returns None if no actionable errors found.
        """
        seen: set[str] = set()
        lessons: list[str] = []

        for msg in messages:
            if msg.get("role") != "tool":
                continue
            content = msg.get("content", "")
            if not isinstance(content, str):
                continue

            for pattern in self._ERROR_PATTERNS:
                match = pattern.search(content)
                if match:
                    # Build dedup key from the matched groups
                    key = match.group(0)[:120]
                    if key not in seen:
                        seen.add(key)
                        lessons.append(f"- {key}")

        if not lessons:
            return None

        header = "[COMPRESSION_CONTEXT] Previous tool errors — do NOT retry these approaches:"
        body = "\n".join(lessons)
        full = f"{header}\n{body}"

        # Cap size to avoid bloating context
        if len(full) > self._MAX_LESSON_CHARS:
            full = full[: self._MAX_LESSON_CHARS - 3] + "..."

        return full


# ── Singleton accessor ──────────────────────────────────────────────

_budget_manager: TokenBudgetManager | None = None


def get_token_budget_manager(token_manager: TokenManager) -> TokenBudgetManager:
    """Get or create the token budget manager singleton.

    Args:
        token_manager: The token counting service to delegate to.
    """
    global _budget_manager
    if _budget_manager is None:
        _budget_manager = TokenBudgetManager(token_manager)
    return _budget_manager
