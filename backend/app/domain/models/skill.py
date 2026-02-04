"""Skill domain models for prepackaged agent capabilities.

Inspired by Claude Code's skills architecture:
- Skills = Prompt Template + Context Injection + Execution Context Modification
- Meta-tool pattern for dynamic skill invocation
- Support for both user-invoked and AI-invoked skills

Enhanced with Manus AI's progressive disclosure pattern:
- Level 1: Metadata only (name, description)
- Level 2: Metadata + body (full instructions)
- Level 3: Everything including resources
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from enum import Enum
from typing import TYPE_CHECKING, Any

import yaml
from pydantic import BaseModel, Field

if TYPE_CHECKING:
    pass


class ResourceType(str, Enum):
    """Types of skill resources for progressive disclosure."""

    SCRIPT = "script"  # Executable scripts bundled with the skill
    REFERENCE = "reference"  # Reference documentation
    TEMPLATE = "template"  # Templates for output generation


class SkillCategory(str, Enum):
    """Categories for organizing skills."""

    RESEARCH = "research"
    CODING = "coding"
    BROWSER = "browser"
    FILE_MANAGEMENT = "file_management"
    DATA_ANALYSIS = "data_analysis"
    COMMUNICATION = "communication"
    CUSTOM = "custom"


class SkillSource(str, Enum):
    """Source type for skills."""

    OFFICIAL = "official"  # Built-in skills
    COMMUNITY = "community"  # Shared by users
    CUSTOM = "custom"  # User-created


class SkillInvocationType(str, Enum):
    """Controls how a skill can be invoked.

    Based on Claude Code's frontmatter configuration pattern.
    """

    USER = "user"  # Only user can invoke via /skill-name
    AI = "ai"  # AI decides when to invoke based on context
    BOTH = "both"  # Either user or AI can invoke (default)


class SkillResource(BaseModel):
    """A bundled resource within a skill.

    Resources are loaded on demand based on disclosure level:
    - Level 1-2: Resource metadata only (type, path, description)
    - Level 3: Full content loaded
    """

    type: ResourceType
    path: str = Field(..., description="Relative path within skill directory")
    description: str = Field(..., description="What this resource contains")
    content: str | None = Field(
        default=None,
        description="Resource content (loaded on demand at level 3)",
    )


class SkillMetadata(BaseModel):
    """Skill metadata parsed from YAML frontmatter in SKILL.md files.

    Follows Manus AI's skill file format:
    ---
    name: skill-name
    description: What the skill does.
    ---
    """

    name: str = Field(default="", description="Skill identifier/slug")
    description: str = Field(default="", description="Brief skill description")

    @classmethod
    def from_yaml(cls, content: str) -> SkillMetadata:
        """Parse YAML frontmatter from SKILL.md content.

        Args:
            content: Full SKILL.md file content with YAML frontmatter.

        Returns:
            SkillMetadata with parsed name and description.

        Raises:
            ValueError: If no YAML frontmatter is found.
        """
        # Match frontmatter including empty case (---\n---)
        match = re.match(r"^---\n(.*?)\n?---", content, re.DOTALL)
        if not match:
            raise ValueError("No YAML frontmatter found")

        yaml_content = match.group(1)
        data = yaml.safe_load(yaml_content) or {}

        return cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
        )


class Skill(BaseModel):
    """Prepackaged capability for agents.

    Skills are collections of tools, prompts, and configurations
    that enhance the agent's abilities for specific tasks.
    """

    id: str = Field(..., description="Unique skill identifier (slug)")
    name: str = Field(..., description="Display name")
    description: str = Field(..., description="What this skill does")
    category: SkillCategory
    source: SkillSource = SkillSource.CUSTOM  # Default to CUSTOM for safety
    icon: str = Field(default="sparkles", description="Lucide icon name")

    # Tool integration
    required_tools: list[str] = Field(
        default_factory=list,
        description="Tool names this skill requires",
    )
    optional_tools: list[str] = Field(
        default_factory=list,
        description="Tools that enhance this skill",
    )

    # Prompt enhancement
    system_prompt_addition: str | None = Field(
        default=None,
        description="Added to agent system prompt when enabled",
    )

    # Configuration schema
    configurations: dict[str, dict] = Field(
        default_factory=dict,
        description="Skill-specific settings schema",
    )
    default_enabled: bool = Field(default=False)

    # Claude-style invocation configuration
    invocation_type: SkillInvocationType = Field(
        default=SkillInvocationType.BOTH,
        description="Controls who can invoke this skill (user, ai, or both)",
    )

    # Tool restrictions (Claude-style allowed_tools pattern)
    allowed_tools: list[str] | None = Field(
        default=None,
        description="If set, restricts the agent to only these tools when skill is active",
    )

    # Dynamic context injection (Claude-style !command syntax)
    supports_dynamic_context: bool = Field(
        default=False,
        description="Whether system_prompt_addition supports !command substitution",
    )

    # Trigger patterns for automatic activation (Claude-style skill triggers)
    trigger_patterns: list[str] = Field(
        default_factory=list,
        description="Regex patterns that trigger this skill automatically",
    )

    # Metadata
    version: str = Field(default="1.0.0")
    author: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    # Premium/feature flags
    is_premium: bool = Field(default=False)

    # Custom skill ownership (Phase 1: Custom Skills)
    owner_id: str | None = Field(
        default=None,
        description="User ID who created this custom skill",
    )
    is_public: bool = Field(
        default=False,
        description="Whether this custom skill is shared with the community",
    )
    parent_skill_id: str | None = Field(
        default=None,
        description="ID of the skill this was derived from (for templates)",
    )

    # Marketplace features (Phase 2: Skill Marketplace)
    community_rating: float = Field(
        default=0.0,
        description="Average community rating (1-5 scale)",
    )
    rating_count: int = Field(
        default=0,
        description="Number of ratings received",
    )
    install_count: int = Field(
        default=0,
        description="Number of times this skill has been installed",
    )
    is_featured: bool = Field(
        default=False,
        description="Whether this skill is featured in the marketplace",
    )
    tags: list[str] = Field(
        default_factory=list,
        description="Searchable tags for discovery",
    )

    # Progressive Disclosure Fields (Manus AI pattern)
    body: str = Field(
        default="",
        description="Full instructions from SKILL.md (disclosed at level 2+)",
    )
    resources: list[SkillResource] = Field(
        default_factory=list,
        description="Bundled resources (disclosed at level 3)",
    )

    def get_disclosure_level(self, level: int) -> dict[str, Any]:
        """Get skill data at the specified disclosure level.

        Progressive disclosure pattern from Manus AI:
        - Level 1: Metadata only (name, description, category, etc.)
        - Level 2: Metadata + body (full instructions)
        - Level 3: Everything including resources with content

        Args:
            level: Disclosure level (1, 2, or 3).

        Returns:
            Dictionary with skill data appropriate for the level.

        Raises:
            ValueError: If level is not 1, 2, or 3.
        """
        if level not in (1, 2, 3):
            raise ValueError(f"Invalid disclosure level: {level}. Must be 1, 2, or 3.")

        # Level 1: Metadata only
        result: dict[str, Any] = {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "category": self.category.value,
            "source": self.source.value,
            "icon": self.icon,
            "version": self.version,
            "tags": self.tags,
        }

        if level >= 2:
            # Level 2: Add body
            result["body"] = self.body
            result["system_prompt_addition"] = self.system_prompt_addition
            result["required_tools"] = self.required_tools
            result["optional_tools"] = self.optional_tools

        if level >= 3:
            # Level 3: Add resources
            result["resources"] = [
                {
                    "type": r.type.value,
                    "path": r.path,
                    "description": r.description,
                    "content": r.content,
                }
                for r in self.resources
            ]

        return result

    @classmethod
    def from_skill_md(
        cls,
        content: str,
        category: SkillCategory,
        resources: list[SkillResource] | None = None,
        **kwargs: Any,
    ) -> Skill:
        """Create a Skill from SKILL.md file content.

        Parses YAML frontmatter for metadata and extracts body content.

        Args:
            content: Full SKILL.md file content with YAML frontmatter.
            category: Category for the skill.
            resources: Optional list of bundled resources.
            **kwargs: Additional fields to pass to Skill constructor.

        Returns:
            Skill instance populated from the SKILL.md content.

        Raises:
            ValueError: If no YAML frontmatter is found.
        """
        # Parse metadata from frontmatter
        metadata = SkillMetadata.from_yaml(content)

        # Extract body (everything after frontmatter)
        match = re.match(r"^---\n.*?\n---\n*", content, re.DOTALL)
        body = content[match.end() :].strip() if match else content.strip()

        return cls(
            id=metadata.name,
            name=metadata.name,
            description=metadata.description,
            category=category,
            body=body,
            resources=resources or [],
            **kwargs,
        )


class UserSkillConfig(BaseModel):
    """User's configuration for a specific skill."""

    skill_id: str
    enabled: bool = True
    config: dict = Field(default_factory=dict)  # Skill-specific settings
    order: int = 0  # Display/priority order
