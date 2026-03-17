"""Tests for Skill model with progressive disclosure pattern.

Tests the enhancement of the Skill model with Pythinker AI's progressive disclosure pattern,
including SkillMetadata parsing, SkillResource bundling, and disclosure levels.
"""

import pytest

from app.domain.exceptions.base import BusinessRuleViolation
from app.domain.models.skill import (
    ResourceType,
    Skill,
    SkillCategory,
    SkillMetadata,
    SkillResource,
)


class TestSkillMetadata:
    """Tests for SkillMetadata YAML frontmatter parsing."""

    def test_skill_metadata_parsing(self):
        """Test parsing YAML frontmatter from SKILL.md content."""
        yaml_content = """---
name: excel-generator
description: Generate professional Excel spreadsheets with consistent styling.
---

# Excel Generator

Instructions here...
"""
        metadata = SkillMetadata.from_yaml(yaml_content)
        assert metadata.name == "excel-generator"
        assert "Excel" in metadata.description

    def test_skill_metadata_parsing_multiline_description(self):
        """Test parsing YAML with multiline description."""
        yaml_content = """---
name: research-assistant
description: |
  A comprehensive research assistant that helps with
  gathering information and synthesizing findings.
---

# Research Assistant
"""
        metadata = SkillMetadata.from_yaml(yaml_content)
        assert metadata.name == "research-assistant"
        assert "comprehensive" in metadata.description
        assert "synthesizing" in metadata.description

    def test_skill_metadata_missing_frontmatter_raises(self):
        """Test that missing frontmatter raises BusinessRuleViolation."""
        content = """# No Frontmatter

Just some content without YAML.
"""
        with pytest.raises(BusinessRuleViolation, match="No YAML frontmatter found"):
            SkillMetadata.from_yaml(content)

    def test_skill_metadata_empty_frontmatter(self):
        """Test parsing empty frontmatter defaults to empty strings."""
        yaml_content = """---
---

# Empty Frontmatter
"""
        metadata = SkillMetadata.from_yaml(yaml_content)
        assert metadata.name == ""
        assert metadata.description == ""


class TestResourceType:
    """Tests for ResourceType enum."""

    def test_resource_type_values(self):
        """Test ResourceType enum has expected values."""
        assert ResourceType.SCRIPT == "script"
        assert ResourceType.REFERENCE == "reference"
        assert ResourceType.TEMPLATE == "template"

    def test_resource_type_is_string_enum(self):
        """Test ResourceType can be compared to string values."""
        # String enums compare equal to their string values
        assert ResourceType.SCRIPT == "script"
        assert ResourceType.REFERENCE == "reference"
        # Can also access the value directly
        assert ResourceType.SCRIPT.value == "script"


class TestSkillResource:
    """Tests for SkillResource model."""

    def test_skill_resource_creation(self):
        """Test creating a SkillResource."""
        resource = SkillResource(
            type=ResourceType.REFERENCE,
            path="refs/api.md",
            description="API documentation",
        )
        assert resource.type == ResourceType.REFERENCE
        assert resource.path == "refs/api.md"
        assert resource.description == "API documentation"
        assert resource.content is None  # Loaded on demand

    def test_skill_resource_with_content(self):
        """Test SkillResource with loaded content."""
        resource = SkillResource(
            type=ResourceType.SCRIPT,
            path="scripts/run.py",
            description="Runner script",
            content="print('Hello, World!')",
        )
        assert resource.content == "print('Hello, World!')"

    def test_skill_resource_string_type(self):
        """Test SkillResource accepts string type that maps to enum."""
        resource = SkillResource(
            type="template",
            path="templates/report.md",
            description="Report template",
        )
        assert resource.type == ResourceType.TEMPLATE


class TestSkillProgressiveDisclosure:
    """Tests for Skill progressive disclosure pattern."""

    def test_skill_progressive_disclosure(self):
        """Test progressive disclosure levels return appropriate data."""
        skill = Skill(
            id="test-skill",
            name="test-skill",
            description="Test description",
            category=SkillCategory.CUSTOM,
            body="Full instructions here",
            resources=[
                SkillResource(
                    type=ResourceType.REFERENCE,
                    path="refs/api.md",
                    description="API docs",
                ),
                SkillResource(
                    type=ResourceType.SCRIPT,
                    path="scripts/run.py",
                    description="Runner",
                ),
            ],
        )

        # Level 1: Only metadata
        level1 = skill.get_disclosure_level(1)
        assert "name" in level1
        assert "description" in level1
        assert "body" not in level1 or level1.get("body") is None
        assert "resources" not in level1 or level1.get("resources") is None

        # Level 2: Metadata + body
        level2 = skill.get_disclosure_level(2)
        assert level2["name"] == "test-skill"
        assert level2["body"] == "Full instructions here"
        assert "resources" not in level2 or level2.get("resources") is None

        # Level 3: Everything
        level3 = skill.get_disclosure_level(3)
        assert level3["body"] == "Full instructions here"
        assert len(level3["resources"]) == 2
        assert level3["resources"][0]["path"] == "refs/api.md"

    def test_skill_disclosure_level_invalid(self):
        """Test that invalid disclosure levels raise ValueError."""
        skill = Skill(
            id="test-skill",
            name="test-skill",
            description="Test description",
            category=SkillCategory.CUSTOM,
        )

        with pytest.raises(ValueError, match="Invalid disclosure level"):
            skill.get_disclosure_level(0)

        with pytest.raises(ValueError, match="Invalid disclosure level"):
            skill.get_disclosure_level(4)

    def test_skill_with_empty_body(self):
        """Test skill with empty body."""
        skill = Skill(
            id="minimal-skill",
            name="minimal-skill",
            description="Minimal skill",
            category=SkillCategory.CUSTOM,
        )

        level2 = skill.get_disclosure_level(2)
        assert level2["body"] == ""


class TestSkillFromSkillMd:
    """Tests for Skill.from_skill_md classmethod."""

    def test_from_skill_md_basic(self):
        """Test creating a Skill from SKILL.md content."""
        content = """---
name: excel-generator
description: Generate professional Excel spreadsheets.
---

# Excel Generator

Use this skill to create Excel spreadsheets with consistent styling.

## Usage

Simply describe the spreadsheet you want to create.
"""
        skill = Skill.from_skill_md(content, category=SkillCategory.DATA_ANALYSIS)

        assert skill.id == "excel-generator"
        assert skill.name == "excel-generator"
        assert "Excel" in skill.description
        assert "Use this skill" in skill.body
        assert skill.category == SkillCategory.DATA_ANALYSIS

    def test_from_skill_md_with_resources(self):
        """Test creating a Skill from SKILL.md with resources."""
        content = """---
name: research-assistant
description: Help with research tasks.
---

# Research Assistant

Instructions for research.
"""
        resources = [
            SkillResource(
                type=ResourceType.REFERENCE,
                path="refs/sources.md",
                description="Source list",
            ),
            SkillResource(
                type=ResourceType.TEMPLATE,
                path="templates/report.md",
                description="Report template",
            ),
        ]

        skill = Skill.from_skill_md(content, category=SkillCategory.RESEARCH, resources=resources)

        assert skill.id == "research-assistant"
        assert len(skill.resources) == 2
        assert skill.resources[0].type == ResourceType.REFERENCE

    def test_from_skill_md_preserves_body(self):
        """Test that from_skill_md preserves the body after frontmatter."""
        content = """---
name: test-skill
description: A test skill.
---

# Test Skill

This is the body content.

## Section 1

More content here.

## Section 2

Even more content.
"""
        skill = Skill.from_skill_md(content, category=SkillCategory.CUSTOM)

        assert "# Test Skill" in skill.body
        assert "## Section 1" in skill.body
        assert "## Section 2" in skill.body
        assert "---" not in skill.body  # Frontmatter should be stripped
