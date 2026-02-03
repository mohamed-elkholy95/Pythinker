#!/usr/bin/env python3
"""Validate a skill directory structure and content.

This script checks that a skill meets all requirements before delivery.

Usage:
    python quick_validate.py <skill-name>

Example:
    python quick_validate.py web-scraper
"""

import re
import sys
from pathlib import Path


class ValidationError:
    """Represents a validation error."""

    def __init__(self, severity: str, message: str):
        self.severity = severity  # ERROR, WARNING
        self.message = message

    def __str__(self) -> str:
        return f"[{self.severity}] {self.message}"


def validate_skill(skill_dir: Path) -> list[ValidationError]:
    """Validate a skill directory.

    Args:
        skill_dir: Path to the skill directory

    Returns:
        List of validation errors
    """
    errors: list[ValidationError] = []

    # Check skill directory exists
    if not skill_dir.exists():
        errors.append(ValidationError("ERROR", f"Skill directory not found: {skill_dir}"))
        return errors

    if not skill_dir.is_dir():
        errors.append(ValidationError("ERROR", f"Not a directory: {skill_dir}"))
        return errors

    # Check SKILL.md exists
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        errors.append(ValidationError("ERROR", "SKILL.md not found"))
        return errors

    # Read and validate SKILL.md
    content = skill_md.read_text()

    # Check frontmatter
    if not content.startswith("---"):
        errors.append(ValidationError("ERROR", "SKILL.md must start with YAML frontmatter (---)"))
    else:
        # Extract frontmatter
        parts = content.split("---", 2)
        if len(parts) < 3:
            errors.append(ValidationError("ERROR", "Invalid SKILL.md format - frontmatter not closed"))
        else:
            frontmatter = parts[1].strip()
            body = parts[2].strip()

            # Check required fields
            if "name:" not in frontmatter:
                errors.append(ValidationError("ERROR", "Frontmatter missing 'name' field"))
            if "description:" not in frontmatter:
                errors.append(ValidationError("ERROR", "Frontmatter missing 'description' field"))

            # Check description quality
            desc_match = re.search(r"description:\s*(.+?)(?:\n|$)", frontmatter)
            if desc_match:
                description = desc_match.group(1).strip()
                if len(description) < 20:
                    errors.append(ValidationError("WARNING", "Description is too short (< 20 chars)"))
                if "TODO" in description:
                    errors.append(ValidationError("ERROR", "Description contains TODO placeholder"))
                if "use for:" not in description.lower() and "when to use:" not in description.lower():
                    errors.append(ValidationError("WARNING", "Description should include 'Use for:' triggers"))

            # Check body has required sections
            if "## Overview" not in body and "## overview" not in body.lower():
                errors.append(ValidationError("WARNING", "SKILL.md should have an Overview section"))
            if "## Workflow" not in body and "## workflow" not in body.lower():
                errors.append(ValidationError("WARNING", "SKILL.md should have a Workflow section"))

            # Check for TODO placeholders
            if "TODO" in body:
                errors.append(ValidationError("ERROR", "SKILL.md body contains TODO placeholders"))

            # Check line count
            line_count = len(body.split("\n"))
            if line_count > 500:
                errors.append(ValidationError("WARNING", f"SKILL.md is too long ({line_count} lines, max 500)"))

            # Check character count
            if len(body) > 10000:
                errors.append(ValidationError("WARNING", f"SKILL.md body is very long ({len(body)} chars)"))

    # Check directory structure
    scripts_dir = skill_dir / "scripts"
    references_dir = skill_dir / "references"
    templates_dir = skill_dir / "templates"

    # Warn about empty directories
    if scripts_dir.exists() and not any(scripts_dir.iterdir()):
        errors.append(ValidationError("WARNING", "scripts/ directory is empty"))
    if references_dir.exists() and not any(references_dir.iterdir()):
        errors.append(ValidationError("WARNING", "references/ directory is empty"))
    if templates_dir.exists() and not any(templates_dir.iterdir()):
        errors.append(ValidationError("WARNING", "templates/ directory is empty"))

    # Check for forbidden files
    forbidden = ["README.md", "CHANGELOG.md", ".git"]
    for item in skill_dir.iterdir():
        if item.name in forbidden:
            errors.append(ValidationError("WARNING", f"Skill contains unnecessary file: {item.name}"))

    return errors


def main() -> None:
    """Main entry point."""
    if len(sys.argv) < 2:
        print("Usage: python quick_validate.py <skill-name-or-path>")
        print("\nExamples:")
        print("  python quick_validate.py web-scraper")
        print("  python quick_validate.py /path/to/skill")
        sys.exit(1)

    skill_path = sys.argv[1]

    # Handle both skill name and full path
    skill_dir = Path(skill_path)
    if not skill_dir.is_absolute() and not skill_dir.exists():
        # Try as skill name in current directory
        skill_dir = Path(".") / skill_path

    print(f"Validating skill: {skill_dir}\n")

    errors = validate_skill(skill_dir)

    # Count by severity
    error_count = sum(1 for e in errors if e.severity == "ERROR")
    warning_count = sum(1 for e in errors if e.severity == "WARNING")

    # Print results
    if not errors:
        print("✅ Skill validation passed!")
        sys.exit(0)

    for error in errors:
        symbol = "❌" if error.severity == "ERROR" else "⚠️"
        print(f"{symbol} {error}")

    print(f"\nSummary: {error_count} error(s), {warning_count} warning(s)")

    if error_count > 0:
        print("\n❌ Validation FAILED - fix errors before delivery")
        sys.exit(1)
    else:
        print("\n⚠️ Validation passed with warnings")
        sys.exit(0)


if __name__ == "__main__":
    main()
