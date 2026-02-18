"""Skill loader with progressive disclosure.

Implements Pythinker AI's context-efficient skill loading pattern:
- Discovers skills by scanning directories
- Loads only what's needed at each disclosure level
- Caches loaded skills to avoid redundant I/O

AgentSkills standard compliance (Anthropic open standard):
- Uses skills-ref library for SKILL.md parsing and validation
- Skills created here are portable to Claude Code, Cursor, GitHub Copilot, etc.
- Falls back to legacy PyYAML parser for backward compatibility

Progressive Disclosure Levels:
- Level 1: Metadata only (name, description) - ~100 tokens
- Level 2: Metadata + body (full instructions) - <500 lines
- Level 3: Everything including resources with content
"""

from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path
from typing import TYPE_CHECKING, Protocol

import aiofiles

from app.domain.models.skill import (
    ResourceType,
    Skill,
    SkillCategory,
    SkillMetadata,
    SkillResource,
    SkillSource,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Optional skills-ref integration (AgentSkills open standard)
try:
    from skills_ref.parser import parse_frontmatter as _agentskills_parse_frontmatter
    from skills_ref.validator import validate as _agentskills_validate

    _AGENTSKILLS_AVAILABLE = True
    logger.debug("skills-ref library available — AgentSkills standard compliance enabled")
except ImportError:
    _AGENTSKILLS_AVAILABLE = False
    logger.debug("skills-ref not installed — using legacy YAML parser only")


# Maps AgentSkills metadata.category values to Pythinker's SkillCategory enum
_CATEGORY_MAP: dict[str, SkillCategory] = {
    "research": SkillCategory.RESEARCH,
    "coding": SkillCategory.CODING,
    "browser": SkillCategory.BROWSER,
    "file_management": SkillCategory.FILE_MANAGEMENT,
    "file-management": SkillCategory.FILE_MANAGEMENT,
    "data_analysis": SkillCategory.DATA_ANALYSIS,
    "data-analysis": SkillCategory.DATA_ANALYSIS,
    "communication": SkillCategory.COMMUNICATION,
    "custom": SkillCategory.CUSTOM,
}


def _extract_agentskills_fields(meta_dict: dict) -> dict:
    """Extract and normalize AgentSkills frontmatter fields for Pythinker's Skill model.

    Handles the mapping from AgentSkills field names (hyphens allowed) to
    Pythinker's Skill model fields (underscores). Also maps the nested
    ``metadata`` sub-dict (arbitrary key-value pairs) to structured fields.

    AgentSkills frontmatter reference:
      name, description, license, compatibility, allowed-tools,
      metadata.author, metadata.version, metadata.category, metadata.tags

    Args:
        meta_dict: Raw frontmatter dict from skills-ref or PyYAML parser.

    Returns:
        Dict with keys: category, author, version, tags, allowed_tools.
    """
    extra_meta: dict = meta_dict.get("metadata", {}) or {}

    # Category: check metadata sub-dict first, then top-level
    raw_category = extra_meta.get("category") or meta_dict.get("category", "")
    category = _CATEGORY_MAP.get(str(raw_category).lower(), SkillCategory.CUSTOM)

    # Author and version from metadata sub-dict
    author: str | None = extra_meta.get("author") or meta_dict.get("author") or None
    version: str = str(extra_meta.get("version") or meta_dict.get("version") or "1.0.0")

    # Tags: accept list or comma/space-separated string
    raw_tags = extra_meta.get("tags") or meta_dict.get("tags") or []
    if isinstance(raw_tags, str):
        tags: list[str] = [t.strip() for t in re.split(r"[,\s]+", raw_tags) if t.strip()]
    else:
        tags = list(raw_tags)

    # allowed-tools: AgentSkills uses hyphenated key + space-separated pattern string
    # e.g. "Bash(git:*) Read Write" → ["Bash(git:*)", "Read", "Write"]
    raw_tools = meta_dict.get("allowed-tools") or meta_dict.get("allowed_tools") or ""
    if isinstance(raw_tools, str):
        allowed_tools: list[str] = raw_tools.split() if raw_tools.strip() else []
    elif isinstance(raw_tools, list):
        allowed_tools = [str(t) for t in raw_tools]
    else:
        allowed_tools = []

    return {
        "category": category,
        "author": author,
        "version": version,
        "tags": tags,
        "allowed_tools": allowed_tools,
    }


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

    Implements Pythinker AI's context-efficient skill loading:
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

        Uses the AgentSkills standard (skills-ref) for parsing and validation
        when available, with fallback to the legacy PyYAML parser.

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
            # --- AgentSkills non-blocking validation (warnings only) ---
            if _AGENTSKILLS_AVAILABLE:
                await self._run_agentskills_validation(name, skill_path)

            # Read SKILL.md content
            async with aiofiles.open(skill_md_path, encoding="utf-8") as f:
                content = await f.read()

            if not content.strip():
                logger.warning(f"Empty SKILL.md for skill: {name}")
                return None

            # --- Parse frontmatter via AgentSkills standard with fallback ---
            meta_dict, body = await self._parse_frontmatter(name, content)
            if not meta_dict:
                return None

            # Build skill based on disclosure level
            skill_body = "" if disclosure_level < 2 else body
            resources: list[SkillResource] = []

            if disclosure_level >= 3:
                resources = await self._load_resources(skill_path)

            # Map AgentSkills fields to Pythinker Skill model
            skill_name = meta_dict.get("name") or name
            skill_extra = _extract_agentskills_fields(meta_dict)

            return Skill(
                id=skill_name,
                name=skill_name,
                description=meta_dict.get("description", ""),
                category=skill_extra["category"],
                source=SkillSource.CUSTOM,
                body=skill_body,
                resources=resources,
                author=skill_extra["author"],
                version=skill_extra["version"],
                tags=skill_extra["tags"],
                allowed_tools=skill_extra["allowed_tools"] or None,
            )

        except Exception as e:
            logger.error(f"Error loading skill {name}: {e}")
            return None

    async def _run_agentskills_validation(self, name: str, skill_path: Path) -> None:
        """Run AgentSkills standard validation in a thread (non-blocking).

        Logs warnings for any violations without blocking skill loading.
        This ensures all filesystem-loaded skills are standard-compliant.

        Args:
            name: Skill name for log context.
            skill_path: Path to the skill directory.
        """
        try:
            loop = asyncio.get_running_loop()
            errors: list[str] = await loop.run_in_executor(None, _agentskills_validate, skill_path)
            if errors:
                for err in errors:
                    logger.warning(f"[AgentSkills] {name}: {err}")
            else:
                logger.debug(f"[AgentSkills] {name}: passes standard validation")
        except Exception as e:
            logger.debug(f"[AgentSkills] {name}: validation skipped ({e})")

    async def _parse_frontmatter(self, name: str, content: str) -> tuple[dict, str]:
        """Parse SKILL.md frontmatter using skills-ref with PyYAML fallback.

        Tries the AgentSkills standard parser first (strictyaml-based),
        then falls back to Pythinker's legacy PyYAML parser.

        Args:
            name: Skill name for log context.
            content: Full SKILL.md file content.

        Returns:
            Tuple of (metadata_dict, body_str). Returns ({}, "") on failure.
        """
        # --- Primary: AgentSkills standard parser (strictyaml) ---
        if _AGENTSKILLS_AVAILABLE:
            try:
                meta_dict, body = _agentskills_parse_frontmatter(content)
                return meta_dict, body
            except Exception as e:
                logger.debug(f"[AgentSkills] {name}: standard parser failed ({e}), using fallback")

        # --- Fallback: legacy PyYAML parser ---
        try:
            metadata = SkillMetadata.from_yaml(content)
            match = re.match(r"^---\n.*?\n---\n*", content, re.DOTALL)
            body = content[match.end() :].strip() if match else ""
            return {"name": metadata.name, "description": metadata.description}, body
        except ValueError as e:
            logger.warning(f"Invalid frontmatter in {name}/SKILL.md: {e}")
            return {}, ""

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

        # Security: prevent path traversal and eliminate TOCTOU race.
        # We resolve once, check containment, then open the *resolved* path —
        # this means even a symlink swap between check and open is safe because
        # we always open the path we already validated.
        try:
            resolved = full_path.resolve()
            skill_resolved = skill_path.resolve()
            if not str(resolved).startswith(str(skill_resolved) + "/") and resolved != skill_resolved:
                logger.warning(f"Path traversal attempt blocked: {resource_path}")
                return None
        except (OSError, ValueError):
            return None

        if not resolved.exists():
            logger.debug(f"Resource not found: {skill_name}/{resource_path}")
            return None

        try:
            # Open the resolved (canonical) path, not the original, to eliminate
            # the TOCTOU window between the containment check and the open call.
            async with aiofiles.open(resolved, encoding="utf-8") as f:
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
