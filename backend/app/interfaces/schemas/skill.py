"""Schemas for skill-related API requests and responses."""

from datetime import datetime

from pydantic import BaseModel, Field


class SkillResponse(BaseModel):
    """Response schema for a skill."""

    id: str
    name: str
    description: str
    category: str
    source: str
    icon: str
    required_tools: list[str] = []
    optional_tools: list[str] = []
    is_premium: bool = False
    default_enabled: bool = False
    version: str = "1.0.0"
    author: str | None = None
    updated_at: datetime
    # Custom skill fields
    owner_id: str | None = None
    is_public: bool = False
    parent_skill_id: str | None = None
    system_prompt_addition: str | None = None  # Included for custom skill editing
    # Claude-style configuration fields
    invocation_type: str = "both"  # user, ai, or both
    allowed_tools: list[str] | None = None  # Tool restrictions
    supports_dynamic_context: bool = False  # !command syntax support
    trigger_patterns: list[str] = []  # Auto-activation patterns
    # Marketplace fields (Phase 2)
    community_rating: float = 0.0  # Average rating (1-5)
    rating_count: int = 0  # Number of ratings
    install_count: int = 0  # Number of installations
    is_featured: bool = False  # Featured in marketplace
    tags: list[str] = []  # Searchable tags


class UserSkillResponse(BaseModel):
    """Response schema for a user's skill configuration."""

    skill: SkillResponse
    enabled: bool
    config: dict = Field(default_factory=dict)
    order: int = 0


class SkillListResponse(BaseModel):
    """Response schema for list of skills."""

    skills: list[SkillResponse]
    total: int


class UserSkillsResponse(BaseModel):
    """Response schema for user's skills configuration."""

    skills: list[UserSkillResponse]
    enabled_count: int
    max_skills: int = 5


class UpdateUserSkillRequest(BaseModel):
    """Request schema for updating a user's skill configuration."""

    enabled: bool | None = None
    config: dict | None = None
    order: int | None = None


class EnableSkillsRequest(BaseModel):
    """Request schema for enabling multiple skills at once."""

    skill_ids: list[str] = Field(..., max_length=5, description="List of skill IDs to enable (max 5)")


class SkillToolsResponse(BaseModel):
    """Response schema for skill tools."""

    skill_ids: list[str]
    tools: list[str]


# Custom Skill CRUD Schemas (Phase 2)


class CreateCustomSkillRequest(BaseModel):
    """Request schema for creating a custom skill."""

    name: str = Field(..., min_length=2, max_length=100, description="Display name for the skill")
    description: str = Field(..., min_length=10, max_length=500, description="Brief description of what the skill does")
    category: str = Field(default="custom", description="Skill category")
    icon: str = Field(default="sparkles", description="Lucide icon name")
    required_tools: list[str] = Field(default_factory=list, description="Required tool names")
    optional_tools: list[str] = Field(default_factory=list, description="Optional tool names")
    system_prompt_addition: str = Field(
        ..., min_length=10, max_length=4000, description="System prompt addition for agent guidance"
    )
    # Claude-style configuration (optional for custom skills)
    invocation_type: str = Field(
        default="both",
        description="Who can invoke this skill: 'user', 'ai', or 'both'",
    )
    allowed_tools: list[str] | None = Field(
        default=None,
        description="If set, restricts agent to only these tools when skill is active",
    )
    supports_dynamic_context: bool = Field(
        default=False,
        description="Whether system_prompt_addition supports !command syntax for dynamic content",
    )
    trigger_patterns: list[str] = Field(
        default_factory=list,
        description="Regex patterns that auto-trigger this skill",
    )


class UpdateCustomSkillRequest(BaseModel):
    """Request schema for updating a custom skill."""

    name: str | None = Field(default=None, min_length=2, max_length=100)
    description: str | None = Field(default=None, min_length=10, max_length=500)
    icon: str | None = None
    required_tools: list[str] | None = None
    optional_tools: list[str] | None = None
    system_prompt_addition: str | None = Field(default=None, min_length=10, max_length=4000)
    # Claude-style configuration updates
    invocation_type: str | None = None
    allowed_tools: list[str] | None = None
    supports_dynamic_context: bool | None = None
    trigger_patterns: list[str] | None = None


class CustomSkillListResponse(BaseModel):
    """Response schema for list of custom skills."""

    skills: list[SkillResponse]
    total: int


class PublishSkillRequest(BaseModel):
    """Request schema for publishing a custom skill to community."""

    confirm: bool = Field(..., description="Confirm publishing to community")


# =============================================================================
# SKILL PACKAGE SCHEMAS (for skill delivery)
# =============================================================================


class SkillPackageFileResponse(BaseModel):
    """Response schema for a file in a skill package."""

    path: str = Field(..., description="Relative path within package")
    content: str = Field(..., description="File content")
    size: int = Field(..., description="File size in bytes")


class SkillPackageResponse(BaseModel):
    """Response schema for a skill package."""

    id: str = Field(..., description="Package ID")
    name: str = Field(..., description="Skill name")
    description: str = Field(..., description="Skill description")
    version: str = Field(default="1.0.0", description="Package version")
    icon: str = Field(default="puzzle", description="Lucide icon name")
    category: str = Field(default="custom", description="Skill category")
    author: str | None = Field(default=None, description="Author name")
    file_tree: dict = Field(default_factory=dict, description="Hierarchical file tree")
    files: list[SkillPackageFileResponse] = Field(default_factory=list, description="Package files")
    file_id: str | None = Field(default=None, description="GridFS file ID for download")
    skill_id: str | None = Field(default=None, description="Associated skill ID in database")
    file_count: int = Field(default=0, description="Total number of files")
    created_at: datetime | None = None


class InstallSkillFromPackageRequest(BaseModel):
    """Request schema for installing a skill from a package."""

    enable_after_install: bool = Field(default=True, description="Enable the skill after installation")


class CommandResponse(BaseModel):
    """Response schema for a Superpowers command."""

    command: str = Field(..., description="Command name (without leading slash)")
    skill_id: str = Field(..., description="Skill ID that this command invokes")
    description: str = Field(..., description="Help text for the command")


class CommandListResponse(BaseModel):
    """Response schema for list of available commands."""

    commands: list[CommandResponse] = Field(default_factory=list, description="Available commands")
    count: int = Field(..., description="Total number of commands")


class CommandMapResponse(BaseModel):
    """Response schema for command/alias -> skill_id mapping.

    Used by frontend to identify slash commands in chat input.
    Keys are command names (lowercase, no leading slash), values are skill_ids.
    """

    command_map: dict[str, str] = Field(
        default_factory=dict,
        description="Mapping of command/alias -> skill_id for slash command detection",
    )
