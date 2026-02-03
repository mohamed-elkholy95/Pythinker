"""Skill domain models for prepackaged agent capabilities.

Inspired by Claude Code's skills architecture:
- Skills = Prompt Template + Context Injection + Execution Context Modification
- Meta-tool pattern for dynamic skill invocation
- Support for both user-invoked and AI-invoked skills
"""

from datetime import UTC, datetime
from enum import Enum

from pydantic import BaseModel, Field


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


class UserSkillConfig(BaseModel):
    """User's configuration for a specific skill."""

    skill_id: str
    enabled: bool = True
    config: dict = Field(default_factory=dict)  # Skill-specific settings
    order: int = 0  # Display/priority order
