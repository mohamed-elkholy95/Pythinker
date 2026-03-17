"""Skill discovery middleware — scans filesystem skill directories at runtime.

Reads SKILL.md frontmatter from public/ and custom/ category directories,
then injects a formatted skill listing into the RuntimeContext metadata so
downstream middlewares and the agent system prompt can advertise available skills.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware

logger = logging.getLogger(__name__)

# Matches a YAML frontmatter block at the start of a file (--- ... ---).
_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)

# Ordered category subdirectory names to scan
_CATEGORIES = ("public", "custom")


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class SkillSummary:
    """Lightweight skill descriptor extracted from SKILL.md frontmatter."""

    name: str
    description: str
    category: str
    path: str

    def to_prompt_entry(self) -> str:
        """Return a single-line prompt-ready representation of this skill."""
        return f"  - {self.name}: {self.description} [{self.category}]"


# ---------------------------------------------------------------------------
# Frontmatter parser
# ---------------------------------------------------------------------------


def _parse_frontmatter(path: Path) -> dict[str, Any] | None:
    """Read *path* and parse its YAML frontmatter block.

    Args:
        path: Absolute path to a SKILL.md file.

    Returns:
        Parsed frontmatter as a dict, or None on any read/parse error.
    """
    try:
        content = path.read_text(encoding="utf-8")
        match = _FRONTMATTER_RE.match(content)
        if not match:
            logger.debug("No YAML frontmatter found in %s", path)
            return None
        return yaml.safe_load(match.group(1)) or {}
    except Exception as exc:
        logger.warning("Failed to parse frontmatter in %s: %s", path, exc)
        return None


# ---------------------------------------------------------------------------
# Directory scanner
# ---------------------------------------------------------------------------


def scan_skill_directories(root: Path) -> list[SkillSummary]:
    """Scan *root*/{public,custom}/ for skill directories containing SKILL.md.

    Each immediate child directory of a category directory that contains a
    ``SKILL.md`` file is treated as a skill.  The YAML frontmatter is parsed
    to extract *name* and *description* fields.

    Args:
        root: Root skills directory.  Expected layout::

            root/
              public/
                web-research/
                  SKILL.md
              custom/
                my-skill/
                  SKILL.md

    Returns:
        Sorted (by directory name) list of :class:`SkillSummary` objects.
        Empty list when no skills are found or the root does not exist.
    """
    summaries: list[SkillSummary] = []

    for category in _CATEGORIES:
        category_dir = root / category
        if not category_dir.is_dir():
            continue

        for skill_dir in sorted(category_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                logger.debug("Skipping %s: no SKILL.md", skill_dir)
                continue

            meta = _parse_frontmatter(skill_md)
            if meta is None:
                continue

            name = str(meta.get("name") or skill_dir.name)
            description = str(meta.get("description") or "")

            summaries.append(
                SkillSummary(
                    name=name,
                    description=description,
                    category=category,
                    path=str(skill_md),
                )
            )

    return sorted(summaries, key=lambda s: s.name)


# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------


class SkillDiscoveryMiddleware(RuntimeMiddleware):
    """Runtime middleware that discovers skills from the filesystem.

    On ``before_run``, scans the configured *skills_root* directory and injects:

    - ``ctx.metadata["discovered_skills"]``: list of :class:`SkillSummary`
    - ``ctx.metadata["skill_prompt_section"]``: XML-formatted string ready for
      inclusion in the agent system prompt.

    Args:
        skills_root: Path to the root skills directory.  Pass ``None`` (or omit)
            to disable scanning — the middleware becomes a no-op.
    """

    def __init__(self, skills_root: Path | str | None = None) -> None:
        self._root: Path | None = Path(skills_root) if skills_root is not None else None

    async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
        """Scan skill directories and populate context metadata."""
        if self._root is None or not self._root.is_dir():
            logger.debug(
                "SkillDiscoveryMiddleware: root not set or does not exist (%s) — skipping",
                self._root,
            )
            return ctx

        skills = scan_skill_directories(self._root)
        ctx.metadata["discovered_skills"] = skills
        ctx.metadata["skill_prompt_section"] = self._format_skill_section(skills)
        logger.info(
            "SkillDiscoveryMiddleware: discovered %d skill(s) in %s",
            len(skills),
            self._root,
        )
        return ctx

    @staticmethod
    def _format_skill_section(skills: list[SkillSummary]) -> str:
        """Render *skills* as an XML ``<available_skills>`` block.

        Args:
            skills: Skills to render.

        Returns:
            Multi-line XML string, or an empty ``<available_skills>`` tag when
            *skills* is empty.
        """
        if not skills:
            return "<available_skills>\n</available_skills>"

        entries = "\n".join(skill.to_prompt_entry() for skill in skills)
        return f"<available_skills>\n{entries}\n</available_skills>"
