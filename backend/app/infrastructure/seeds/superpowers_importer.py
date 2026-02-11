"""Importer utility for Superpowers SKILL.md files.

Parses Superpowers skill format (YAML frontmatter + Markdown content)
and converts to Pythinker Skill models.

SKILL.md Format:
---
name: skill-name
description: Short description
---

# Skill Title

Full skill content in Markdown...
"""

import re
from pathlib import Path
from typing import Any

import yaml

from app.domain.models.skill import Skill, SkillCategory, SkillInvocationType, SkillSource
from app.infrastructure.seeds.superpowers_tool_mapping import get_default_tools_for_skill


class SkillParseError(Exception):
    """Raised when skill file parsing fails."""


def parse_skill_md(file_path: Path) -> tuple[dict[str, Any], str]:
    """Parse a SKILL.md file into frontmatter and content.

    Args:
        file_path: Path to SKILL.md file

    Returns:
        Tuple of (frontmatter_dict, markdown_content)

    Raises:
        SkillParseError: If file format is invalid
    """
    if not file_path.exists():
        raise SkillParseError(f"File not found: {file_path}")

    content = file_path.read_text(encoding="utf-8")

    # Match YAML frontmatter pattern
    # Format: --- at start, YAML content, --- delimiter, markdown content
    pattern = r"^---\s*\n(.*?)\n---\s*\n(.*)$"
    match = re.match(pattern, content, re.DOTALL)

    if not match:
        raise SkillParseError(f"No YAML frontmatter found in {file_path}")

    frontmatter_str = match.group(1)
    markdown_content = match.group(2).strip()

    try:
        frontmatter = yaml.safe_load(frontmatter_str)
    except yaml.YAMLError as e:
        raise SkillParseError(f"Invalid YAML in {file_path}: {e}") from e

    if not isinstance(frontmatter, dict):
        raise SkillParseError(f"Frontmatter must be a dict in {file_path}")

    return frontmatter, markdown_content


def extract_trigger_patterns(description: str, content: str) -> list[str]:
    """Extract trigger patterns from skill description and content.

    Args:
        description: Skill description from frontmatter
        content: Full markdown content

    Returns:
        List of regex patterns
    """
    patterns = []

    # Extract patterns from description
    # Look for phrases like "Use when...", "before...", etc.
    desc_lower = description.lower()

    if "before" in desc_lower and "creative work" in desc_lower:
        patterns.extend(
            [
                r"(?i)create.*feature",
                r"(?i)build.*component",
                r"(?i)add.*functionality",
                r"(?i)design\s+",
                r"(?i)implement.*new",
            ]
        )

    if "bug" in desc_lower or "debug" in desc_lower:
        patterns.extend(
            [
                r"(?i)debug",
                r"(?i)fix.*bug",
                r"(?i)error",
                r"(?i)test.*fail",
                r"(?i)unexpected.*behavior",
            ]
        )

    if "test" in desc_lower and "implementation" in desc_lower:
        patterns.extend(
            [
                r"(?i)implement",
                r"(?i)add.*feature",
                r"(?i)write.*code",
                r"(?i)build.*function",
            ]
        )

    if "plan" in desc_lower and "write" in desc_lower:
        patterns.extend(
            [
                r"(?i)write.*plan",
                r"(?i)create.*plan",
                r"(?i)implementation.*plan",
            ]
        )

    if "execute" in desc_lower and "plan" in desc_lower:
        patterns.extend(
            [
                r"(?i)execute.*plan",
                r"(?i)implement.*plan",
                r"(?i)follow.*plan",
            ]
        )

    if "worktree" in desc_lower:
        patterns.extend(
            [
                r"(?i)create.*worktree",
                r"(?i)new.*branch",
            ]
        )

    if "branch" in desc_lower and "finish" in desc_lower:
        patterns.extend(
            [
                r"(?i)finish.*branch",
                r"(?i)merge.*branch",
                r"(?i)create.*pr",
            ]
        )

    if "code.*review" in desc_lower or "review.*code" in desc_lower:
        patterns.extend(
            [
                r"(?i)code.*review",
                r"(?i)review.*code",
                r"(?i)ready.*review",
            ]
        )

    if "skill" in desc_lower and ("creat" in desc_lower or "writ" in desc_lower):
        patterns.extend(
            [
                r"(?i)create.*skill",
                r"(?i)write.*skill",
                r"(?i)new.*skill",
            ]
        )

    # Remove duplicates while preserving order
    seen = set()
    unique_patterns = []
    for pattern in patterns:
        if pattern not in seen:
            seen.add(pattern)
            unique_patterns.append(pattern)

    return unique_patterns


def infer_category(name: str, description: str, content: str) -> SkillCategory:
    """Infer skill category from name, description, and content.

    Args:
        name: Skill name
        description: Skill description
        content: Full markdown content

    Returns:
        SkillCategory enum value
    """
    name_lower = name.lower()
    desc_lower = description.lower()

    # Check for coding-related keywords
    coding_keywords = [
        "test",
        "debug",
        "git",
        "commit",
        "branch",
        "code review",
        "worktree",
        "tdd",
    ]
    if any(keyword in name_lower or keyword in desc_lower for keyword in coding_keywords):
        return SkillCategory.CODING

    # Check for research keywords
    research_keywords = ["research", "search", "browse", "gather"]
    if any(keyword in name_lower or keyword in desc_lower for keyword in research_keywords):
        return SkillCategory.RESEARCH

    # Default to CUSTOM for workflow/orchestration skills
    return SkillCategory.CUSTOM


def infer_invocation_type(name: str, description: str) -> SkillInvocationType:
    """Infer invocation type from skill name and description.

    Args:
        name: Skill name
        description: Skill description

    Returns:
        SkillInvocationType enum value
    """
    name_lower = name.lower()

    # Skills that should only be AI-triggered
    ai_only_patterns = [
        "test-driven-development",  # Auto-trigger during implementation
        "systematic-debugging",  # Auto-trigger on errors
        "verification-before-completion",  # Auto-trigger at task end
    ]
    if any(pattern in name_lower for pattern in ai_only_patterns):
        return SkillInvocationType.AI

    # Skills that should only be user-triggered
    user_only_patterns = [
        "subagent-driven",
        "dispatching-parallel",
        "receiving-code-review",
        "using-superpowers",
    ]
    if any(pattern in name_lower for pattern in user_only_patterns):
        return SkillInvocationType.USER

    # Default to BOTH (user or AI can invoke)
    return SkillInvocationType.BOTH


def assign_icon(name: str, category: SkillCategory) -> str:
    """Assign a Lucide icon name based on skill name and category.

    Args:
        name: Skill name
        category: Skill category

    Returns:
        Lucide icon name
    """
    # Specific icon mappings
    icon_map = {
        "brainstorming": "lightbulb",
        "writing-plans": "file-text",
        "executing-plans": "play-circle",
        "test-driven-development": "check-circle",
        "systematic-debugging": "bug",
        "subagent-driven-development": "users",
        "dispatching-parallel-agents": "git-branch",
        "using-git-worktrees": "git-branch",
        "finishing-a-development-branch": "git-merge",
        "requesting-code-review": "file-search",
        "receiving-code-review": "message-square",
        "verification-before-completion": "check-square",
        "using-superpowers": "zap",
        "writing-skills": "file-edit",
    }

    name_lower = name.lower()
    if name_lower in icon_map:
        return icon_map[name_lower]

    # Fallback to category-based icons
    category_icons = {
        SkillCategory.CODING: "code",
        SkillCategory.RESEARCH: "search",
        SkillCategory.BROWSER: "globe",
        SkillCategory.FILE_MANAGEMENT: "folder",
        SkillCategory.DATA_ANALYSIS: "bar-chart",
        SkillCategory.COMMUNICATION: "message-circle",
        SkillCategory.CUSTOM: "sparkles",
    }

    return category_icons.get(category, "sparkles")


def convert_skill_md_to_model(
    file_path: Path,
    *,
    author: str = "Superpowers by Jesse Vincent",
) -> Skill:
    """Convert a SKILL.md file to a Pythinker Skill model.

    Args:
        file_path: Path to SKILL.md file
        author: Skill author name

    Returns:
        Skill model instance

    Raises:
        SkillParseError: If parsing fails
    """
    frontmatter, content = parse_skill_md(file_path)

    # Extract required fields
    name = frontmatter.get("name")
    description = frontmatter.get("description")

    if not name:
        raise SkillParseError(f"Missing 'name' in frontmatter: {file_path}")
    if not description:
        raise SkillParseError(f"Missing 'description' in frontmatter: {file_path}")

    # Infer/derive other fields
    category = infer_category(name, description, content)
    invocation_type = infer_invocation_type(name, description)
    icon = assign_icon(name, category)
    trigger_patterns = extract_trigger_patterns(description, content)
    required_tools = get_default_tools_for_skill(name)

    # Create Skill model
    return Skill(
        id=name,  # Use name as slug ID
        name=name.replace("-", " ").title(),  # Convert "test-driven-development" → "Test Driven Development"
        description=description,
        category=category,
        source=SkillSource.OFFICIAL,
        icon=icon,
        author=author,
        required_tools=required_tools,
        system_prompt_addition=f"""<{name.replace("-", "_")}_skill>
{content}
</{name.replace("-", "_")}_skill>""",
        invocation_type=invocation_type,
        trigger_patterns=trigger_patterns,
        supports_dynamic_context=False,  # Initially disabled
        allowed_tools=None,  # No restrictions initially
        version="1.0.0",
    )


def import_superpowers_skills(superpowers_dir: Path) -> list[Skill]:
    """Import all Superpowers skills from a directory.

    Args:
        superpowers_dir: Path to superpowers-main directory

    Returns:
        List of Skill models

    Raises:
        SkillParseError: If any skill fails to parse
    """
    skills_dir = superpowers_dir / "skills"
    if not skills_dir.exists():
        raise SkillParseError(f"Skills directory not found: {skills_dir}")

    skills = []
    skill_dirs = [d for d in skills_dir.iterdir() if d.is_dir()]

    for skill_dir in sorted(skill_dirs):
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            continue

        try:
            skill = convert_skill_md_to_model(skill_md)
            skills.append(skill)
        except SkillParseError:
            # Log error but continue with other skills
            continue

    return skills
