"""Skill loader with progressive disclosure.

Implements Manus AI's context-efficient skill loading pattern:
- Discovers skills by scanning directories
- Loads only what's needed at each disclosure level
- Caches loaded skills to avoid redundant I/O

Progressive Disclosure Levels:
- Level 1: Metadata only (name, description) - ~100 tokens
- Level 2: Metadata + body (full instructions) - <500 lines
- Level 3: Everything including resources with content
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Protocol

import aiofiles

from app.domain.models.skill import (
    ResourceType,
    Skill,
    SkillCategory,
    SkillMetadata,
    SkillResource,
    SkillSource,
)

logger = logging.getLogger(__name__)


class SkillLoaderProtocol(Protocol):
    """Protocol for skill loading operations.

    Defines the contract for skill loaders to enable
    dependency injection and testing.
    """

    async def discover_skills(self) -> list[Skill]:
        """Discover all available skills (level 1 disclosure)."""
        ...

    async def load_skill(self, name: str, disclosure_level: int = 2) -> Skill | None:
        """Load a skill at the specified disclosure level."""
        ...

    async def load_resource(self, skill_name: str, resource_path: str) -> str | None:
        """Load a specific resource from a skill."""
        ...


class SkillLoader:
    """Loads skills with progressive disclosure.

    Implements Manus AI's context-efficient skill loading:
    - Discovers skills by scanning directories
    - Loads only what's needed at each disclosure level
    - Caches loaded skills to avoid redundant I/O

    Attributes:
        skills_dir: Path to the root skills directory.

    Example:
        loader = SkillLoader(skills_dir="/path/to/skills")
        skills = await loader.discover_skills()  # Level 1 metadata
        full_skill = await loader.load_skill("web-research", disclosure_level=3)
    """

    def __init__(self, skills_dir: Path | str) -> None:
        """Initialize the skill loader.

        Args:
            skills_dir: Path to the directory containing skill subdirectories.
                        Each subdirectory should contain a SKILL.md file.
        """
        self.skills_dir = Path(skills_dir)
        self._cache: dict[str, Skill] = {}

    async def discover_skills(self) -> list[Skill]:
        """Discover all available skills (level 1 disclosure).

        Scans the skills directory for subdirectories containing SKILL.md files.
        Returns skills with only metadata populated (name, description).

        Returns:
            List of Skill objects with level 1 disclosure (metadata only).
            Returns empty list if directory doesn't exist or contains no valid skills.
        """
        skills: list[Skill] = []

        if not self.skills_dir.exists():
            logger.warning(f"Skills directory does not exist: {self.skills_dir}")
            return skills

        try:
            # Scan for skill directories
            for item in self.skills_dir.iterdir():
                if not item.is_dir():
                    continue

                skill_md_path = item / "SKILL.md"
                if not skill_md_path.exists():
                    logger.debug(f"Skipping {item.name}: no SKILL.md found")
                    continue

                try:
                    skill = await self._load_skill_at_level(item.name, 1)
                    if skill:
                        skills.append(skill)
                except Exception as e:
                    logger.warning(f"Failed to load skill {item.name}: {e}")
                    continue

        except Exception as e:
            logger.error(f"Error scanning skills directory: {e}")

        logger.info(f"Discovered {len(skills)} skills in {self.skills_dir}")
        return skills

    async def load_skill(self, name: str, disclosure_level: int = 2) -> Skill | None:
        """Load a skill at the specified disclosure level.

        Progressive disclosure levels:
        - Level 1: Metadata only (name, description, category, etc.)
        - Level 2: Metadata + body (full instructions from SKILL.md)
        - Level 3: Everything including resources with content loaded

        Args:
            name: The skill name/identifier (directory name).
            disclosure_level: The disclosure level (1, 2, or 3). Default is 2.

        Returns:
            Skill object at the requested disclosure level, or None if not found.
        """
        cache_key = f"{name}:{disclosure_level}"

        # Check cache first
        if cache_key in self._cache:
            logger.debug(f"Cache hit for skill: {cache_key}")
            return self._cache[cache_key]

        skill = await self._load_skill_at_level(name, disclosure_level)

        if skill:
            self._cache[cache_key] = skill
            logger.debug(f"Cached skill: {cache_key}")

        return skill

    async def _load_skill_at_level(self, name: str, disclosure_level: int) -> Skill | None:
        """Internal method to load a skill at a specific level.

        Args:
            name: The skill name/identifier.
            disclosure_level: The disclosure level (1, 2, or 3).

        Returns:
            Skill object or None if not found or invalid.
        """
        skill_path = self.skills_dir / name
        skill_md_path = skill_path / "SKILL.md"

        if not skill_md_path.exists():
            logger.debug(f"Skill not found: {name}")
            return None

        try:
            # Read SKILL.md content
            async with aiofiles.open(skill_md_path, encoding="utf-8") as f:
                content = await f.read()

            if not content.strip():
                logger.warning(f"Empty SKILL.md for skill: {name}")
                return None

            # Parse metadata from frontmatter
            try:
                metadata = SkillMetadata.from_yaml(content)
            except ValueError as e:
                logger.warning(f"Invalid frontmatter in {name}/SKILL.md: {e}")
                return None

            # Extract body (everything after frontmatter)
            match = re.match(r"^---\n.*?\n---\n*", content, re.DOTALL)
            body = content[match.end() :].strip() if match else ""

            # Build skill based on disclosure level
            skill_body = "" if disclosure_level < 2 else body
            resources: list[SkillResource] = []

            if disclosure_level >= 3:
                resources = await self._load_resources(skill_path)

            return Skill(
                id=metadata.name or name,
                name=metadata.name or name,
                description=metadata.description,
                category=SkillCategory.CUSTOM,
                source=SkillSource.CUSTOM,
                body=skill_body,
                resources=resources,
            )

        except Exception as e:
            logger.error(f"Error loading skill {name}: {e}")
            return None

    async def _load_resources(self, skill_path: Path) -> list[SkillResource]:
        """Load all bundled resources from a skill directory.

        Scans scripts/, references/, and templates/ directories
        and loads their contents.

        Args:
            skill_path: Path to the skill directory.

        Returns:
            List of SkillResource objects with content loaded.
        """
        resources: list[SkillResource] = []

        resource_dirs = {
            "scripts": ResourceType.SCRIPT,
            "references": ResourceType.REFERENCE,
            "templates": ResourceType.TEMPLATE,
        }

        for dir_name, resource_type in resource_dirs.items():
            dir_path = skill_path / dir_name
            if not dir_path.exists():
                continue

            # Recursively find all files
            found_resources = await self._scan_resource_dir(dir_path, dir_name, resource_type)
            resources.extend(found_resources)

        logger.debug(f"Loaded {len(resources)} resources from {skill_path.name}")
        return resources

    async def _scan_resource_dir(
        self, dir_path: Path, base_path: str, resource_type: ResourceType
    ) -> list[SkillResource]:
        """Recursively scan a resource directory for files.

        Args:
            dir_path: Path to the resource directory.
            base_path: Base path prefix for relative paths (e.g., "scripts").
            resource_type: The type of resources in this directory.

        Returns:
            List of SkillResource objects with content loaded.
        """
        resources: list[SkillResource] = []

        try:
            for item in dir_path.iterdir():
                if item.is_file():
                    try:
                        async with aiofiles.open(item, encoding="utf-8") as f:
                            content = await f.read()

                        relative_path = f"{base_path}/{item.name}"
                        description = self._generate_resource_description(item.name, resource_type)

                        resources.append(
                            SkillResource(
                                type=resource_type,
                                path=relative_path,
                                description=description,
                                content=content,
                            )
                        )
                    except Exception as e:
                        logger.warning(f"Failed to read resource {item}: {e}")

                elif item.is_dir():
                    # Recurse into subdirectories
                    sub_path = f"{base_path}/{item.name}"
                    sub_resources = await self._scan_resource_dir(item, sub_path, resource_type)
                    resources.extend(sub_resources)

        except Exception as e:
            logger.error(f"Error scanning resource directory {dir_path}: {e}")

        return resources

    def _generate_resource_description(self, filename: str, resource_type: ResourceType) -> str:
        """Generate a description for a resource based on its type and name.

        Args:
            filename: The name of the resource file.
            resource_type: The type of resource.

        Returns:
            A descriptive string for the resource.
        """
        base_name = Path(filename).stem

        descriptions = {
            ResourceType.SCRIPT: f"Executable script: {base_name}",
            ResourceType.REFERENCE: f"Reference documentation: {base_name}",
            ResourceType.TEMPLATE: f"Output template: {base_name}",
        }

        return descriptions.get(resource_type, f"Resource: {base_name}")

    async def load_resource(self, skill_name: str, resource_path: str) -> str | None:
        """Load a specific resource from a skill.

        Enables on-demand loading of individual resources without
        loading the entire skill at level 3.

        Args:
            skill_name: The skill name/identifier.
            resource_path: Relative path to the resource within the skill
                          (e.g., "references/api.md").

        Returns:
            The resource content as a string, or None if not found.
        """
        skill_path = self.skills_dir / skill_name
        full_path = skill_path / resource_path

        # Security: prevent path traversal
        try:
            resolved = full_path.resolve()
            skill_resolved = skill_path.resolve()
            if not str(resolved).startswith(str(skill_resolved) + "/") and resolved != skill_resolved:
                logger.warning(f"Path traversal attempt blocked: {resource_path}")
                return None
        except (OSError, ValueError):
            return None

        if not full_path.exists():
            logger.debug(f"Resource not found: {skill_name}/{resource_path}")
            return None

        try:
            async with aiofiles.open(full_path, encoding="utf-8") as f:
                content = await f.read()
            logger.debug(f"Loaded resource: {skill_name}/{resource_path}")
            return content
        except Exception as e:
            logger.error(f"Error loading resource {skill_name}/{resource_path}: {e}")
            return None

    def clear_cache(self) -> None:
        """Clear the skill cache.

        Use when skills have been modified externally or when
        memory needs to be reclaimed.
        """
        self._cache.clear()
        logger.debug("Skill cache cleared")

    def invalidate_skill(self, skill_name: str) -> None:
        """Invalidate cache entries for a specific skill.

        Args:
            skill_name: The skill name to invalidate.
        """
        keys_to_remove = [k for k in self._cache if k.startswith(f"{skill_name}:")]
        for key in keys_to_remove:
            del self._cache[key]
        logger.debug(f"Invalidated cache for skill: {skill_name}")
