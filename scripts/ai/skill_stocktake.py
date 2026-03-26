from __future__ import annotations

import json
import re
from itertools import combinations
from pathlib import Path


FRONTMATTER_PATTERN = re.compile(r"\A---\n(.*?)\n---\n?", re.DOTALL)
FIELD_PATTERN = re.compile(r"^(name|description):\s*(.+)$", re.MULTILINE)


def _parse_frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_PATTERN.match(text)
    if not match:
        return {}
    frontmatter = match.group(1)
    return {key: value.strip() for key, value in FIELD_PATTERN.findall(frontmatter)}


def _normalize_words(text: str) -> set[str]:
    return {word for word in re.findall(r"[a-z0-9]+", text.lower()) if len(word) > 2}


def _inventory_skills(skills_root: Path) -> list[dict[str, str]]:
    skills: list[dict[str, str]] = []
    for skill_file in sorted(skills_root.glob("*/SKILL.md")):
        text = skill_file.read_text(encoding="utf-8")
        meta = _parse_frontmatter(text)
        skills.append(
            {
                "path": str(skill_file),
                "name": meta.get("name", ""),
                "description": meta.get("description", ""),
            }
        )
    return skills


def stocktake_skills(skills_root: Path) -> dict[str, object]:
    skills_root = skills_root.resolve()
    if not skills_root.exists():
        return {"skills": [], "warnings": [f"{skills_root} does not exist"]}

    skills = _inventory_skills(skills_root)
    warnings: list[str] = []

    for skill in skills:
        if not skill["name"]:
            warnings.append(f"{skill['path']}: missing name")
        if not skill["description"]:
            warnings.append(f"{skill['path']}: missing description")

    for left, right in combinations(skills, 2):
        left_words = _normalize_words(f"{left['name']} {left['description']}")
        right_words = _normalize_words(f"{right['name']} {right['description']}")
        if not left_words or not right_words:
            continue
        intersection = left_words & right_words
        union = left_words | right_words
        similarity = len(intersection) / len(union)
        if (
            left["description"]
            and left["description"] == right["description"]
            or similarity >= 0.8
        ):
            warnings.append(
                f"Potential overlap: {Path(left['path']).parent.name} vs {Path(right['path']).parent.name}"
            )

    return {"skills": skills, "warnings": warnings}


def main() -> None:
    print(json.dumps(stocktake_skills(Path.cwd() / "skills"), indent=2))


if __name__ == "__main__":
    main()
