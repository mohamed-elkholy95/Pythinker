"""Skill Validator for validating SKILL.md files.

This module provides the SkillFileValidator class that validates skill directories
by checking their SKILL.md files for proper YAML frontmatter and field validation.

Validation rules:
- SKILL.md must exist in the skill directory
- Must start with valid YAML frontmatter (---)
- Frontmatter must be a valid YAML dictionary
- Only allowed keys: name, description, license, allowed-tools, metadata
- Required fields: name, description
- Name must be hyphen-case (lowercase letters, digits, hyphens)
- Name cannot start/end with hyphen or have consecutive hyphens
- Name max length: 64 characters
- Description must be a string without angle brackets
- Description max length: 1024 characters
"""

import re
from pathlib import Path
from typing import ClassVar

import yaml
from pydantic import BaseModel, Field


class ValidationResult(BaseModel):
    """Result of skill validation.

    Attributes:
        valid: Whether the skill is valid.
        error: Error message if validation failed, None if valid.
        warnings: List of warning messages (non-fatal issues).
    """

    valid: bool
    error: str | None = None
    warnings: list[str] = Field(default_factory=list)


class SkillFileValidator:
    """Validates skill directories and their SKILL.md files.

    Validates that SKILL.md files have proper YAML frontmatter
    with required fields and correct formatting.

    Attributes:
        ALLOWED_PROPERTIES: Set of allowed frontmatter keys.
        MAX_NAME_LENGTH: Maximum allowed length for skill name.
        MAX_DESCRIPTION_LENGTH: Maximum allowed length for description.
    """

    ALLOWED_PROPERTIES: ClassVar[set[str]] = {
        "name",
        "description",
        "license",
        "allowed-tools",
        "metadata",
    }
    MAX_NAME_LENGTH: ClassVar[int] = 64
    MAX_DESCRIPTION_LENGTH: ClassVar[int] = 1024

    # Pattern for valid hyphen-case names:
    # - Only lowercase letters, digits, and hyphens
    # - Cannot start or end with hyphen
    # - No consecutive hyphens
    _NAME_PATTERN: ClassVar[re.Pattern[str]] = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")

    def validate(self, skill_path: Path | str) -> ValidationResult:
        """Validate a skill directory.

        Checks that the skill has a valid SKILL.md file with proper
        YAML frontmatter and all required fields.

        Args:
            skill_path: Path to the skill directory (containing SKILL.md).

        Returns:
            ValidationResult indicating whether the skill is valid
            and any error or warning messages.
        """
        skill_path = Path(skill_path)
        skill_md_path = skill_path / "SKILL.md"

        # Check SKILL.md exists
        if not skill_md_path.exists() or not skill_md_path.is_file():
            return ValidationResult(valid=False, error="SKILL.md not found")

        # Read SKILL.md content
        try:
            content = skill_md_path.read_text()
        except Exception as e:
            return ValidationResult(valid=False, error=f"Failed to read SKILL.md: {e}")

        # Check for frontmatter
        if not content.startswith("---"):
            return ValidationResult(valid=False, error="Missing YAML frontmatter (must start with ---)")

        # Extract frontmatter
        frontmatter_result = self._extract_frontmatter(content)
        if frontmatter_result.error:
            return ValidationResult(valid=False, error=frontmatter_result.error)

        frontmatter = frontmatter_result.frontmatter

        # Validate frontmatter is a dictionary
        if not isinstance(frontmatter, dict):
            return ValidationResult(valid=False, error="Frontmatter must be a YAML dictionary")

        # Check for empty frontmatter
        if not frontmatter:
            return ValidationResult(valid=False, error="Frontmatter is empty (missing required fields)")

        # Check for unexpected keys
        unexpected_keys = set(frontmatter.keys()) - self.ALLOWED_PROPERTIES
        if unexpected_keys:
            return ValidationResult(
                valid=False,
                error=f"Unexpected keys in frontmatter: {', '.join(sorted(unexpected_keys))}",
            )

        # Validate required fields
        if "name" not in frontmatter:
            return ValidationResult(valid=False, error="Missing required field: name")

        if "description" not in frontmatter:
            return ValidationResult(valid=False, error="Missing required field: description")

        # Validate name
        name_result = self._validate_name(frontmatter["name"])
        if not name_result.valid:
            return name_result

        # Validate description
        desc_result = self._validate_description(frontmatter["description"])
        if not desc_result.valid:
            return desc_result

        return ValidationResult(valid=True)

    def _extract_frontmatter(self, content: str) -> "FrontmatterResult":
        """Extract and parse YAML frontmatter from content.

        Args:
            content: Full SKILL.md content starting with ---.

        Returns:
            FrontmatterResult with parsed frontmatter or error.
        """
        # Find closing ---
        lines = content.split("\n")
        if len(lines) < 2:
            return FrontmatterResult(error="Invalid frontmatter format", frontmatter=None)

        # Find the second --- that closes the frontmatter
        end_index = None
        for i, line in enumerate(lines[1:], start=1):
            if line.strip() == "---":
                end_index = i
                break

        if end_index is None:
            return FrontmatterResult(
                error="Invalid frontmatter format (missing closing ---)",
                frontmatter=None,
            )

        # Extract YAML content
        yaml_content = "\n".join(lines[1:end_index])

        # Parse YAML
        try:
            frontmatter = yaml.safe_load(yaml_content)
        except yaml.YAMLError as e:
            return FrontmatterResult(error=f"Invalid YAML in frontmatter: {e}", frontmatter=None)

        return FrontmatterResult(error=None, frontmatter=frontmatter)

    def _validate_name(self, name: str | None) -> ValidationResult:
        """Validate the skill name.

        Args:
            name: The skill name to validate.

        Returns:
            ValidationResult for the name validation.
        """
        if not isinstance(name, str):
            return ValidationResult(valid=False, error="Name must be a string (hyphen-case format)")

        if len(name) > self.MAX_NAME_LENGTH:
            return ValidationResult(
                valid=False,
                error=f"Name exceeds maximum length of {self.MAX_NAME_LENGTH} characters",
            )

        if not self._NAME_PATTERN.match(name):
            return ValidationResult(
                valid=False,
                error="Name must be in hyphen-case format (lowercase letters, digits, "
                "and hyphens; cannot start/end with hyphen or have consecutive hyphens)",
            )

        return ValidationResult(valid=True)

    def _validate_description(self, description: str | None) -> ValidationResult:
        """Validate the skill description.

        Args:
            description: The skill description to validate.

        Returns:
            ValidationResult for the description validation.
        """
        if not isinstance(description, str):
            return ValidationResult(valid=False, error="Description must be a string")

        if len(description) > self.MAX_DESCRIPTION_LENGTH:
            return ValidationResult(
                valid=False,
                error=f"Description exceeds maximum length of {self.MAX_DESCRIPTION_LENGTH} characters",
            )

        if "<" in description or ">" in description:
            return ValidationResult(
                valid=False,
                error="Description cannot contain angle brackets (< or >)",
            )

        return ValidationResult(valid=True)


class FrontmatterResult:
    """Helper class for frontmatter extraction result.

    Attributes:
        error: Error message if extraction failed.
        frontmatter: Parsed frontmatter dictionary.
    """

    def __init__(self, error: str | None, frontmatter: dict[str, object] | None) -> None:
        """Initialize the frontmatter result.

        Args:
            error: Error message if extraction failed.
            frontmatter: Parsed frontmatter dictionary.
        """
        self.error = error
        self.frontmatter = frontmatter

        # Also store as ValidationResult for convenience
        if error:
            self.validation_result = ValidationResult(valid=False, error=error)
        else:
            self.validation_result = ValidationResult(valid=True)
