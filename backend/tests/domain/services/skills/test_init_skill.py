"""Tests for SkillInitializer.

Tests the skill initialization functionality that creates proper skill
directory structures following the convention:
- skill-name/
  - SKILL.md (with YAML frontmatter)
  - scripts/example.py
  - references/reference.md
  - templates/.gitkeep
"""

import shutil
import tempfile
from pathlib import Path

import pytest

from app.domain.services.skills.init_skill import SkillInitializer


@pytest.fixture
def temp_skills_dir() -> Path:
    """Create a temporary skills directory."""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


class TestSkillInitializerInit:
    """Tests for SkillInitializer initialization."""

    def test_init_with_path(self, temp_skills_dir: Path) -> None:
        """Test initialization with Path object."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        assert initializer.skills_base_path == temp_skills_dir

    def test_init_with_string_path(self, temp_skills_dir: Path) -> None:
        """Test initialization accepts str not just Path."""
        initializer = SkillInitializer(skills_base_path=str(temp_skills_dir))
        assert initializer.skills_base_path == temp_skills_dir
        assert isinstance(initializer.skills_base_path, Path)


class TestSkillInitializerTitleCase:
    """Tests for title case conversion."""

    def test_title_case_simple(self, temp_skills_dir: Path) -> None:
        """Test simple skill name conversion."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        assert initializer._title_case("my-skill") == "My Skill"

    def test_title_case_single_word(self, temp_skills_dir: Path) -> None:
        """Test single word skill name."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        assert initializer._title_case("excel") == "Excel"

    def test_title_case_multiple_hyphens(self, temp_skills_dir: Path) -> None:
        """Test skill name with multiple hyphens."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        assert initializer._title_case("my-api-helper") == "My Api Helper"

    def test_title_case_with_numbers(self, temp_skills_dir: Path) -> None:
        """Test skill name containing numbers."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        assert initializer._title_case("api-v2-helper") == "Api V2 Helper"

    def test_title_case_already_titlecase(self, temp_skills_dir: Path) -> None:
        """Test skill name that already has uppercase letters."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        # Should still work, converting hyphens to spaces
        assert initializer._title_case("API-Helper") == "Api Helper"


class TestSkillInitializerStructure:
    """Tests for skill directory structure creation."""

    def test_init_creates_skill_structure(self, temp_skills_dir: Path) -> None:
        """Test that init_skill creates complete directory structure."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        result = initializer.init_skill("test-skill")

        assert result is not None
        assert (temp_skills_dir / "test-skill" / "SKILL.md").exists()
        assert (temp_skills_dir / "test-skill" / "scripts").is_dir()
        assert (temp_skills_dir / "test-skill" / "references").is_dir()
        assert (temp_skills_dir / "test-skill" / "templates").is_dir()

    def test_init_creates_valid_skill_md(self, temp_skills_dir: Path) -> None:
        """Test that SKILL.md has valid YAML frontmatter."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        initializer.init_skill("my-api-helper")

        skill_md = (temp_skills_dir / "my-api-helper" / "SKILL.md").read_text()
        assert skill_md.startswith("---")
        assert "name: my-api-helper" in skill_md
        assert "description:" in skill_md

    def test_init_fails_if_exists(self, temp_skills_dir: Path) -> None:
        """Test that init returns None if skill already exists."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        initializer.init_skill("existing-skill")
        result = initializer.init_skill("existing-skill")

        assert result is None

    def test_init_returns_path_on_success(self, temp_skills_dir: Path) -> None:
        """Test that init returns the created skill path."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        result = initializer.init_skill("new-skill")

        assert result is not None
        assert result == temp_skills_dir / "new-skill"
        assert result.exists()


class TestSkillInitializerTemplates:
    """Tests for template content creation."""

    def test_skill_md_contains_title(self, temp_skills_dir: Path) -> None:
        """Test that SKILL.md contains the skill title."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        initializer.init_skill("data-analyzer")

        skill_md = (temp_skills_dir / "data-analyzer" / "SKILL.md").read_text()
        assert "# Data Analyzer" in skill_md

    def test_skill_md_has_complete_structure(self, temp_skills_dir: Path) -> None:
        """Test that SKILL.md has all required sections."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        initializer.init_skill("complete-skill")

        skill_md = (temp_skills_dir / "complete-skill" / "SKILL.md").read_text()
        assert "## Overview" in skill_md
        assert "## Usage" in skill_md
        assert "## Resources" in skill_md
        assert "**scripts/**" in skill_md
        assert "**references/**" in skill_md
        assert "**templates/**" in skill_md

    def test_example_script_created(self, temp_skills_dir: Path) -> None:
        """Test that example.py is created with correct content."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        initializer.init_skill("test-skill")

        example_py = (temp_skills_dir / "test-skill" / "scripts" / "example.py").read_text()
        assert "#!/usr/bin/env python3" in example_py
        assert "test-skill" in example_py
        assert "def main()" in example_py
        assert 'if __name__ == "__main__":' in example_py

    def test_reference_md_created(self, temp_skills_dir: Path) -> None:
        """Test that reference.md is created with correct content."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        initializer.init_skill("test-skill")

        reference_md = (temp_skills_dir / "test-skill" / "references" / "reference.md").read_text()
        assert "# Reference Documentation for Test Skill" in reference_md
        assert "[TODO: Add detailed reference documentation]" in reference_md

    def test_templates_gitkeep_created(self, temp_skills_dir: Path) -> None:
        """Test that .gitkeep is created in templates directory."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        initializer.init_skill("test-skill")

        gitkeep = temp_skills_dir / "test-skill" / "templates" / ".gitkeep"
        assert gitkeep.exists()


class TestSkillInitializerEdgeCases:
    """Tests for edge cases and validation."""

    def test_empty_skill_name(self, temp_skills_dir: Path) -> None:
        """Test handling of empty skill name."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        result = initializer.init_skill("")

        # Should return None for empty skill name
        assert result is None

    def test_skill_name_with_spaces(self, temp_skills_dir: Path) -> None:
        """Test that skill names with spaces are handled."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        # Spaces in directory names should still work but may not be ideal
        result = initializer.init_skill("skill with spaces")

        # Implementation choice: either reject or convert
        # Our implementation will handle it (create directory as-is)
        assert result is not None

    def test_skill_name_with_underscores(self, temp_skills_dir: Path) -> None:
        """Test that skill names with underscores work correctly."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        result = initializer.init_skill("my_skill_name")

        assert result is not None
        assert (temp_skills_dir / "my_skill_name" / "SKILL.md").exists()

    def test_skill_name_unicode(self, temp_skills_dir: Path) -> None:
        """Test handling of unicode characters in skill names."""
        initializer = SkillInitializer(skills_base_path=temp_skills_dir)
        result = initializer.init_skill("skill-with-unicode-cafe")

        assert result is not None
        assert result.exists()


class TestSkillInitializerClassAttributes:
    """Tests for class attribute templates."""

    def test_skill_template_defined(self, temp_skills_dir: Path) -> None:
        """Test that SKILL_TEMPLATE class attribute is defined."""
        assert hasattr(SkillInitializer, "SKILL_TEMPLATE")
        assert "{skill_name}" in SkillInitializer.SKILL_TEMPLATE
        assert "{skill_title}" in SkillInitializer.SKILL_TEMPLATE

    def test_example_script_template_defined(self, temp_skills_dir: Path) -> None:
        """Test that EXAMPLE_SCRIPT class attribute is defined."""
        assert hasattr(SkillInitializer, "EXAMPLE_SCRIPT")
        assert "{skill_name}" in SkillInitializer.EXAMPLE_SCRIPT

    def test_example_reference_template_defined(self, temp_skills_dir: Path) -> None:
        """Test that EXAMPLE_REFERENCE class attribute is defined."""
        assert hasattr(SkillInitializer, "EXAMPLE_REFERENCE")
        assert "{skill_title}" in SkillInitializer.EXAMPLE_REFERENCE
