"""Skill Creator Tools.

This module provides tools for AI-assisted custom skill creation.
These tools are used by the Skill Creator meta-skill to help users
create custom skills through conversation.
"""

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.domain.models.event import SkillDeliveryEvent, SkillPackageFileData
from app.domain.models.skill import Skill, SkillCategory, SkillSource
from app.domain.models.tool_result import ToolResult
from app.domain.repositories.skill_package_repository import SkillPackageRepository
from app.domain.services.skill_packager import get_skill_packager
from app.domain.services.skill_validator import CustomSkillValidator
from app.domain.services.tools.base import BaseTool, ToolDefaults, tool

logger = logging.getLogger(__name__)


class SkillCreatorTool(BaseTool):
    """Tool for creating custom skills through AI conversation.

    This tool is used by the Skill Creator meta-skill to save
    user-defined custom skills to the database and emit a skill
    delivery event for the frontend to display.
    """

    name: str = "skill_creator"

    def __init__(
        self,
        user_id: str | None = None,
        emit_event: Callable[[Any], None] | None = None,
        skill_package_repo: SkillPackageRepository | None = None,
    ):
        """Initialize the skill creator tool.

        Args:
            user_id: The ID of the user creating skills (required for ownership)
            emit_event: Optional callback to emit events to the frontend
            skill_package_repo: Repository for persisting skill packages.
                When ``None`` the save step is skipped silently.
        """
        super().__init__(
            defaults=ToolDefaults(category="skill"),
        )
        self._user_id = user_id
        self._emit_event = emit_event
        self._skill_package_repo = skill_package_repo

    @tool(
        name="skill_create",
        description="Create a new custom skill with optional bundled files. Use after user has approved the skill definition and you've created supporting files.",
        parameters={
            "name": {
                "type": "string",
                "description": "Display name for the skill (2-100 characters)",
            },
            "description": {
                "type": "string",
                "description": "Brief description of what the skill does (10-500 characters)",
            },
            "icon": {
                "type": "string",
                "description": "Lucide icon name (e.g., sparkles, wand-2, code, pen-tool, search)",
            },
            "required_tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of required tool names",
            },
            "optional_tools": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of optional tool names",
            },
            "system_prompt_addition": {
                "type": "string",
                "description": "System prompt instructions for the skill (the body of SKILL.md)",
            },
            "scripts": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "File name (e.g., seo_analyzer.py)"},
                        "content": {"type": "string", "description": "File content"},
                    },
                },
                "description": "Optional scripts to bundle (placed in scripts/ folder)",
            },
            "references": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "File name (e.g., style_guide.md)"},
                        "content": {"type": "string", "description": "File content"},
                    },
                },
                "description": "Optional reference docs to bundle (placed in references/ folder)",
            },
            "templates": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "filename": {"type": "string", "description": "File name (e.g., blog_outline.md)"},
                        "content": {"type": "string", "description": "File content"},
                    },
                },
                "description": "Optional templates to bundle (placed in templates/ folder)",
            },
        },
        required=["name", "description", "required_tools", "system_prompt_addition"],
    )
    async def skill_create(
        self,
        name: str,
        description: str,
        system_prompt_addition: str,
        required_tools: list[str],
        icon: str = "sparkles",
        optional_tools: list[str] | None = None,
        scripts: list[dict[str, str]] | None = None,
        references: list[dict[str, str]] | None = None,
        templates: list[dict[str, str]] | None = None,
        **kwargs: Any,
    ) -> ToolResult:
        """Create a custom skill with optional bundled files.

        Args:
            name: Display name for the skill
            description: Brief description
            system_prompt_addition: System prompt instructions (SKILL.md body)
            required_tools: Required tool names
            icon: Lucide icon name
            optional_tools: Optional tool names
            scripts: Optional scripts [{filename, content}] for scripts/ folder
            references: Optional references [{filename, content}] for references/ folder
            templates: Optional templates [{filename, content}] for templates/ folder

        Returns:
            ToolResult with success status and skill ID
        """
        if not self._user_id:
            return ToolResult(
                success=False,
                message="Cannot create skill: User ID not available",
            )

        try:
            # Generate skill ID
            slug = name.lower().replace(" ", "-")[:30]
            skill_id = f"custom-{slug}-{str(uuid4())[:8]}"

            # Create skill object
            skill = Skill(
                id=skill_id,
                name=name,
                description=description,
                category=SkillCategory.CUSTOM,
                source=SkillSource.CUSTOM,
                icon=icon or "sparkles",
                required_tools=required_tools or [],
                optional_tools=optional_tools or [],
                system_prompt_addition=system_prompt_addition,
                owner_id=self._user_id,
                is_public=False,
                default_enabled=False,
                version="1.0.0",
                author=self._user_id,
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

            # Validate the skill
            errors = CustomSkillValidator.validate(skill)
            if errors:
                return ToolResult(
                    success=False,
                    message=f"Skill validation failed: {'; '.join(errors)}",
                )

            # Save to database
            from app.application.services.skill_service import get_skill_service

            skill_service = get_skill_service()
            await skill_service.create_skill(skill)

            logger.info(f"Created custom skill {skill_id} for user {self._user_id}")

            # CRITICAL: Invalidate caches so the new skill is immediately usable
            from app.domain.services.skill_registry import invalidate_skill_caches

            await invalidate_skill_caches(skill_id)
            logger.info(f"Invalidated skill caches for {skill_id} - registry and triggers refreshed")

            # Create skill package for delivery with bundled files
            from app.domain.models.skill_package import SkillPackageFile, SkillPackageMetadata

            packager = get_skill_packager()

            # Convert bundled files to SkillPackageFile objects
            script_files = None
            if scripts:
                script_files = [
                    SkillPackageFile.from_content(f"scripts/{s['filename']}", s["content"])
                    for s in scripts
                    if s.get("filename") and s.get("content")
                ]

            reference_files = None
            if references:
                reference_files = [
                    SkillPackageFile.from_content(f"references/{r['filename']}", r["content"])
                    for r in references
                    if r.get("filename") and r.get("content")
                ]

            template_files = None
            if templates:
                template_files = [
                    SkillPackageFile.from_content(f"templates/{t['filename']}", t["content"])
                    for t in templates
                    if t.get("filename") and t.get("content")
                ]

            # Create full package with bundled files
            metadata = SkillPackageMetadata(
                name=name,
                description=description,
                version="1.0.0",
                icon=icon or "sparkles",
                category="custom",
                author=self._user_id,
                required_tools=required_tools or [],
                optional_tools=optional_tools or [],
            )

            package = packager.create_package(
                metadata=metadata,
                workflow_content=system_prompt_addition,
                scripts=script_files,
                references=reference_files,
                templates=template_files,
                skill_id=skill_id,
            )

            # Save package to database for later retrieval
            if self._skill_package_repo is not None:
                try:
                    package_doc = {
                        "id": package.id,
                        "name": package.name,
                        "description": package.description,
                        "version": package.version,
                        "icon": package.icon,
                        "category": package.category,
                        "author": package.author,
                        "skill_id": skill_id,
                        "file_tree": package.file_tree,
                        "files": [
                            {"path": f.path, "content": f.content, "size": f.size, "file_type": f.file_type}
                            for f in package.files
                        ],
                        "file_id": package.file_id,
                        "created_at": datetime.now(UTC),
                    }
                    await self._skill_package_repo.save_package(package_doc)
                except Exception as e:
                    logger.warning(f"Failed to save skill package to database: {e}")

            # Emit skill delivery event if callback provided
            if self._emit_event:
                delivery_event = SkillDeliveryEvent(
                    package_id=package.id,
                    name=package.name,
                    description=package.description,
                    version=package.version,
                    icon=package.icon,
                    category=package.category,
                    author=package.author,
                    file_tree=package.file_tree,
                    files=[
                        SkillPackageFileData(
                            path=f.path,
                            content=f.content,
                            size=f.size,
                        )
                        for f in package.files
                    ],
                    file_id=package.file_id,
                    skill_id=skill_id,
                )
                self._emit_event(delivery_event)
                logger.info(f"Emitted skill delivery event for {skill_id}")

            return ToolResult(
                success=True,
                message=f"Created custom skill '{name}' successfully! Skill ID: {skill_id}",
                data={
                    "skill_id": skill_id,
                    "package_id": package.id,
                    "name": name,
                    "description": description,
                    "file_count": package.file_count,
                },
            )

        except Exception as e:
            logger.error(f"Failed to create skill: {e}")
            return ToolResult(
                success=False,
                message=f"Failed to create skill: {e!s}",
            )


class SkillListTool(BaseTool):
    """Tool for listing user's custom skills."""

    name: str = "skill_list"

    def __init__(self, user_id: str | None = None):
        super().__init__(
            defaults=ToolDefaults(is_read_only=True, category="skill"),
        )
        self._user_id = user_id

    @tool(
        name="skill_list_user",
        description="List all custom skills created by the current user",
        parameters={},
        required=[],
    )
    async def skill_list_user(self, **kwargs: Any) -> ToolResult:
        """List user's custom skills."""
        if not self._user_id:
            return ToolResult(
                success=False,
                message="Cannot list skills: User ID not available",
            )

        try:
            from app.application.services.skill_service import get_skill_service

            skill_service = get_skill_service()
            skills = await skill_service.get_skills_by_owner(self._user_id)

            if not skills:
                return ToolResult(
                    success=True,
                    message="You haven't created any custom skills yet.",
                    data={"skills": []},
                )

            skill_list = [
                {
                    "id": s.id,
                    "name": s.name,
                    "description": s.description,
                    "is_public": s.is_public,
                }
                for s in skills
            ]

            return ToolResult(
                success=True,
                message=f"Found {len(skills)} custom skill(s):\n"
                + "\n".join(f"- {s['name']}: {s['description']}" for s in skill_list),
                data={"skills": skill_list},
            )

        except Exception as e:
            logger.error(f"Failed to list skills: {e}")
            return ToolResult(
                success=False,
                message=f"Failed to list skills: {e!s}",
            )


class SkillDeleteTool(BaseTool):
    """Tool for deleting custom skills."""

    name: str = "skill_delete"

    def __init__(self, user_id: str | None = None):
        super().__init__(
            defaults=ToolDefaults(is_destructive=True, category="skill"),
        )
        self._user_id = user_id

    @tool(
        name="skill_delete",
        description="Delete a custom skill by ID. Only works for skills owned by the user.",
        parameters={
            "skill_id": {
                "type": "string",
                "description": "The ID of the skill to delete",
            },
        },
        required=["skill_id"],
    )
    async def skill_delete(self, skill_id: str, **kwargs: Any) -> ToolResult:
        """Delete a custom skill."""
        if not self._user_id:
            return ToolResult(
                success=False,
                message="Cannot delete skill: User ID not available",
            )

        try:
            from app.application.services.skill_service import get_skill_service

            skill_service = get_skill_service()

            # Verify skill exists and is owned by user
            skill = await skill_service.get_skill_by_id(skill_id)
            if not skill:
                return ToolResult(
                    success=False,
                    message=f"Skill not found: {skill_id}",
                )

            if skill.owner_id != self._user_id:
                return ToolResult(
                    success=False,
                    message="You don't have permission to delete this skill",
                )

            # Delete the skill
            success = await skill_service.delete_skill(skill_id)
            if not success:
                return ToolResult(
                    success=False,
                    message=f"Failed to delete skill: {skill_id}",
                )

            logger.info(f"Deleted custom skill {skill_id} for user {self._user_id}")

            return ToolResult(
                success=True,
                message=f"Deleted skill '{skill.name}' successfully",
            )

        except Exception as e:
            logger.error(f"Failed to delete skill: {e}")
            return ToolResult(
                success=False,
                message=f"Failed to delete skill: {e!s}",
            )


def get_skill_creator_tools(
    user_id: str | None = None,
    emit_event: Callable[[Any], None] | None = None,
    skill_package_repo: SkillPackageRepository | None = None,
) -> list[BaseTool]:
    """Get all skill creator tools.

    Args:
        user_id: The user ID for ownership tracking
        emit_event: Optional callback to emit events to the frontend
        skill_package_repo: Repository for persisting skill packages.
            When ``None`` the save step is skipped silently.

    Returns:
        List of skill creator tools
    """
    return [
        SkillCreatorTool(user_id=user_id, emit_event=emit_event, skill_package_repo=skill_package_repo),
        SkillListTool(user_id=user_id),
        SkillDeleteTool(user_id=user_id),
    ]
