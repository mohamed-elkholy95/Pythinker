"""Coordinator helpers for worker context injection and allowlists."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class WorkerSkillContext:
    skill_ids: list[str]
    prompt_addition: str | None
    allowed_tools: list[str] | None

    def has_tool_restrictions(self) -> bool:
        return bool(self.allowed_tools)


async def build_worker_skill_context(
    worker: Any,
    skill_ids: list[str],
    *,
    base_system_prompt: str,
    execution_system_prompt: str,
) -> WorkerSkillContext | None:
    """Load worker skill context and apply prompt/tool allowlists."""
    if not skill_ids:
        return None

    from app.domain.services.skill_registry import get_skill_registry

    registry = await get_skill_registry()
    await registry._ensure_fresh()
    skill_context = await registry.build_context(skill_ids, expand_dynamic=True)

    if skill_context.prompt_addition:
        worker.system_prompt = base_system_prompt + execution_system_prompt + skill_context.prompt_addition

    allowed_tools = None
    if skill_context.has_tool_restrictions():
        allowed_tools = list(skill_context.allowed_tools)
        worker.tools = [tool for tool in worker.tools if tool.name in allowed_tools]

    logger.info(
        "Coordinator applied worker context: skills=%s, tool_restrictions=%s",
        skill_context.skill_ids,
        allowed_tools,
    )
    return WorkerSkillContext(
        skill_ids=list(skill_context.skill_ids),
        prompt_addition=skill_context.prompt_addition,
        allowed_tools=allowed_tools,
    )
