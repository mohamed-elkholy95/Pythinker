"""Tests for SkillValidator.

Tests the skill validation functionality that validates SKILL.md files
with YAML frontmatter according to the skill specification:
- Must have valid YAML frontmatter (starts with ---)
- Required fields: name, description
- Name must be hyphen-case (lowercase letters, digits, hyphens only)
- Name cannot start/end with hyphen or have consecutive hyphens
- Description must not contain angle brackets
- Only allowed properties: name, description, license, allowed-tools, metadata
"""

import tempfile
from pathlib import Path

import pytest

from app.domain.services.skills.skill_validator import SkillValidator, ValidationResult


@pytest.fixture
def temp_skill_dir() -> Path:
    """Create a temporary skill directory with valid SKILL.md."""
    with tempfile.TemporaryDirectory() as temp_dir:
        skill_dir = Path(temp_dir)
        (skill_dir / "SKILL.md").write_text("""---
name: my-valid-skill
description: A valid skill description
---

# My Valid Skill

Content here.
""")
        yield skill_dir


class TestValidationResult:
    """Tests for ValidationResult model."""

    def test_valid_result(self) -> None:
        """Test creating a valid result."""
        result = ValidationResult(valid=True)
        assert result.valid is True
        assert result.error is None
        assert result.warnings == []

    def test_invalid_result_with_error(self) -> None:
        """Test creating an invalid result with error."""
        result = ValidationResult(valid=False, error="Something went wrong")
        assert result.valid is False
        assert result.error == "Something went wrong"
        assert result.warnings == []

    def test_valid_result_with_warnings(self) -> None:
        """Test creating a valid result with warnings."""
        result = ValidationResult(valid=True, warnings=["Consider adding license"])
        assert result.valid is True
        assert result.error is None
        assert result.warnings == ["Consider adding license"]


class TestSkillValidatorClassAttributes:
    """Tests for SkillValidator class attributes."""

    def test_allowed_properties(self) -> None:
        """Test that allowed properties are defined correctly."""
        expected = {"name", "description", "license", "allowed-tools", "metadata"}
        assert expected == SkillValidator.ALLOWED_PROPERTIES

    def test_max_name_length(self) -> None:
        """Test that max name length is defined."""
        assert SkillValidator.MAX_NAME_LENGTH == 64

    def test_max_description_length(self) -> None:
        """Test that max description length is defined."""
        assert SkillValidator.MAX_DESCRIPTION_LENGTH == 1024


class TestSkillValidatorValidSkill:
    """Tests for validating valid skills."""

    def test_validate_valid_skill(self, temp_skill_dir: Path) -> None:
        """Test validating a valid skill returns success."""
        validator = SkillValidator()
        result = validator.validate(temp_skill_dir)
        assert result.valid is True
        assert result.error is None

    def test_validate_valid_skill_with_string_path(self, temp_skill_dir: Path) -> None:
        """Test validating a skill with string path works."""
        validator = SkillValidator()
        result = validator.validate(str(temp_skill_dir))
        assert result.valid is True
        assert result.error is None

    def test_validate_skill_with_all_optional_fields(self) -> None:
        """Test validating a skill with all allowed optional fields."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: complete-skill
description: A complete skill with all fields
license: MIT
allowed-tools:
  - browser
  - terminal
metadata:
  author: Test Author
  version: 1.0.0
---

# Complete Skill

Full content here.
""")
            result = validator.validate(skill_dir)
        assert result.valid is True
        assert result.error is None


class TestSkillValidatorMissingFiles:
    """Tests for missing files validation."""

    def test_validate_missing_skill_md(self) -> None:
        """Test that missing SKILL.md returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            result = validator.validate(Path(temp_dir))
        assert result.valid is False
        assert "SKILL.md not found" in result.error


class TestSkillValidatorFrontmatter:
    """Tests for frontmatter validation."""

    def test_validate_missing_frontmatter(self) -> None:
        """Test that missing frontmatter returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("# No frontmatter\n\nJust content.")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "frontmatter" in result.error.lower()

    def test_validate_empty_frontmatter(self) -> None:
        """Test that empty frontmatter returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
---

# Empty frontmatter
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        # Should indicate missing required fields or empty frontmatter
        assert result.error is not None

    def test_validate_invalid_yaml_frontmatter(self) -> None:
        """Test that invalid YAML in frontmatter returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: valid-name
description: [unclosed bracket
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        # Should indicate YAML parsing error
        assert result.error is not None

    def test_validate_frontmatter_not_dict(self) -> None:
        """Test that non-dict frontmatter returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
- item1
- item2
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert result.error is not None


class TestSkillValidatorNameValidation:
    """Tests for skill name validation."""

    def test_validate_invalid_name_format(self) -> None:
        """Test that non-hyphen-case name returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: Invalid_Name
description: Test
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "hyphen-case" in result.error.lower()

    def test_validate_name_with_uppercase(self) -> None:
        """Test that uppercase letters in name return error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: MySkill
description: Test
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "hyphen-case" in result.error.lower()

    def test_validate_name_starts_with_hyphen(self) -> None:
        """Test that name starting with hyphen returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: -my-skill
description: Test
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "hyphen-case" in result.error.lower()

    def test_validate_name_ends_with_hyphen(self) -> None:
        """Test that name ending with hyphen returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: my-skill-
description: Test
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "hyphen-case" in result.error.lower()

    def test_validate_name_with_consecutive_hyphens(self) -> None:
        """Test that consecutive hyphens in name return error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: my--skill
description: Test
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "hyphen-case" in result.error.lower()

    def test_validate_name_too_long(self) -> None:
        """Test that name exceeding max length returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            long_name = "a" * 65  # MAX_NAME_LENGTH is 64
            (skill_dir / "SKILL.md").write_text(f"""---
name: {long_name}
description: Test
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "64" in result.error or "length" in result.error.lower()

    def test_validate_missing_name(self) -> None:
        """Test that missing name returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
description: Test description
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "name" in result.error.lower()

    def test_validate_name_with_numbers(self) -> None:
        """Test that name with numbers is valid."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: api-v2-helper
description: Test
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is True


class TestSkillValidatorDescriptionValidation:
    """Tests for skill description validation."""

    def test_validate_missing_description(self) -> None:
        """Test that missing description returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: my-skill
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "description" in result.error.lower()

    def test_validate_description_too_long(self) -> None:
        """Test that description exceeding max length returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            long_desc = "a" * 1025  # MAX_DESCRIPTION_LENGTH is 1024
            (skill_dir / "SKILL.md").write_text(f"""---
name: my-skill
description: {long_desc}
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "1024" in result.error or "length" in result.error.lower()

    def test_validate_description_with_angle_brackets(self) -> None:
        """Test that description with angle brackets returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: This has <html> tags
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "angle" in result.error.lower() or "<" in result.error

    def test_validate_description_with_greater_than(self) -> None:
        """Test that description with > returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: Value > 100
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "angle" in result.error.lower() or ">" in result.error

    def test_validate_description_not_string(self) -> None:
        """Test that non-string description returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description:
  - item1
  - item2
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert result.error is not None


class TestSkillValidatorUnexpectedKeys:
    """Tests for unexpected keys validation."""

    def test_validate_unexpected_keys(self) -> None:
        """Test that unexpected keys return error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: Test
author: Someone
custom-field: value
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "unexpected" in result.error.lower() or "author" in result.error

    def test_validate_single_unexpected_key(self) -> None:
        """Test that a single unexpected key returns error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: my-skill
description: Test
version: 1.0.0
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is False
        assert "version" in result.error


class TestSkillValidatorEdgeCases:
    """Tests for edge cases."""

    def test_validate_name_single_char(self) -> None:
        """Test that single character name is valid."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").write_text("""---
name: a
description: Test
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is True

    def test_validate_name_max_length(self) -> None:
        """Test that name at max length is valid."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            max_name = "a" * 64  # Exactly MAX_NAME_LENGTH
            (skill_dir / "SKILL.md").write_text(f"""---
name: {max_name}
description: Test
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is True

    def test_validate_description_max_length(self) -> None:
        """Test that description at max length is valid."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            max_desc = "a" * 1024  # Exactly MAX_DESCRIPTION_LENGTH
            (skill_dir / "SKILL.md").write_text(f"""---
name: my-skill
description: {max_desc}
---

Content
""")
            result = validator.validate(skill_dir)
        assert result.valid is True

    def test_validate_nonexistent_path(self) -> None:
        """Test that nonexistent path returns error."""
        validator = SkillValidator()
        result = validator.validate(Path("/nonexistent/path/to/skill"))
        assert result.valid is False
        assert "SKILL.md not found" in result.error

    def test_validate_skill_md_is_directory(self) -> None:
        """Test that SKILL.md as directory returns appropriate error."""
        validator = SkillValidator()
        with tempfile.TemporaryDirectory() as temp_dir:
            skill_dir = Path(temp_dir)
            (skill_dir / "SKILL.md").mkdir()  # Create as directory, not file
            result = validator.validate(skill_dir)
        assert result.valid is False
        # Should fail when trying to read it
        assert result.error is not None
