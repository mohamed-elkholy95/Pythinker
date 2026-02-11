"""Role-scoped memory access for agents.

Each agent role (planner, executor, researcher) gets a filtered view
of the memory store, retrieving only memory types relevant to their role.
This prevents information overload and improves context quality.
"""

import logging
from typing import TYPE_CHECKING

from app.domain.models.long_term_memory import MemoryType

if TYPE_CHECKING:
    from app.domain.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

# Role-specific memory type filters
ROLE_MEMORY_TYPES: dict[str, list[MemoryType]] = {
    "planner": [
        MemoryType.TASK_OUTCOME,
        MemoryType.ERROR_PATTERN,
        MemoryType.PROCEDURE,
        MemoryType.PROJECT_CONTEXT,
    ],
    "executor": [
        MemoryType.PROCEDURE,
        MemoryType.FACT,
        MemoryType.PROJECT_CONTEXT,
        MemoryType.ERROR_PATTERN,
    ],
    "researcher": [
        MemoryType.FACT,
        MemoryType.ENTITY,
        MemoryType.PROJECT_CONTEXT,
    ],
    "reflector": [
        MemoryType.TASK_OUTCOME,
        MemoryType.ERROR_PATTERN,
        MemoryType.PREFERENCE,
    ],
}

# Token budget for memory context injection
MAX_MEMORY_CONTEXT_TOKENS = 500


class RoleScopedMemory:
    """Provides role-specific memory access patterns.

    Wraps MemoryService with role-based filtering to give each agent
    only the memories most relevant to their function.
    """

    def __init__(
        self,
        memory_service: "MemoryService",
        role: str,
        user_id: str,
    ) -> None:
        self._service = memory_service
        self._role = role
        self._user_id = user_id

    async def get_context(self, task_description: str, limit: int = 10) -> str:
        """Get role-appropriate memories formatted for context injection.

        Args:
            task_description: Current task for semantic matching
            limit: Max memories to retrieve

        Returns:
            Formatted memory context string (token-budgeted)
        """
        try:
            types = ROLE_MEMORY_TYPES.get(self._role, list(MemoryType))

            memories = await self._service.retrieve_relevant(
                user_id=self._user_id,
                context=task_description,
                memory_types=types,
                limit=limit,
            )

            if not memories:
                return ""

            return await self._service.format_memories_for_context(memories)

        except Exception:
            logger.warning("Role-scoped memory retrieval failed for %s", self._role, exc_info=True)
            return ""

    async def get_error_patterns(self, context: str, limit: int = 3) -> str:
        """Get relevant error patterns for the current context.

        Args:
            context: Current task/tool context
            limit: Max error patterns to retrieve

        Returns:
            Formatted error pattern warnings
        """
        try:
            memories = await self._service.retrieve_relevant(
                user_id=self._user_id,
                context=context,
                memory_types=[MemoryType.ERROR_PATTERN],
                limit=limit,
            )

            if not memories:
                return ""

            lines = ["Known issues to watch for:"]
            lines.extend(f"- {mem.memory.content}" for mem in memories)

            return "\n".join(lines)

        except Exception:
            logger.debug("Error pattern retrieval failed", exc_info=True)
            return ""

    async def get_user_preferences(self, limit: int = 5) -> str:
        """Get user preferences for context injection.

        Returns:
            Formatted user preferences
        """
        try:
            memories = await self._service.retrieve_relevant(
                user_id=self._user_id,
                context="user preferences and working style",
                memory_types=[MemoryType.PREFERENCE],
                limit=limit,
            )

            if not memories:
                return ""

            lines = ["User preferences:"]
            lines.extend(f"- {mem.memory.content}" for mem in memories)

            return "\n".join(lines)

        except Exception:
            logger.debug("Preference retrieval failed", exc_info=True)
            return ""

    @property
    def role(self) -> str:
        """Get the role this memory scope is for."""
        return self._role

    @property
    def user_id(self) -> str:
        """Get the user ID."""
        return self._user_id
