"""Skill discovery and loading tools bridging to the vendored SkillsLoader.

Provides two tools:
- ListSkillsTool: Lists all available skills with names, descriptions, and sources.
- ReadSkillTool: Reads the full markdown instructions of a specific skill by name.

Both tools depend on a SkillLoaderProtocol abstraction so the domain layer
never imports vendored infrastructure directly.
"""

import logging
from typing import Any, Protocol

from app.domain.models.tool_result import ToolResult
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool

logger = logging.getLogger(__name__)


class SkillLoaderProtocol(Protocol):
    """Protocol for skill discovery and loading.

    Matches the subset of the vendored SkillsLoader API used by these tools.
    """

    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, Any]]:
        """List available skills.

        Args:
            filter_unavailable: If True, exclude skills with unmet requirements.

        Returns:
            List of dicts with at least 'name', 'path', 'source' keys.
        """
        ...

    def load_skill(self, name: str) -> str | None:
        """Load skill content by name.

        Args:
            name: Skill directory name.

        Returns:
            Skill markdown content or None if not found.
        """
        ...


class ListSkillsTool(BaseTool):
    """Tool for listing all available skills with their descriptions."""

    name: str = "skills"

    def __init__(
        self,
        skill_loader: SkillLoaderProtocol,
        max_observe: int | None = None,
    ) -> None:
        super().__init__(
            max_observe=max_observe,
            defaults=ToolDefaults(is_read_only=True, is_concurrency_safe=True, category="skill"),
        )
        self._skill_loader = skill_loader

    @tool(
        name="list_skills",
        description="List all available skills with their names, sources, and file paths.",
        parameters={},
        required=[],
    )
    async def list_skills(self, **_: Any) -> ToolResult:
        """List all available skills.

        Returns:
            ToolResult with skill listing or empty message.
        """
        try:
            skills = self._skill_loader.list_skills(filter_unavailable=True)
        except Exception as exc:
            logger.warning("Failed to list skills: %s", exc)
            return ToolResult.error(f"Failed to list skills: {exc}")

        if not skills:
            return ToolResult.ok(
                message="No skills are currently available.",
                data={"skills": []},
            )

        lines = [f"Found {len(skills)} available skill(s):\n"]
        for skill in skills:
            name = skill.get("name", "unknown")
            source = skill.get("source", "unknown")
            lines.append(f"- **{name}** (source: {source})")

        return ToolResult.ok(
            message="\n".join(lines),
            data={"skills": skills},
        )


class ReadSkillTool(BaseTool):
    """Tool for reading the full instructions of a skill by name."""

    name: str = "skills"

    def __init__(
        self,
        skill_loader: SkillLoaderProtocol,
        max_observe: int | None = None,
    ) -> None:
        super().__init__(
            max_observe=max_observe,
            defaults=ToolDefaults(is_read_only=True, is_concurrency_safe=True, category="skill"),
        )
        self._skill_loader = skill_loader

    @tool(
        name="read_skill",
        description="Read the full instructions of a skill by name.",
        parameters={
            "skill_name": {
                "type": "string",
                "description": "Name of the skill to read",
            },
        },
        required=["skill_name"],
    )
    async def read_skill(self, skill_name: str, **_: Any) -> ToolResult:
        """Read skill content by name.

        Args:
            skill_name: Name of the skill to load.

        Returns:
            ToolResult with skill content or error.
        """
        if not skill_name or not skill_name.strip():
            return ToolResult.error("skill_name is required and cannot be empty.")

        skill_name = skill_name.strip()

        try:
            content = self._skill_loader.load_skill(skill_name)
        except Exception as exc:
            logger.warning("Failed to load skill '%s': %s", skill_name, exc)
            return ToolResult.error(f"Failed to load skill '{skill_name}': {exc}")

        if content is None:
            # Provide available skills in the error to help the agent self-correct
            try:
                available = self._skill_loader.list_skills(filter_unavailable=True)
                available_names = [s.get("name", "") for s in available]
            except Exception:
                available_names = []

            hint = ""
            if available_names:
                hint = f" Available skills: {', '.join(available_names)}"

            return ToolResult.error(
                f"Skill '{skill_name}' not found.{hint}",
            )

        return ToolResult.ok(
            message=content,
            data={"skill_name": skill_name, "content_length": len(content)},
        )
