"""External Skill Importer — fetch and validate AgentSkills-compatible packages.

Supports importing skills from:
- Raw SKILL.md URLs (single-file skills)
- GitHub repository paths (directory-based skills)
- Zip archive URLs (full skill packages with scripts/references)

All fetching goes through HTTPClientPool (project-wide connection pooling policy).
All external URLs are validated against the project's SSRF guard before fetching.
All imported skills are validated with skills-ref before persisting.

Architecture notes:
- This lives in infrastructure/external/ because it deals with network I/O
  and third-party HTTP — classic infrastructure concern.
- The returned Skill domain objects are passed up to the application layer;
  this module never writes to MongoDB directly.
- Temp directories are always cleaned up via TemporaryDirectory context managers.
"""

from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import tempfile
import zipfile
from pathlib import Path
from typing import Any

import aiofiles

from app.domain.models.skill import Skill, SkillCategory, SkillSource
from app.domain.utils.url_filters import is_ssrf_target
from app.infrastructure.external.http_pool import HTTPClientPool

logger = logging.getLogger(__name__)

# Optional skills-ref for validation
try:
    from skills_ref.parser import read_properties as _agentskills_read_properties
    from skills_ref.validator import validate as _agentskills_validate

    _AGENTSKILLS_AVAILABLE = True
except ImportError:
    _AGENTSKILLS_AVAILABLE = False


_GITHUB_API_BASE = "https://api.github.com"

# Reasonable limits to prevent DoS via large skill archives or deep trees
_MAX_SKILL_ARCHIVE_BYTES = 10 * 1024 * 1024  # 10 MB
_MAX_SKILL_FILES = 100

# Fixed pool name for all ad-hoc external URL fetches — prevents pool
# pollution from user-supplied hostnames filling the 100-entry HTTPClientPool.
_EXTERNAL_IMPORT_POOL_NAME = "skill-import-external"


class SkillImportError(Exception):
    """Raised when a skill cannot be imported."""


class ExternalSkillImporter:
    """Fetches and validates AgentSkills-compatible skills from external sources.

    All HTTP operations use HTTPClientPool (project connection pooling policy).
    All external URLs are checked with is_ssrf_target() before any fetch.
    Validation uses the skills-ref library (AgentSkills open standard).

    Example::

        importer = ExternalSkillImporter()

        # Import from a GitHub repository path
        skill = await importer.import_from_github(
            repo="anthropics/skills",
            path="pdf-processing",
        )

        # Import from a raw URL
        skill = await importer.import_from_url("https://example.com/my-skill/SKILL.md")

        # Import a zip archive
        skill = await importer.import_from_zip_url("https://example.com/my-skill.zip")
    """

    def __init__(self, http_timeout: float = 30.0) -> None:
        self._timeout = http_timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def import_from_github(
        self,
        repo: str,
        path: str = "",
        ref: str = "main",
        category: SkillCategory = SkillCategory.CUSTOM,
    ) -> Skill:
        """Import a skill from a GitHub repository directory.

        Fetches all files in the skill directory via the GitHub Contents API,
        then writes them to a temporary directory for validation.

        Args:
            repo: Repository in ``owner/repo`` format (e.g. ``"anthropics/skills"``).
            path: Path inside the repo to the skill directory (e.g. ``"pdf-processing"``).
            ref: Git branch, tag, or commit SHA. Defaults to ``"main"``.
            category: Pythinker category to assign. Defaults to CUSTOM.

        Returns:
            Validated Skill domain object ready for persistence.

        Raises:
            SkillImportError: If the skill cannot be fetched or fails validation.
        """
        api_path = f"/repos/{repo}/contents/{path}".rstrip("/")
        api_url = f"{_GITHUB_API_BASE}{api_path}?ref={ref}"
        logger.info(f"Importing skill from GitHub: {repo}/{path}@{ref}")

        client = await HTTPClientPool.get_client(
            "github-api",
            base_url=_GITHUB_API_BASE,
            timeout=self._timeout,
            headers={"Accept": "application/vnd.github.v3+json"},
        )

        response = await client.get(api_url)
        if response.status_code == 404:
            raise SkillImportError(f"GitHub path not found: {repo}/{path}@{ref}")
        if response.status_code != 200:
            raise SkillImportError(f"GitHub API error {response.status_code}: {response.text[:200]}")

        entries: list[dict[str, Any]] = response.json()
        if not isinstance(entries, list):
            # Single file returned — wrap so we can treat it uniformly
            entries = [entries]

        with tempfile.TemporaryDirectory(prefix="pythinker-skill-") as tmp_str:
            tmp_dir = Path(tmp_str)
            # Shared mutable counter prevents unbounded recursion across dirs
            file_counter: list[int] = [0]
            await self._download_github_entries(entries, tmp_dir, repo, ref, file_counter)
            return await self._build_skill_from_dir(tmp_dir, category, source=SkillSource.COMMUNITY)

    async def import_from_url(
        self,
        url: str,
        category: SkillCategory = SkillCategory.CUSTOM,
    ) -> Skill:
        """Import a skill from a direct SKILL.md URL.

        The URL should point to a raw SKILL.md file.  A minimal skill
        directory (containing only SKILL.md) will be created for validation.

        Args:
            url: Direct URL to the raw SKILL.md content.
            category: Pythinker category to assign. Defaults to CUSTOM.

        Returns:
            Validated Skill domain object.

        Raises:
            SkillImportError: On SSRF-blocked URLs, HTTP errors, or validation failures.
        """
        # SSRF guard — blocks private IPs, localhost, cloud metadata, Docker services
        ssrf_reason = is_ssrf_target(url)
        if ssrf_reason:
            raise SkillImportError(f"URL blocked by SSRF protection: {ssrf_reason}")

        logger.info(f"Importing skill from URL: {url}")
        client = await HTTPClientPool.get_client(
            _EXTERNAL_IMPORT_POOL_NAME,
            timeout=self._timeout,
        )
        response = await client.get(url)
        if response.status_code != 200:
            raise SkillImportError(f"Failed to fetch SKILL.md: HTTP {response.status_code}")

        content = response.text
        if not content.strip():
            raise SkillImportError("Empty SKILL.md content received")

        with tempfile.TemporaryDirectory(prefix="pythinker-skill-") as tmp_str:
            tmp_dir = Path(tmp_str)
            skill_md = tmp_dir / "SKILL.md"
            async with aiofiles.open(skill_md, "w", encoding="utf-8") as f:
                await f.write(content)
            return await self._build_skill_from_dir(tmp_dir, category, source=SkillSource.COMMUNITY)

    async def import_from_zip_url(
        self,
        url: str,
        skill_subpath: str = "",
        category: SkillCategory = SkillCategory.CUSTOM,
    ) -> Skill:
        """Import a skill from a zip archive URL.

        Downloads the archive, extracts it, then locates SKILL.md for
        validation.  Handles GitHub-style "Download ZIP" URLs.

        Args:
            url: URL to a ``.zip`` archive containing the skill.
            skill_subpath: Optional sub-directory inside the zip where the
                           skill lives (e.g. ``"pdf-processing/"``).
            category: Pythinker category to assign. Defaults to CUSTOM.

        Returns:
            Validated Skill domain object.

        Raises:
            SkillImportError: On SSRF-blocked URLs, HTTP errors, oversized
                              archives, or validation failures.
        """
        # SSRF guard — blocks private IPs, localhost, cloud metadata, Docker services
        ssrf_reason = is_ssrf_target(url)
        if ssrf_reason:
            raise SkillImportError(f"URL blocked by SSRF protection: {ssrf_reason}")

        logger.info(f"Importing skill from ZIP: {url}")
        client = await HTTPClientPool.get_client(
            _EXTERNAL_IMPORT_POOL_NAME,
            timeout=self._timeout,
        )
        response = await client.get(url)
        if response.status_code != 200:
            raise SkillImportError(f"Failed to fetch zip archive: HTTP {response.status_code}")

        content_bytes = response.content
        if len(content_bytes) > _MAX_SKILL_ARCHIVE_BYTES:
            raise SkillImportError(
                f"Skill archive too large: {len(content_bytes)} bytes (max {_MAX_SKILL_ARCHIVE_BYTES})"
            )

        with tempfile.TemporaryDirectory(prefix="pythinker-skill-") as tmp_str:
            tmp_dir = Path(tmp_str)
            await self._extract_zip(content_bytes, tmp_dir)

            # Find the SKILL.md — prefer skill_subpath if given
            skill_dir = await self._locate_skill_dir(tmp_dir, skill_subpath)
            return await self._build_skill_from_dir(skill_dir, category, source=SkillSource.COMMUNITY)

    async def validate_skill_dir(self, skill_dir: Path) -> list[str]:
        """Validate a skill directory against the AgentSkills standard.

        Wraps ``skills_ref.validator.validate()`` in an executor so it
        doesn't block the event loop.

        Args:
            skill_dir: Path to the skill directory containing ``SKILL.md``.

        Returns:
            List of validation error strings.  Empty list means valid.
        """
        if not _AGENTSKILLS_AVAILABLE:
            logger.debug("skills-ref not installed; skipping AgentSkills validation")
            return []

        try:
            loop = asyncio.get_running_loop()
            errors: list[str] = await loop.run_in_executor(None, _agentskills_validate, skill_dir)
            return errors
        except Exception as e:
            logger.warning(f"AgentSkills validation error: {e}")
            return [str(e)]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _build_skill_from_dir(
        self,
        skill_dir: Path,
        category: SkillCategory,
        source: SkillSource = SkillSource.COMMUNITY,
    ) -> Skill:
        """Validate a temp skill directory and construct a Skill domain object.

        Args:
            skill_dir: Directory containing SKILL.md (and optional sub-dirs).
            category: Pythinker SkillCategory to assign.
            source: Pythinker SkillSource (defaults to COMMUNITY).

        Returns:
            Populated Skill domain object.

        Raises:
            SkillImportError: If SKILL.md is missing or validation fails hard.
        """
        skill_md = skill_dir / "SKILL.md"
        if not skill_md.exists():
            raise SkillImportError(f"No SKILL.md found in skill directory: {skill_dir}")

        # Run AgentSkills standard validation
        errors = await self.validate_skill_dir(skill_dir)
        if errors:
            # Log all errors; raise on critical ones (missing required fields)
            for err in errors:
                logger.warning(f"[AgentSkills validation] {err}")
            critical = [e for e in errors if "name" in e.lower() or "description" in e.lower()]
            if critical:
                raise SkillImportError(f"Skill failed AgentSkills validation: {'; '.join(critical)}")

        # Read properties using skills-ref if available
        if _AGENTSKILLS_AVAILABLE:
            try:
                loop = asyncio.get_running_loop()
                props = await loop.run_in_executor(None, _agentskills_read_properties, skill_dir)
                skill_name = props.name
                description = props.description
                author = (props.metadata or {}).get("author")
                version = (props.metadata or {}).get("version", "1.0.0")
                raw_tags = (props.metadata or {}).get("tags", "")
                tags = (
                    [t.strip() for t in re.split(r"[,\s]+", raw_tags) if t.strip()]
                    if isinstance(raw_tags, str)
                    else list(raw_tags or [])
                )
                raw_tools = props.allowed_tools or ""
                allowed_tools = raw_tools.split() if raw_tools.strip() else []
            except Exception as e:
                logger.warning(f"skills-ref read_properties failed ({e}); using regex fallback")
                skill_name, description, author, version, tags, allowed_tools = await self._parse_skill_md_fallback(
                    skill_md
                )
        else:
            skill_name, description, author, version, tags, allowed_tools = await self._parse_skill_md_fallback(
                skill_md
            )

        if not skill_name:
            raise SkillImportError("Skill has no name in frontmatter")

        logger.info(f"Successfully imported skill '{skill_name}' from external source")

        return Skill(
            id=skill_name,
            name=skill_name,
            description=description,
            category=category,
            source=source,
            author=author,
            version=version,
            tags=tags,
            allowed_tools=allowed_tools or None,
        )

    async def _parse_skill_md_fallback(self, skill_md: Path) -> tuple[str, str, str | None, str, list[str], list[str]]:
        """Minimal SKILL.md parser used when skills-ref is unavailable.

        Returns:
            Tuple of (name, description, author, version, tags, allowed_tools).
        """
        async with aiofiles.open(skill_md, encoding="utf-8") as f:
            content = await f.read()

        name_match = re.search(r"^name:\s*(.+)$", content, re.MULTILINE)
        desc_match = re.search(r"^description:\s*(.+)$", content, re.MULTILINE)
        author_match = re.search(r"^\s+author:\s*(.+)$", content, re.MULTILINE)
        version_match = re.search(r"^\s+version:\s*(.+)$", content, re.MULTILINE)

        return (
            name_match.group(1).strip() if name_match else "",
            desc_match.group(1).strip() if desc_match else "",
            author_match.group(1).strip() if author_match else None,
            version_match.group(1).strip() if version_match else "1.0.0",
            [],  # tags
            [],  # allowed_tools
        )

    async def _download_github_entries(
        self,
        entries: list[dict[str, Any]],
        dest_dir: Path,
        repo: str,
        ref: str,
        file_counter: list[int],
    ) -> None:
        """Download GitHub directory contents into dest_dir.

        Recursively fetches files and subdirectories.  The ``file_counter``
        list is shared (mutable) across all recursion levels so the
        ``_MAX_SKILL_FILES`` limit is truly global, not per-directory.

        Args:
            entries: List of GitHub Contents API entry dicts.
            dest_dir: Local directory to write files into.
            repo: ``owner/repo`` string (for sub-directory API calls).
            ref: Git ref for sub-directory lookups.
            file_counter: Single-element list ``[n]`` tracking total files
                          downloaded across all recursive calls.
        """
        client = await HTTPClientPool.get_client(
            "github-api",
            base_url=_GITHUB_API_BASE,
            timeout=self._timeout,
            headers={"Accept": "application/vnd.github.v3+json"},
        )

        for entry in entries:
            if file_counter[0] >= _MAX_SKILL_FILES:
                logger.warning(f"Reached global max file limit ({_MAX_SKILL_FILES}); stopping download")
                return

            entry_type = entry.get("type")
            entry_name = entry.get("name", "")
            dest_path = dest_dir / entry_name

            if entry_type == "file":
                download_url = entry.get("download_url")
                if not download_url:
                    continue
                # SSRF guard on API-supplied download URLs (defense-in-depth)
                ssrf_reason = is_ssrf_target(download_url)
                if ssrf_reason:
                    logger.warning(f"Skipping download_url blocked by SSRF guard: {ssrf_reason}")
                    continue
                raw_resp = await client.get(download_url)
                if raw_resp.status_code == 200:
                    async with aiofiles.open(dest_path, "w", encoding="utf-8") as f:
                        await f.write(raw_resp.text)
                    file_counter[0] += 1

            elif entry_type == "dir":
                dest_path.mkdir(parents=True, exist_ok=True)
                sub_url = f"{_GITHUB_API_BASE}/repos/{repo}/contents/{entry['path']}?ref={ref}"
                sub_resp = await client.get(sub_url)
                if sub_resp.status_code == 200:
                    sub_entries = sub_resp.json()
                    if isinstance(sub_entries, list):
                        # Pass the same mutable counter into the recursive call
                        await self._download_github_entries(sub_entries, dest_path, repo, ref, file_counter)

    async def _extract_zip(self, content_bytes: bytes, dest_dir: Path) -> None:
        """Extract a zip archive into dest_dir, blocking zip-slip attacks.

        Checks each member's resolved destination path before extraction to
        prevent directory traversal via ``..`` components, absolute paths,
        backslash separators, and symlink-based escapes.

        Args:
            content_bytes: Raw zip archive bytes.
            dest_dir: Destination directory (already exists).
        """
        dest_abs = os.path.abspath(dest_dir)

        def _do_extract() -> None:
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as zf:
                for member in zf.infolist():
                    # os.path.abspath(join) normalises ".." in string space —
                    # no filesystem I/O needed, so works before the file exists.
                    member_abs = os.path.abspath(os.path.join(dest_abs, member.filename))
                    if not member_abs.startswith(dest_abs + os.sep) and member_abs != dest_abs:
                        raise SkillImportError(f"Zip-slip attempt blocked: '{member.filename}' escapes archive root")
                    zf.extract(member, dest_dir)

        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, _do_extract)

    async def _locate_skill_dir(self, base_dir: Path, skill_subpath: str) -> Path:
        """Find the skill directory inside an extracted archive.

        If ``skill_subpath`` is given and valid, use it directly.
        Otherwise, walk the extracted tree to find the directory containing
        SKILL.md.

        Args:
            base_dir: Root of the extracted archive.
            skill_subpath: Optional sub-path hint (e.g. ``"my-skill/"``).

        Returns:
            Path to the directory containing ``SKILL.md``.

        Raises:
            SkillImportError: If no SKILL.md can be located.
        """
        if skill_subpath:
            candidate = base_dir / skill_subpath
            if (candidate / "SKILL.md").exists():
                return candidate

        # Walk and find first SKILL.md
        def _find() -> Path | None:
            for skill_md in base_dir.rglob("SKILL.md"):
                return skill_md.parent
            return None

        loop = asyncio.get_running_loop()
        found = await loop.run_in_executor(None, _find)
        if not found:
            raise SkillImportError("No SKILL.md found in extracted archive")
        return found


def get_external_skill_importer() -> ExternalSkillImporter:
    """Return a singleton-style importer instance.

    No real state is held, so creating one per request is also fine.
    """
    return ExternalSkillImporter()
