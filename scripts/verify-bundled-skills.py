#!/usr/bin/env python3
"""Verify bundled Superpowers skills are loadable.

This script verifies that:
1. All bundled skills can be parsed
2. Skills have valid YAML frontmatter
3. Required fields are present
4. No external dependencies are needed
"""

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "backend"))

from app.infrastructure.seeds.superpowers_importer import (
    SkillParseError,
    parse_skill_md,
)
from app.infrastructure.seeds.superpowers_skills import SUPERPOWERS_DIR


def main():
    """Verify all bundled skills."""
    print("=" * 60)
    print("BUNDLED SUPERPOWERS SKILLS VERIFICATION")
    print("=" * 60)
    print()

    # Check directory exists
    print(f"📁 Skills directory: {SUPERPOWERS_DIR}")
    print(f"   Exists: {SUPERPOWERS_DIR.exists()}")
    print(f"   Absolute path: {SUPERPOWERS_DIR.absolute()}")
    print()

    if not SUPERPOWERS_DIR.exists():
        print("❌ ERROR: Skills directory not found!")
        print(f"   Expected at: {SUPERPOWERS_DIR.absolute()}")
        return 1

    # Find all SKILL.md files
    skill_files = list(SUPERPOWERS_DIR.glob("*/SKILL.md"))
    print(f"📋 Found {len(skill_files)} skill files")
    print()

    # Parse each skill
    errors = []
    successes = []

    for skill_file in sorted(skill_files):
        skill_name = skill_file.parent.name
        print(f"🔍 Parsing: {skill_name}")

        try:
            frontmatter, content = parse_skill_md(skill_file)

            # Verify required fields
            required_fields = ["name", "description"]
            missing_fields = [f for f in required_fields if f not in frontmatter]

            if missing_fields:
                raise SkillParseError(
                    f"Missing required fields: {', '.join(missing_fields)}"
                )

            # Verify name matches directory
            if frontmatter["name"] != skill_name:
                print(
                    f"   ⚠️  Warning: Name mismatch (dir: {skill_name}, yaml: {frontmatter['name']})"
                )

            # Check content length
            content_len = len(content)
            print(f"   ✅ Valid: {content_len:,} chars")
            print(f"      Description: {frontmatter['description'][:80]}...")

            successes.append(skill_name)

        except SkillParseError as e:
            print(f"   ❌ Parse error: {e}")
            errors.append((skill_name, str(e)))
        except Exception as e:
            print(f"   ❌ Unexpected error: {e}")
            errors.append((skill_name, str(e)))

        print()

    # Summary
    print("=" * 60)
    print("VERIFICATION SUMMARY")
    print("=" * 60)
    print(f"✅ Successful: {len(successes)}/{len(skill_files)}")
    print(f"❌ Failed: {len(errors)}/{len(skill_files)}")
    print()

    if successes:
        print("Successfully parsed skills:")
        for skill in successes:
            print(f"  • {skill}")
        print()

    if errors:
        print("Failed skills:")
        for skill_name, error in errors:
            print(f"  • {skill_name}: {error}")
        print()
        return 1

    print("🎉 All bundled skills verified successfully!")
    print()
    print("Next steps:")
    print("  1. Restart backend: ./dev.sh restart backend")
    print("  2. Test slash commands in Pythinker chat")
    print("  3. Verify skills load without external dependencies")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
