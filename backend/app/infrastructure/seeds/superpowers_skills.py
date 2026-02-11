"""Superpowers skills seed data.

This module imports all 14+ Superpowers skills from the bundled skills directory
and converts them to Pythinker Skill models. Skills are self-contained in Pythinker.

Superpowers is a complete software development workflow system by Jesse Vincent:
https://github.com/obra/superpowers

Skills included:
- brainstorming: Interactive design refinement
- writing-plans: Create implementation plans
- executing-plans: Execute plans in batches
- test-driven-development: RED-GREEN-REFACTOR cycle
- systematic-debugging: 4-phase root cause process
- subagent-driven-development: Fast iteration with two-stage review
- dispatching-parallel-agents: Concurrent subagent workflows
- using-git-worktrees: Parallel development branches
- finishing-a-development-branch: Merge/PR decision workflow
- requesting-code-review: Pre-review checklist
- receiving-code-review: Responding to feedback
- verification-before-completion: Ensure fix actually works
- using-superpowers: Introduction to skills system
- writing-skills: Create new skills following best practices
"""

from pathlib import Path

from app.domain.models.skill import Skill
from app.infrastructure.seeds.superpowers_importer import import_superpowers_skills

# Path to bundled Superpowers skills (relative to this file)
# Changed from external superpowers-main to bundled skills directory
SUPERPOWERS_DIR = Path(__file__).parent / "skills"


def get_superpowers_skills() -> list[Skill]:
    """Get all Superpowers skills as Pythinker Skill models.

    Returns:
        List of Skill models, or empty list if bundled skills directory not found
    """
    if not SUPERPOWERS_DIR.exists():
        return []

    try:
        return import_superpowers_skills(SUPERPOWERS_DIR)
    except Exception:
        return []


# Export the skills for use in seeding
SUPERPOWERS_SKILLS = get_superpowers_skills()
