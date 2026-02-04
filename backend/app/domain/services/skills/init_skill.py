"""Skill Initializer for creating new skill directory structures.

This module provides the SkillInitializer class that creates properly
structured skill directories following the convention:
- skill-name/
  - SKILL.md (with YAML frontmatter)
  - scripts/example.py
  - references/reference.md
  - templates/.gitkeep
"""

from pathlib import Path


class SkillInitializer:
    """Initialize new skill directory structures.

    Creates skill directories with the proper structure and template files
    required for the Pythinker skill system.

    Attributes:
        skills_base_path: Base directory where skills are stored.
        SKILL_TEMPLATE: Template for SKILL.md with YAML frontmatter.
        EXAMPLE_SCRIPT: Template for example Python script.
        EXAMPLE_REFERENCE: Template for reference documentation.
    """

    SKILL_TEMPLATE: str = """---
name: {skill_name}
description: "[TODO: Explain what this skill does and when to use it]"
---

# {skill_title}

## Overview

[TODO: 1-2 sentences explaining what this skill enables]

## Usage

[TODO: Add usage instructions]

## Resources

- **scripts/**: Executable code for automation
- **references/**: Documentation loaded into context as needed
- **templates/**: Output assets (not loaded into context)
"""

    EXAMPLE_SCRIPT: str = '''#!/usr/bin/env python3
"""Example helper script for {skill_name}."""


def main() -> None:
    print("This is an example script for {skill_name}")


if __name__ == "__main__":
    main()
'''

    EXAMPLE_REFERENCE: str = """# Reference Documentation for {skill_title}

[TODO: Add detailed reference documentation]
"""

    def __init__(self, skills_base_path: Path | str) -> None:
        """Initialize the SkillInitializer.

        Args:
            skills_base_path: Base directory where skills will be created.
                Can be a Path object or a string path.
        """
        self.skills_base_path = Path(skills_base_path)

    def _title_case(self, skill_name: str) -> str:
        """Convert skill name to title case.

        Converts hyphenated skill names to space-separated title case.

        Args:
            skill_name: The skill name (e.g., "my-skill").

        Returns:
            Title case version (e.g., "My Skill").
        """
        return " ".join(word.capitalize() for word in skill_name.split("-"))

    def init_skill(self, skill_name: str) -> Path | None:
        """Create a new skill directory structure.

        Creates the skill directory with all required subdirectories
        and template files.

        Args:
            skill_name: Name of the skill to create (e.g., "my-skill").

        Returns:
            Path to the created skill directory, or None if:
            - The skill already exists
            - The skill name is empty
        """
        # Validate skill name
        if not skill_name:
            return None

        skill_path = self.skills_base_path / skill_name

        # Check if skill already exists
        if skill_path.exists():
            return None

        # Create skill directory
        skill_path.mkdir(parents=True, exist_ok=True)

        # Generate title from skill name
        skill_title = self._title_case(skill_name)

        # Create SKILL.md
        skill_md_content = self.SKILL_TEMPLATE.format(
            skill_name=skill_name,
            skill_title=skill_title,
        )
        (skill_path / "SKILL.md").write_text(skill_md_content)

        # Create scripts directory with example.py
        scripts_dir = skill_path / "scripts"
        scripts_dir.mkdir(exist_ok=True)
        example_script_content = self.EXAMPLE_SCRIPT.format(skill_name=skill_name)
        (scripts_dir / "example.py").write_text(example_script_content)

        # Create references directory with reference.md
        references_dir = skill_path / "references"
        references_dir.mkdir(exist_ok=True)
        reference_content = self.EXAMPLE_REFERENCE.format(skill_title=skill_title)
        (references_dir / "reference.md").write_text(reference_content)

        # Create templates directory with .gitkeep
        templates_dir = skill_path / "templates"
        templates_dir.mkdir(exist_ok=True)
        (templates_dir / ".gitkeep").write_text("")

        return skill_path
