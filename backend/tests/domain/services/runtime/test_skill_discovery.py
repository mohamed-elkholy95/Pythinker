"""Tests for skill_discovery_middleware — filesystem scanning and frontmatter parsing."""

from __future__ import annotations

from pathlib import Path

from app.domain.services.runtime.skill_discovery_middleware import (
    SkillSummary,
    scan_skill_directories,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_skill_md(directory: Path, name: str, description: str) -> None:
    """Create a minimal SKILL.md with YAML frontmatter in *directory*."""
    directory.mkdir(parents=True, exist_ok=True)
    content = f"---\nname: {name}\ndescription: {description}\n---\n\nSkill body text.\n"
    (directory / "SKILL.md").write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_discovers_skills_with_skill_md(tmp_path: Path) -> None:
    """Skills in public/ and custom/ are discovered; dirs without SKILL.md are ignored."""
    # Valid skill in public/
    _write_skill_md(tmp_path / "public" / "research", "research", "Web research skill")
    # Valid skill in custom/
    _write_skill_md(tmp_path / "custom" / "my-skill", "my-skill", "A custom skill")
    # Decoy directory in public/ without SKILL.md — must NOT appear in results
    (tmp_path / "public" / "no-skill-here").mkdir(parents=True, exist_ok=True)

    results = scan_skill_directories(tmp_path)

    assert len(results) == 2
    names = {s.name for s in results}
    assert "research" in names
    assert "my-skill" in names


def test_parses_frontmatter(tmp_path: Path) -> None:
    """Frontmatter name and description fields are extracted correctly."""
    _write_skill_md(
        tmp_path / "public" / "deep-research",
        "deep-research",
        "Performs in-depth research on any topic",
    )

    results = scan_skill_directories(tmp_path)

    assert len(results) == 1
    skill = results[0]
    assert skill.name == "deep-research"
    assert skill.description == "Performs in-depth research on any topic"
    assert skill.category == "public"
    assert "SKILL.md" in skill.path


def test_empty_directory_returns_empty(tmp_path: Path) -> None:
    """Scanning an empty root returns an empty list without errors."""
    results = scan_skill_directories(tmp_path)

    assert results == []


def test_skill_summary_to_prompt_entry() -> None:
    """to_prompt_entry() returns a string containing name and description."""
    skill = SkillSummary(
        name="web-search",
        description="Search the web for information",
        category="public",
        path="/skills/public/web-search/SKILL.md",
    )

    entry = skill.to_prompt_entry()

    assert "web-search" in entry
    assert "Search the web for information" in entry
    assert "[public]" in entry
