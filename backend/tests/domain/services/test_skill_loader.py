"""Tests for SkillLoader with progressive disclosure.

Tests the context-efficient skill loading that implements Pythinker AI's
progressive disclosure pattern:
- Level 1: Metadata only (name, description)
- Level 2: Metadata + body (full instructions)
- Level 3: Everything including resources
"""

from pathlib import Path

import pytest

from app.domain.models.skill import ResourceType
from app.domain.services.skill_loader import SkillLoader


@pytest.fixture
def skill_dir(tmp_path: Path) -> Path:
    """Create a temporary skill directory with proper structure."""
    skill_path = tmp_path / "test-skill"
    skill_path.mkdir()

    # Create SKILL.md with YAML frontmatter
    skill_md = skill_path / "SKILL.md"
    skill_md.write_text("""---
name: test-skill
description: A test skill for unit testing.
---

# Test Skill

Use this skill when testing.

## Usage

1. Do thing one
2. Do thing two
""")

    # Create references directory with API docs
    refs = skill_path / "references"
    refs.mkdir()
    (refs / "api.md").write_text("# API Reference\n\nEndpoint docs here.")

    return skill_path


@pytest.fixture
def multi_skill_dir(tmp_path: Path) -> Path:
    """Create multiple skill directories for discovery testing."""
    # First skill
    skill1_path = tmp_path / "skill-one"
    skill1_path.mkdir()
    (skill1_path / "SKILL.md").write_text("""---
name: skill-one
description: First test skill.
---

# Skill One

Instructions for skill one.
""")

    # Second skill
    skill2_path = tmp_path / "skill-two"
    skill2_path.mkdir()
    (skill2_path / "SKILL.md").write_text("""---
name: skill-two
description: Second test skill.
---

# Skill Two

Instructions for skill two.
""")

    return tmp_path


@pytest.fixture
def complete_skill_dir(tmp_path: Path) -> Path:
    """Create a skill with all resource types."""
    skill_path = tmp_path / "complete-skill"
    skill_path.mkdir()

    # SKILL.md
    (skill_path / "SKILL.md").write_text("""---
name: complete-skill
description: A complete skill with all resource types.
---

# Complete Skill

This skill has scripts, references, and templates.

## Scripts

Use `scripts/helper.py` for automated tasks.

## References

See `references/guide.md` for detailed documentation.
""")

    # Scripts directory
    scripts = skill_path / "scripts"
    scripts.mkdir()
    (scripts / "helper.py").write_text('"""Helper script."""\nprint("Hello")')

    # References directory
    refs = skill_path / "references"
    refs.mkdir()
    (refs / "guide.md").write_text("# Guide\n\nDetailed guide content.")

    # Templates directory
    templates = skill_path / "templates"
    templates.mkdir()
    (templates / "output.md").write_text("# Template\n\n{{content}}")

    return skill_path


class TestSkillLoaderDiscovery:
    """Tests for skill discovery functionality."""

    @pytest.mark.asyncio
    async def test_load_skill_metadata(self, skill_dir: Path) -> None:
        """Test discovering skills loads metadata correctly."""
        loader = SkillLoader(skills_dir=skill_dir.parent)
        skills = await loader.discover_skills()

        assert len(skills) == 1
        assert skills[0].name == "test-skill"
        assert skills[0].description == "A test skill for unit testing."

    @pytest.mark.asyncio
    async def test_discover_multiple_skills(self, multi_skill_dir: Path) -> None:
        """Test discovering multiple skills from a directory."""
        loader = SkillLoader(skills_dir=multi_skill_dir)
        skills = await loader.discover_skills()

        assert len(skills) == 2
        skill_names = {s.name for s in skills}
        assert skill_names == {"skill-one", "skill-two"}

    @pytest.mark.asyncio
    async def test_discover_skills_skips_invalid(self, tmp_path: Path) -> None:
        """Test that discovery skips directories without SKILL.md."""
        # Valid skill
        valid = tmp_path / "valid-skill"
        valid.mkdir()
        (valid / "SKILL.md").write_text("""---
name: valid-skill
description: A valid skill.
---

Valid skill content.
""")

        # Invalid directory (no SKILL.md)
        invalid = tmp_path / "not-a-skill"
        invalid.mkdir()
        (invalid / "README.md").write_text("This is not a skill.")

        loader = SkillLoader(skills_dir=tmp_path)
        skills = await loader.discover_skills()

        assert len(skills) == 1
        assert skills[0].name == "valid-skill"

    @pytest.mark.asyncio
    async def test_discover_skills_empty_directory(self, tmp_path: Path) -> None:
        """Test discovery on empty directory returns empty list."""
        loader = SkillLoader(skills_dir=tmp_path)
        skills = await loader.discover_skills()

        assert skills == []


class TestSkillLoaderLoad:
    """Tests for loading skills at different disclosure levels."""

    @pytest.mark.asyncio
    async def test_load_skill_with_resources(self, skill_dir: Path) -> None:
        """Test loading a skill at disclosure level 3 includes resources."""
        loader = SkillLoader(skills_dir=skill_dir.parent)
        skill = await loader.load_skill("test-skill", disclosure_level=3)

        assert skill is not None
        assert len(skill.resources) >= 1
        assert any(r.path.endswith("api.md") for r in skill.resources)

    @pytest.mark.asyncio
    async def test_load_skill_level_1_metadata_only(self, skill_dir: Path) -> None:
        """Test level 1 disclosure returns only metadata."""
        loader = SkillLoader(skills_dir=skill_dir.parent)
        skill = await loader.load_skill("test-skill", disclosure_level=1)

        assert skill is not None
        assert skill.name == "test-skill"
        assert skill.description == "A test skill for unit testing."
        # At level 1, body should be empty or minimal
        assert skill.body == ""
        assert skill.resources == []

    @pytest.mark.asyncio
    async def test_load_skill_level_2_with_body(self, skill_dir: Path) -> None:
        """Test level 2 disclosure includes body but not resources."""
        loader = SkillLoader(skills_dir=skill_dir.parent)
        skill = await loader.load_skill("test-skill", disclosure_level=2)

        assert skill is not None
        assert skill.name == "test-skill"
        assert "# Test Skill" in skill.body
        assert "Do thing one" in skill.body
        # At level 2, resources should not be loaded
        assert skill.resources == []

    @pytest.mark.asyncio
    async def test_load_skill_level_3_full(self, complete_skill_dir: Path) -> None:
        """Test level 3 disclosure includes all resources."""
        loader = SkillLoader(skills_dir=complete_skill_dir.parent)
        skill = await loader.load_skill("complete-skill", disclosure_level=3)

        assert skill is not None
        assert len(skill.resources) == 3

        # Check resource types
        resource_types = {r.type for r in skill.resources}
        assert ResourceType.SCRIPT in resource_types
        assert ResourceType.REFERENCE in resource_types
        assert ResourceType.TEMPLATE in resource_types

        # Check content is loaded
        for resource in skill.resources:
            assert resource.content is not None
            assert len(resource.content) > 0

    @pytest.mark.asyncio
    async def test_load_nonexistent_skill(self, skill_dir: Path) -> None:
        """Test loading a non-existent skill returns None."""
        loader = SkillLoader(skills_dir=skill_dir.parent)
        skill = await loader.load_skill("nonexistent-skill")

        assert skill is None

    @pytest.mark.asyncio
    async def test_load_skill_default_level_is_2(self, skill_dir: Path) -> None:
        """Test default disclosure level is 2."""
        loader = SkillLoader(skills_dir=skill_dir.parent)
        skill = await loader.load_skill("test-skill")

        assert skill is not None
        assert "# Test Skill" in skill.body
        assert skill.resources == []


class TestSkillLoaderCaching:
    """Tests for skill caching functionality."""

    @pytest.mark.asyncio
    async def test_skill_caching(self, skill_dir: Path) -> None:
        """Test that loaded skills are cached."""
        loader = SkillLoader(skills_dir=skill_dir.parent)

        # First load
        skill1 = await loader.load_skill("test-skill", disclosure_level=2)

        # Second load should return cached version
        skill2 = await loader.load_skill("test-skill", disclosure_level=2)

        assert skill1 is skill2  # Same object due to caching

    @pytest.mark.asyncio
    async def test_cache_by_disclosure_level(self, skill_dir: Path) -> None:
        """Test that different disclosure levels are cached separately."""
        loader = SkillLoader(skills_dir=skill_dir.parent)

        # Load at level 1
        skill_l1 = await loader.load_skill("test-skill", disclosure_level=1)

        # Load at level 2
        skill_l2 = await loader.load_skill("test-skill", disclosure_level=2)

        # Should be different objects with different content
        assert skill_l1 is not skill_l2
        assert skill_l1.body == ""
        assert skill_l2.body != ""

    @pytest.mark.asyncio
    async def test_clear_cache(self, skill_dir: Path) -> None:
        """Test cache clearing functionality."""
        loader = SkillLoader(skills_dir=skill_dir.parent)

        # Load and cache
        skill1 = await loader.load_skill("test-skill")

        # Clear cache
        loader.clear_cache()

        # Load again - should be a new object
        skill2 = await loader.load_skill("test-skill")

        assert skill1 is not skill2


class TestSkillLoaderResources:
    """Tests for resource loading functionality."""

    @pytest.mark.asyncio
    async def test_load_specific_resource(self, complete_skill_dir: Path) -> None:
        """Test loading a specific resource from a skill."""
        loader = SkillLoader(skills_dir=complete_skill_dir.parent)

        content = await loader.load_resource("complete-skill", "references/guide.md")

        assert content is not None
        assert "# Guide" in content
        assert "Detailed guide content" in content

    @pytest.mark.asyncio
    async def test_load_resource_nonexistent_skill(self, complete_skill_dir: Path) -> None:
        """Test loading resource from non-existent skill returns None."""
        loader = SkillLoader(skills_dir=complete_skill_dir.parent)

        content = await loader.load_resource("nonexistent-skill", "any.md")

        assert content is None

    @pytest.mark.asyncio
    async def test_load_resource_nonexistent_file(self, complete_skill_dir: Path) -> None:
        """Test loading non-existent resource returns None."""
        loader = SkillLoader(skills_dir=complete_skill_dir.parent)

        content = await loader.load_resource("complete-skill", "nonexistent.md")

        assert content is None

    @pytest.mark.asyncio
    async def test_resource_type_detection(self, complete_skill_dir: Path) -> None:
        """Test that resource types are correctly detected."""
        loader = SkillLoader(skills_dir=complete_skill_dir.parent)
        skill = await loader.load_skill("complete-skill", disclosure_level=3)

        assert skill is not None

        # Find each resource type
        script = next((r for r in skill.resources if r.path.startswith("scripts/")), None)
        reference = next((r for r in skill.resources if r.path.startswith("references/")), None)
        template = next((r for r in skill.resources if r.path.startswith("templates/")), None)

        assert script is not None
        assert script.type == ResourceType.SCRIPT

        assert reference is not None
        assert reference.type == ResourceType.REFERENCE

        assert template is not None
        assert template.type == ResourceType.TEMPLATE


class TestSkillLoaderEdgeCases:
    """Tests for edge cases and error handling."""

    @pytest.mark.asyncio
    async def test_invalid_yaml_frontmatter(self, tmp_path: Path) -> None:
        """Test handling of invalid YAML frontmatter."""
        skill_path = tmp_path / "bad-skill"
        skill_path.mkdir()
        # No frontmatter at all - just plain markdown
        (skill_path / "SKILL.md").write_text("""# No Frontmatter

This skill has no YAML frontmatter at all.
Just plain markdown content.
""")

        loader = SkillLoader(skills_dir=tmp_path)
        skills = await loader.discover_skills()

        # Should skip skills with invalid frontmatter
        assert len(skills) == 0

    @pytest.mark.asyncio
    async def test_empty_skill_md(self, tmp_path: Path) -> None:
        """Test handling of empty SKILL.md file."""
        skill_path = tmp_path / "empty-skill"
        skill_path.mkdir()
        (skill_path / "SKILL.md").write_text("")

        loader = SkillLoader(skills_dir=tmp_path)
        skills = await loader.discover_skills()

        # Should skip empty skills
        assert len(skills) == 0

    @pytest.mark.asyncio
    async def test_nonexistent_skills_directory(self, tmp_path: Path) -> None:
        """Test handling of non-existent skills directory."""
        nonexistent = tmp_path / "does-not-exist"
        loader = SkillLoader(skills_dir=nonexistent)
        skills = await loader.discover_skills()

        assert skills == []

    @pytest.mark.asyncio
    async def test_skill_with_nested_resources(self, tmp_path: Path) -> None:
        """Test loading skills with nested resource directories."""
        skill_path = tmp_path / "nested-skill"
        skill_path.mkdir()

        (skill_path / "SKILL.md").write_text("""---
name: nested-skill
description: Skill with nested resources.
---

# Nested Skill

Has nested reference structure.
""")

        # Create nested references
        refs = skill_path / "references"
        refs.mkdir()
        (refs / "main.md").write_text("# Main Reference")

        nested = refs / "sub"
        nested.mkdir()
        (nested / "detail.md").write_text("# Detailed Reference")

        loader = SkillLoader(skills_dir=tmp_path)
        skill = await loader.load_skill("nested-skill", disclosure_level=3)

        assert skill is not None
        # Should find both main and nested resources
        resource_paths = {r.path for r in skill.resources}
        assert "references/main.md" in resource_paths
        assert "references/sub/detail.md" in resource_paths


class TestSkillLoaderPathTraversal:
    """Test that path traversal attacks are blocked."""

    @pytest.fixture
    def loader_with_skill(self, tmp_path: Path):
        """Create a loader with a real skill directory."""
        skill_dir = tmp_path / "my-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: my-skill\ndescription: test\n---\nBody")
        refs_dir = skill_dir / "references"
        refs_dir.mkdir()
        (refs_dir / "api.md").write_text("API docs")
        # Create a file outside the skill directory
        (tmp_path / "secret.txt").write_text("top secret")
        return SkillLoader(tmp_path)

    @pytest.mark.asyncio
    async def test_path_traversal_blocked(self, loader_with_skill):
        result = await loader_with_skill.load_resource("my-skill", "../../secret.txt")
        assert result is None

    @pytest.mark.asyncio
    async def test_path_traversal_dotdot_blocked(self, loader_with_skill):
        result = await loader_with_skill.load_resource("my-skill", "../secret.txt")
        assert result is None

    @pytest.mark.asyncio
    async def test_valid_resource_still_works(self, loader_with_skill):
        result = await loader_with_skill.load_resource("my-skill", "references/api.md")
        assert result == "API docs"
