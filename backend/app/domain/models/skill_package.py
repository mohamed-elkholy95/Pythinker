"""Skill package domain models.

This module defines models for skill packages - deliverable artifacts that
contain skill definitions with supporting files (scripts, references, templates).

Implements Pythinker-style SKILL.md format with:
- YAML frontmatter (name, description, category, required_tools)
- Goal section
- Workflow section
- Feature ↔ User Value mappings
- Four-layer implementation (Structure, Information, Visual, Interaction)
- Examples section
"""

from datetime import UTC, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class SkillPackageType(str, Enum):
    """Type of skill package."""

    SIMPLE = "simple"  # Basic skill with just prompt
    STANDARD = "standard"  # Standard with workflow
    ADVANCED = "advanced"  # Full Pythinker-style with layers


class SkillFeatureMapping(BaseModel):
    """Feature to User Value mapping from Pythinker SKILL.md format."""

    feature: str  # e.g., "Bar/Column Chart"
    user_value: str  # e.g., "See comparisons at a glance"
    when_to_use: str  # e.g., "Comparing values across categories"


class SkillFeatureCategory(BaseModel):
    """Category of features grouped by user need."""

    category: str  # e.g., "Help Users「Understand Data」"
    mappings: list[SkillFeatureMapping] = Field(default_factory=list)


class SkillWorkflowStep(BaseModel):
    """A step in the skill workflow."""

    step_number: int
    description: str
    substeps: list[str] = Field(default_factory=list)


class SkillExample(BaseModel):
    """Example usage of the skill."""

    title: str
    description: str
    input_example: str | None = None
    output_example: str | None = None
    code_snippet: str | None = None


class SkillImplementationLayer(BaseModel):
    """Implementation layer from Pythinker four-layer structure."""

    name: str  # e.g., "Structure", "Information", "Visual", "Interaction"
    goal: str  # Layer goal
    guidelines: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    code_examples: list[str] = Field(default_factory=list)


class SkillPackageFile(BaseModel):
    """A file within a skill package."""

    path: str  # Relative path: "SKILL.md", "scripts/seo_analyzer.py"
    content: str  # File content (text)
    size: int  # Size in bytes
    file_type: str = "text"  # text, binary, python, markdown

    @classmethod
    def from_content(cls, path: str, content: str) -> "SkillPackageFile":
        """Create a file from path and content."""
        # Detect file type from extension
        file_type = "text"
        if path.endswith(".py"):
            file_type = "python"
        elif path.endswith(".md"):
            file_type = "markdown"
        elif path.endswith(".json"):
            file_type = "json"
        elif path.endswith(".yaml") or path.endswith(".yml"):
            file_type = "yaml"

        return cls(
            path=path,
            content=content,
            size=len(content.encode("utf-8")),
            file_type=file_type,
        )


class SkillPackageMetadata(BaseModel):
    """Metadata extracted from SKILL.md YAML frontmatter.

    Supports Pythinker-style SKILL.md format with extended fields.
    """

    name: str
    description: str
    version: str = "1.0.0"
    author: str | None = None
    category: str = "custom"
    icon: str = "puzzle"
    required_tools: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)

    # Pythinker-style extended fields
    goal: str | None = None  # Primary goal of the skill
    core_principle: str | None = None  # Core design principle
    tags: list[str] = Field(default_factory=list)

    # Dependency management
    python_dependencies: list[str] = Field(default_factory=list)  # pip packages
    system_dependencies: list[str] = Field(default_factory=list)  # System tools

    # Feature categories (Pythinker-style "Help Users X" sections)
    feature_categories: list[SkillFeatureCategory] = Field(default_factory=list)

    # Workflow steps
    workflow_steps: list[SkillWorkflowStep] = Field(default_factory=list)

    # Implementation layers (Pythinker four-layer pattern)
    implementation_layers: list[SkillImplementationLayer] = Field(default_factory=list)

    # Examples
    examples: list[SkillExample] = Field(default_factory=list)


class SkillPackage(BaseModel):
    """A deliverable skill package.

    Skill packages are ZIP archives containing:
    - SKILL.md: Main definition with YAML frontmatter
    - requirements.txt: Python dependencies (optional)
    - scripts/: Helper scripts (.py files)
    - references/: Reference documents (.md files)
    - templates/: Template files (.md, .txt files)
    - tools/: Custom tool implementations (optional)
    - examples/: Usage examples (optional)

    Implements Pythinker-style SKILL.md format.
    """

    id: str  # Package ID (UUID)
    name: str
    description: str
    version: str = "1.0.0"
    icon: str = "puzzle"
    category: str = "custom"
    author: str | None = None
    package_type: SkillPackageType = SkillPackageType.STANDARD

    # File management
    files: list[SkillPackageFile] = Field(default_factory=list)
    file_tree: dict[str, Any] = Field(default_factory=dict)  # Hierarchical structure
    file_id: str | None = None  # GridFS file ID for the ZIP archive
    skill_id: str | None = None  # DB skill ID if also saved to database

    # Extended metadata (parsed from SKILL.md)
    metadata: SkillPackageMetadata | None = None

    # Timestamps
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @property
    def filename(self) -> str:
        """Get the package filename with .skill extension."""
        # Sanitize name for filename
        safe_name = self.name.lower().replace(" ", "-")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c == "-")
        return f"{safe_name}.skill"

    @property
    def total_size(self) -> int:
        """Get total size of all files in bytes."""
        return sum(f.size for f in self.files)

    @property
    def file_count(self) -> int:
        """Get total number of files."""
        return len(self.files)

    def get_file(self, path: str) -> SkillPackageFile | None:
        """Get a file by path."""
        for f in self.files:
            if f.path == path:
                return f
        return None

    def get_skill_md(self) -> SkillPackageFile | None:
        """Get the SKILL.md file."""
        return self.get_file("SKILL.md")

    def get_requirements_txt(self) -> SkillPackageFile | None:
        """Get the requirements.txt file if present."""
        return self.get_file("requirements.txt")

    def get_files_in_directory(self, directory: str) -> list[SkillPackageFile]:
        """Get all files within a specific directory.

        Args:
            directory: Directory path (e.g., "scripts", "tools")

        Returns:
            List of files within that directory
        """
        prefix = f"{directory}/" if not directory.endswith("/") else directory
        return [f for f in self.files if f.path.startswith(prefix)]

    def has_directory(self, directory: str) -> bool:
        """Check if package has files in the specified directory."""
        return len(self.get_files_in_directory(directory)) > 0

    @property
    def has_scripts(self) -> bool:
        """Check if package has script files."""
        return self.has_directory("scripts")

    @property
    def has_tools(self) -> bool:
        """Check if package has custom tool implementations."""
        return self.has_directory("tools")

    @property
    def has_examples(self) -> bool:
        """Check if package has example files."""
        return self.has_directory("examples")

    @property
    def has_references(self) -> bool:
        """Check if package has reference documents."""
        return self.has_directory("references")

    @property
    def has_templates(self) -> bool:
        """Check if package has template files."""
        return self.has_directory("templates")

    @property
    def has_requirements(self) -> bool:
        """Check if package has Python dependencies."""
        return self.get_requirements_txt() is not None

    def get_python_scripts(self) -> list[SkillPackageFile]:
        """Get all Python script files."""
        return [f for f in self.files if f.path.endswith(".py")]

    def get_markdown_files(self) -> list[SkillPackageFile]:
        """Get all Markdown files."""
        return [f for f in self.files if f.path.endswith(".md")]

    @property
    def summary(self) -> dict[str, Any]:
        """Get a summary of the package contents."""
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "category": self.category,
            "package_type": self.package_type.value,
            "file_count": self.file_count,
            "total_size": self.total_size,
            "has_scripts": self.has_scripts,
            "has_tools": self.has_tools,
            "has_examples": self.has_examples,
            "has_requirements": self.has_requirements,
            "created_at": self.created_at.isoformat(),
        }
