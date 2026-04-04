"""Step-level orchestration helpers extracted from PlanActFlow.

Owns the logic for agent selection per step, post-step routing decisions
(skip vs. update plan), step dependency checking, and failure cascading.

Usage:
    fse = FlowStepExecutor(
        default_executor=executor,
        phase_router=phase_router,
        step_failure_handler=step_failure_handler,
    )
    agent = await fse.get_executor_for_step(step)
    should_skip, reason = fse.should_skip_plan_update(step, remaining, ...)
    blocked_ids = fse.handle_step_failure(plan, failed_step)

This is a pure domain service with zero infrastructure imports.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING, Any

from app.domain.models.tool_permission import PermissionTier

if TYPE_CHECKING:
    from app.domain.models.plan import Plan, Step
    from app.domain.services.agents.base import BaseAgent
    from app.domain.services.flows.phase_router import PhaseRouter
    from app.domain.services.flows.step_failure import StepFailureHandler

logger = logging.getLogger(__name__)


class FlowStepExecutor:
    """Step-level orchestration extracted from PlanActFlow.

    Responsibilities:
    - Select the appropriate agent for a step (multi-agent dispatch)
    - Decide whether to skip plan updates after step completion
    - Check step dependencies and skip conditions
    - Handle step failure cascading

    The executor does NOT import any infrastructure. Agent factory,
    registry, and other collaborators are injected via constructor.
    """

    __slots__ = (
        "_active_tier",
        "_agent_factory",
        "_agent_id",
        "_agent_registry",
        "_default_executor",
        "_enable_multi_agent",
        "_phase_router",
        "_session_id",
        "_specialized_agents",
        "_step_failure_handler",
    )

    def __init__(
        self,
        *,
        default_executor: BaseAgent,
        phase_router: PhaseRouter,
        step_failure_handler: StepFailureHandler,
        agent_id: str = "",
        session_id: str = "",
        enable_multi_agent: bool = False,
        agent_registry: Any = None,
        agent_factory: Any = None,
    ) -> None:
        self._default_executor: BaseAgent = default_executor
        self._phase_router: PhaseRouter = phase_router
        self._step_failure_handler: StepFailureHandler = step_failure_handler
        self._agent_id: str = agent_id
        self._session_id: str = session_id
        self._enable_multi_agent: bool = enable_multi_agent
        self._active_tier: PermissionTier = PermissionTier.DANGER
        self._agent_registry = agent_registry
        self._agent_factory = agent_factory
        self._specialized_agents: dict[str, BaseAgent] = {}
        self._default_executor.set_active_tier(self._active_tier)

    def set_active_tier(self, tier: PermissionTier) -> None:
        """Apply the current permission tier to default and cached executors."""
        self._active_tier = tier
        self._default_executor.set_active_tier(tier)
        for agent in self._specialized_agents.values():
            agent.set_active_tier(tier)

    # ── Agent Selection ────────────────────────────────────────────────

    def _extract_agent_type(self, step_description: str) -> str | None:
        """Extract [AGENT_TYPE] prefix from step description.

        Example: "[RESEARCH] Find documentation on the topic" -> "research"
        """
        match = re.search(r"\[([A-Z_]+)\]", step_description)
        if match:
            return match.group(1).lower()
        return None

    def _infer_capabilities(self, step: Step) -> set:
        """Infer required capabilities from step description."""
        from app.domain.models.agent_registry import AgentCapability

        capabilities: set[AgentCapability] = set()
        desc_lower = step.description.lower()

        # Map keywords to capabilities
        capability_keywords = {
            AgentCapability.WEB_BROWSING: ["browse", "website", "page", "click", "navigate", "visit"],
            AgentCapability.WEB_SEARCH: ["search", "find", "lookup", "query", "google"],
            AgentCapability.CODE_WRITING: ["code", "implement", "write", "function", "class", "script", "program"],
            AgentCapability.CODE_REVIEW: ["review", "check", "audit", "verify code", "find bugs"],
            AgentCapability.FILE_OPERATIONS: ["file", "read", "write", "save", "create file", "modify"],
            AgentCapability.SHELL_COMMANDS: ["run", "execute", "shell", "command", "terminal", "bash"],
            AgentCapability.RESEARCH: ["research", "investigate", "study", "analyze", "gather"],
            AgentCapability.SUMMARIZATION: ["summarize", "summary", "brief", "overview", "condense"],
        }

        for capability, keywords in capability_keywords.items():
            for keyword in keywords:
                if keyword in desc_lower:
                    capabilities.add(capability)
                    break

        return capabilities

    async def get_executor_for_step(self, step: Step) -> BaseAgent:
        """Select the appropriate executor for a step.

        Uses the AgentRegistry to select a specialized agent based on:
        1. Explicit [AGENT_TYPE] prefix in step description
        2. Inferred capabilities from step description
        3. Falls back to the default ExecutionAgent

        Args:
            step: The step to get an executor for

        Returns:
            A BaseAgent (specialized or default ExecutionAgent)
        """
        if not self._enable_multi_agent or not self._agent_registry:
            return self._default_executor

        from app.domain.models.agent_registry import AgentType

        # Check for explicit agent type in step
        agent_type_hint = self._extract_agent_type(step.description)

        # Check if step has agent_type set
        if step.agent_type:
            agent_type_hint = step.agent_type

        # Try to match by type first
        if agent_type_hint:
            try:
                agent_type = AgentType(agent_type_hint)
                spec = self._agent_registry.get(agent_type)
                if spec:
                    # Check if we already have this agent created
                    cache_key = f"{agent_type.value}_{self._agent_id}"
                    if cache_key not in self._specialized_agents:
                        agent = await self._agent_factory.create_agent(
                            agent_type,
                            f"{self._agent_id}_{agent_type.value}",
                            spec,
                        )
                        agent.set_active_tier(self._active_tier)
                        self._specialized_agents[cache_key] = agent
                        logger.info(f"Created specialized {agent_type.value} agent for step")
                    return self._specialized_agents[cache_key]
            except ValueError:
                logger.debug(f"Unknown agent type hint: {agent_type_hint}")

        # Try to match by inferred capabilities
        capabilities = self._infer_capabilities(step)
        if capabilities:
            candidates = self._agent_registry.select_for_task(
                task_description=step.description,
                context={"session_id": self._session_id},
                required_capabilities=capabilities,
            )
            if candidates:
                best_spec = candidates[0]
                cache_key = f"{best_spec.agent_type.value}_{self._agent_id}"
                if cache_key not in self._specialized_agents:
                    agent = await self._agent_factory.create_agent(
                        best_spec.agent_type,
                        f"{self._agent_id}_{best_spec.agent_type.value}",
                        best_spec,
                    )
                    agent.set_active_tier(self._active_tier)
                    self._specialized_agents[cache_key] = agent
                    logger.info(
                        f"Selected specialized {best_spec.agent_type.value} agent "
                        f"for step based on capabilities: {capabilities}"
                    )
                return self._specialized_agents[cache_key]

        # Fall back to default executor
        return self._default_executor

    # ── Post-Step Routing ──────────────────────────────────────────────

    def is_read_only_step(self, step: Step) -> bool:
        """Check if a step is likely read-only (doesn't modify state).

        Read-only steps don't require plan updates after completion since they
        don't change the execution context significantly.

        Args:
            step: The step to check

        Returns:
            True if the step appears to be read-only
        """
        if not step or not step.description:
            return False

        desc_lower = step.description.lower()

        # Research-style steps can discover new work and should keep plan updates enabled.
        dynamic_research_patterns = [
            "research",
            "investigate",
            "explore",
            "analyze",
            "review",
            "compare",
            "search",
            "browse",
            "fetch",
            "retrieve",
            "verify",
            "validate",
            "cross-check",
            "benchmark",
        ]
        if any(pattern in desc_lower for pattern in dynamic_research_patterns):
            return False

        # Read-only action patterns
        read_only_patterns = [
            "read",
            "view",
            "list",
            "check",
            "inspect",
            "show",
            "display",
            "print",
            "understand",
            "learn",
        ]

        # Write action patterns (if present, NOT read-only)
        write_patterns = [
            "write",
            "create",
            "modify",
            "update",
            "delete",
            "remove",
            "install",
            "execute",
            "run",
            "build",
            "compile",
            "deploy",
            "change",
            "edit",
            "save",
            "store",
            "set",
            "configure",
        ]

        has_read_pattern = any(pattern in desc_lower for pattern in read_only_patterns)
        has_write_pattern = any(pattern in desc_lower for pattern in write_patterns)

        # Read-only if has read patterns but no write patterns
        return has_read_pattern and not has_write_pattern

    def is_research_or_complex_task(
        self,
        plan: Plan | None,
        step: Step | None = None,
        cached_complexity: float | None = None,
    ) -> bool:
        """Detect tasks where dynamic plan updates should remain enabled."""
        try:
            if cached_complexity is not None and cached_complexity >= 0.45:
                return True
        except Exception:
            logger.debug("Complexity probe failed while checking dynamic plan update eligibility", exc_info=True)

        research_patterns = [
            "research",
            "investigate",
            "explore",
            "analyze",
            "compare",
            "multi-source",
            "multiple sources",
            "benchmark",
            "report",
            "citation",
            "cross-check",
            "verify findings",
            "validate findings",
        ]
        texts_to_scan: list[str] = []
        if step and step.description:
            texts_to_scan.append(step.description)
        if plan:
            if plan.goal:
                texts_to_scan.append(plan.goal)
            if plan.message:
                texts_to_scan.append(plan.message)

        for text in texts_to_scan:
            lowered = text.lower()
            if any(pattern in lowered for pattern in research_patterns):
                return True
        return False

    def should_skip_plan_update(
        self,
        step: Step,
        remaining_steps: int,
        plan: Plan | None = None,
        cached_complexity: float | None = None,
    ) -> tuple[bool, str]:
        """Determine if plan update phase should be skipped for faster execution.

        Skipping plan updates saves 2-5 seconds per step by avoiding an LLM call.
        Safe to skip when the plan state is predictable.

        Args:
            step: The step that just completed
            remaining_steps: Number of pending steps remaining
            plan: The current plan (for research/complex detection)
            cached_complexity: Pre-computed task complexity score

        Returns:
            Tuple of (should_skip, reason)
        """
        # No remaining work means there is nothing left to update.
        if remaining_steps <= 0:
            return True, "no remaining steps"

        # Skip if step failed (will trigger replanning anyway)
        if not step.success:
            return True, "step failed"

        # Keep dynamic updates enabled for research/complex tasks so the planner
        # can add follow-up steps when discoveries require deeper investigation.
        if self.is_research_or_complex_task(plan, step, cached_complexity):
            return False, ""

        # Skip for simple tasks (complexity-based optimization)
        try:
            if cached_complexity is not None and cached_complexity < 0.4:
                return True, f"simple task (complexity={cached_complexity:.2f})"
        except Exception as e:
            logger.debug(f"Complexity check failed, continuing with verification: {e}")

        # Skip for read-only steps (they don't change execution context)
        if self.is_read_only_step(step) and remaining_steps <= 1:
            return True, "read-only step"

        # For non-research tasks, skip update on final pending step.
        if remaining_steps == 1:
            return True, "final pending step"

        # Default: don't skip
        return False, ""

    # ── Pre-Step Guards ────────────────────────────────────────────────

    def check_step_dependencies(self, plan: Plan | None, step: Step) -> bool:
        """Check step dependencies (delegated to PhaseRouter)."""
        if not plan:
            return True
        return self._phase_router.check_step_dependencies(plan, step)

    def should_skip_step(self, plan: Plan | None, step: Step) -> tuple[bool, str]:
        """Check if a step should be skipped (delegated to PhaseRouter)."""
        if not plan:
            return False, ""
        return self._phase_router.should_skip_step(plan, step)

    # ── Failure Handling ───────────────────────────────────────────────

    def handle_step_failure(self, plan: Plan | None, failed_step: Step) -> list[str]:
        """Handle step failure by marking dependent steps as blocked."""
        if not plan:
            return []
        return self._step_failure_handler.handle_failure(plan, failed_step)

    def check_and_skip_steps(self, plan: Plan | None) -> list[str]:
        """Check all pending steps and skip those that should be skipped."""
        if not plan:
            return []
        return self._step_failure_handler.check_and_skip_steps(plan)
