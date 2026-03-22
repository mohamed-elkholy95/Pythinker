# Comprehensive Skills System Enhancement Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Transform Pythinker's skills system into a world-class, community-driven skill ecosystem with OpenClaw Hub integration, improved user skill management, streamlined nanobot-backend skill bridge, and a full skill marketplace experience.

**Architecture:** Extend existing DDD layers (domain/application/infrastructure/interfaces) to support federated skill sources (local DB, OpenClaw Hub, SkillKit API), add skill import/export, enhance the nanobot `SkillsLoader` to pull from the backend DB, and build a skill marketplace UI in the Vue frontend. No new infrastructure services — reuse MongoDB + Redis + existing HTTP client pooling.

**Tech Stack:** Python 3.12+ (FastAPI, Pydantic v2, Motor/Beanie), Vue 3 Composition API + TypeScript, SKILL.md format (YAML frontmatter + Markdown body), ClawHub CLI (`npx clawhub@latest`), SkillKit API (localhost:3737)

---

## Current State Analysis

### What Exists (73 files)

**Backend Domain Layer:**
- `backend/app/domain/models/skill.py` — `Skill`, `SkillMetadata`, `SkillResource`, `UserSkillConfig` models with progressive disclosure (L1/L2/L3), marketplace fields (ratings, tags, fork support), Claude-style invocation types
- `backend/app/domain/repositories/skill_repository.py` — `SkillRepository` Protocol
- `backend/app/domain/services/skill_loader.py` — Filesystem `SkillLoader` with AgentSkills standard compliance (`skills-ref` library), progressive disclosure, resource loading
- `backend/app/domain/services/skill_registry.py` — Singleton `SkillRegistry` with TTL caching, trigger pattern compilation, context building
- `backend/app/domain/services/skill_activation_framework.py` — `SkillActivationFramework` for explicit/controlled skill activation (chat selection, slash commands, auto-trigger)
- `backend/app/domain/services/skill_trigger_matcher.py` — Pattern-based auto-trigger matching
- `backend/app/domain/services/skill_validator.py` — `CustomSkillValidator` for user-created skills
- `backend/app/domain/services/command_registry.py` — Slash command registry (`/brainstorm`, `/design`, etc.)
- `backend/app/domain/services/skill_matcher.py` — Skill matching for plan-act flows
- `backend/app/domain/services/skill_packager.py` — ZIP packaging for skill export
- `backend/app/domain/services/tools/skill_tools.py` — `ListSkillsTool`, `ReadSkillTool` agent tools
- `backend/app/domain/services/tools/skill_creator.py` — AI-assisted skill creation tool
- `backend/app/domain/services/tools/skill_invoke.py` — Skill invocation tool
- `backend/app/domain/services/tools/github_skill_seeker.py` — Search GitHub for skills
- `backend/app/domain/services/runtime/skill_discovery_middleware.py` — Runtime middleware that scans filesystem skills
- `backend/app/domain/services/prompts/skill_context.py` — Build system prompt additions from skills
- `backend/app/domain/services/skills/init_skill.py` — Skill initialization
- `backend/app/domain/services/skills/skill_validator.py` — Additional skill validation
- `backend/app/domain/models/skill_package.py` — `SkillPackage`, `SkillPackageFile` models

**Backend Application Layer:**
- `backend/app/application/services/skill_service.py` — `SkillService` with CRUD, user skill configs, seeding

**Backend Infrastructure Layer:**
- `backend/app/infrastructure/repositories/mongo_skill_repository.py` — Full MongoDB implementation with marketplace search, ratings (atomic aggregation), fork, publish/unpublish, feature flagging
- `backend/app/infrastructure/plugins/skill_plugin_loader.py` — Plugin-based skill loading
- `backend/app/infrastructure/seeds/skills_seed.py` — Official skills seed data
- `backend/app/infrastructure/models/documents.py` — `SkillDocument` Beanie document

**Backend API Layer:**
- `backend/app/interfaces/api/skills_routes.py` — Full REST API: CRUD, marketplace search, community publish, skill packages, command system
- `backend/app/interfaces/schemas/skill.py` — Request/response schemas

**Nanobot (Sandbox Agent):**
- `backend/nanobot/agent/skills.py` — `SkillsLoader` (independent from backend): loads from `workspace/skills/` and `builtin_skills/`, requirement checking, XML summary for agent prompt
- `backend/nanobot/skills/` — 8 built-in skills: clawhub, cron, github, memory, skill-creator, summarize, tmux, weather

**Frontend:**
- `frontend/src/components/settings/SkillsSettings.vue` — Full skills settings page (1146 lines): enable/disable, custom skill CRUD, build-with-pythinker, community browser, skill viewer, delivery card
- `frontend/src/components/SkillPicker.vue` — Per-message skill selection widget
- `frontend/src/components/SkillDeliveryCard.vue` — Skill delivery/install card
- `frontend/src/components/skill/SkillFileTree.vue` — File tree viewer for skill packages
- `frontend/src/components/skill/SkillFileTreeNode.vue` — Tree node component
- `frontend/src/components/skill/SkillFilePreview.vue` — File preview component
- `frontend/src/components/settings/SkillCreatorDialog.vue` — Dialog for creating custom skills
- `frontend/src/composables/useSkills.ts` — Full Pinia-style composable: available/custom/user skills, per-message selection, session-level persistence, CRUD operations
- `frontend/src/composables/useSkillEvents.ts` — SSE skill event handling
- `frontend/src/composables/useSkillViewer.ts` — Skill file viewer logic
- `frontend/src/api/skills.ts` — API client for all skill endpoints

**Tests:** 15+ test files covering skills

**Project-Level Skills (OpenCode/Claude):**
- `.opencode/skills/` — 8 Pythinker-specific skills (ddd-architecture, sandbox-management, browser-automation, memory-system, etc.)

### Identified Gaps & Enhancement Opportunities

| Gap | Impact | Priority |
|-----|--------|----------|
| **Nanobot has its own independent SkillsLoader** — no bridge to backend DB skills | Nanobot agents can't use user-created or community skills from the backend | HIGH |
| **No OpenClaw Hub integration at code level** — only a nanobot SKILL.md with CLI instructions | Users can't browse/install Hub skills from the Pythinker UI | HIGH |
| **No user-specific skill workspace directories** — all custom skills go to DB only | Users can't develop skills locally with version control | MEDIUM |
| **MAX_ENABLED_SKILLS = 5 is hardcoded** — no per-user/per-plan flexibility | Enterprise/power users limited unnecessarily | LOW |
| **No skill versioning/updates** — install once, no update mechanism | Community skills can't be updated | MEDIUM |
| **No skill dependency resolution** — skills can't require other skills | Complex skill compositions impossible | LOW |
| **Skill marketplace UI is minimal** — browse/search exists but no discovery UX | Poor skill discovery experience | MEDIUM |
| **No bulk skill import** (from zip, URL, or registry) | Manual one-by-one creation only | HIGH |
| **No skill sharing between users** — publish exists but no easy share | Community growth limited | MEDIUM |

---

## Phase 1: Bridge Nanobot Skills to Backend (HIGH)

### Task 1.1: Create BackendSkillLoader for Nanobot

**Goal:** Enable nanobot agents to access skills stored in the backend MongoDB, not just filesystem skills.

**Files:**
- Create: `backend/nanobot/agent/backend_skill_loader.py`
- Modify: `backend/nanobot/agent/skills.py`

**Step 1:** Write test for BackendSkillLoader

```python
# tests/nanobot/test_backend_skill_loader.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from nanobot.agent.backend_skill_loader import BackendSkillLoader


@pytest.fixture
def mock_skill_service():
    service = MagicMock()
    service.get_available_skills = AsyncMock(return_value=[])
    service.get_skill_by_id = AsyncMock(return_value=None)
    return service


@pytest.mark.asyncio
async def test_list_skills_returns_backend_skills(mock_skill_service):
    from app.domain.models.skill import Skill, SkillCategory, SkillSource
    skill = Skill(
        id="test-skill", name="Test Skill", description="A test",
        category=SkillCategory.CUSTOM, source=SkillSource.CUSTOM,
        body="Instructions here", system_prompt_addition="Be helpful",
    )
    mock_skill_service.get_available_skills.return_value = [skill]

    loader = BackendSkillLoader(skill_service=mock_skill_service)
    skills = loader.list_skills()

    assert len(skills) == 1
    assert skills[0]["name"] == "test-skill"
    assert skills[0]["source"] == "backend"


@pytest.mark.asyncio
async def test_load_skill_returns_body_content(mock_skill_service):
    from app.domain.models.skill import Skill, SkillCategory, SkillSource
    skill = Skill(
        id="research", name="Research Skill", description="Deep research",
        category=SkillCategory.RESEARCH, source=SkillSource.CUSTOM,
        body="## Research Instructions\n\n1. Search\n2. Summarize",
        system_prompt_addition="Use search tools",
    )
    mock_skill_service.get_skill_by_id.return_value = skill

    loader = BackendSkillLoader(skill_service=mock_skill_service)
    content = loader.load_skill("research")

    assert "Research Instructions" in content
    assert "## Research Instructions" in content
```

**Step 2:** Implement BackendSkillLoader

```python
# backend/nanobot/agent/backend_skill_loader.py
"""BackendSkillLoader bridges nanobot to the Pythinker backend skill DB."""

from __future__ import annotations

import logging
from typing import Any, Protocol

logger = logging.getLogger(__name__)


class SkillServiceProtocol(Protocol):
    """Protocol matching backend SkillService interface."""

    async def get_available_skills(self) -> list[Any]: ...
    async def get_skill_by_id(self, skill_id: str) -> Any | None: ...
    async def get_skills_by_ids(self, skill_ids: list[str]) -> list[Any]: ...


class BackendSkillLoader:
    """Loads skills from the Pythinker backend database.

    Implements the same interface as the filesystem SkillsLoader
    so nanobot can transparently use backend-stored skills.
    """

    def __init__(self, skill_service: SkillServiceProtocol) -> None:
        self._service = skill_service

    def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
        """List all available skills from the backend.

        Returns list of dicts with 'name', 'path', 'source' keys.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            skills = loop.run_until_complete(self._service.get_available_skills())
        except RuntimeError:
            skills = asyncio.run(self._service.get_available_skills())

        return [
            {
                "name": skill.id,
                "path": f"backend://{skill.id}",
                "source": "backend",
            }
            for skill in skills
        ]

    def load_skill(self, name: str) -> str | None:
        """Load a skill's full content from the backend.

        Reconstructs SKILL.md format from the Skill domain model.
        """
        import asyncio

        try:
            loop = asyncio.get_running_loop()
            skill = loop.run_until_complete(self._service.get_skill_by_id(name))
        except RuntimeError:
            skill = asyncio.run(self._service.get_skill_by_id(name))

        if skill is None:
            return None

        parts = []
        # Reconstruct YAML frontmatter
        parts.append("---")
        parts.append(f"name: {skill.name}")
        parts.append(f"description: {skill.description}")
        parts.append(f"category: {skill.category.value}")
        parts.append(f"version: {skill.version}")
        if skill.author:
            parts.append(f"author: {skill.author}")
        if skill.tags:
            parts.append(f"tags: {skill.tags}")
        parts.append("---")
        parts.append("")

        # Add body
        if skill.body:
            parts.append(skill.body)

        return "\n".join(parts)

    def build_skills_summary(self) -> str:
        """Build XML summary of backend skills for agent prompt."""
        skills = self.list_skills(filter_unavailable=False)
        if not skills:
            return ""

        def escape(s: str) -> str:
            return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

        lines = ["<skills>"]
        for s in skills:
            lines.append(f'  <skill available="true">')
            lines.append(f"    <name>{escape(s['name'])}</name>")
            lines.append(f"    <location>{s['path']}</location>")
            lines.append(f"    <source>{s['source']}</source>")
            lines.append("  </skill>")
        lines.append("</skills>")

        return "\n".join(lines)

    def load_skills_for_context(self, skill_names: list[str]) -> str:
        """Load multiple skills formatted for agent context."""
        parts = []
        for name in skill_names:
            content = self.load_skill(name)
            if content:
                parts.append(f"### Skill: {name}\n\n{content}")
        return "\n\n---\n\n".join(parts) if parts else ""

    def get_always_skills(self) -> list[str]:
        """Get skills marked as always=true."""
        # Backend skills use default_enabled field
        import asyncio
        try:
            loop = asyncio.get_running_loop()
            skills = loop.run_until_complete(self._service.get_available_skills())
        except RuntimeError:
            skills = asyncio.run(self._service.get_available_skills())

        return [s.id for s in skills if s.default_enabled]
```

**Step 3:** Modify `SkillsLoader` to merge backend skills

Update `backend/nanobot/agent/skills.py` to optionally accept and merge a `BackendSkillLoader`:

```python
# Add to SkillsLoader.__init__:
def __init__(
    self,
    workspace: Path,
    builtin_skills_dir: Path | None = None,
    backend_loader: "BackendSkillLoader | None" = None,
):
    self.workspace = workspace
    self.workspace_skills = workspace / "skills"
    self.builtin_skills = builtin_skills_dir or BUILTIN_SKILLS_DIR
    self._backend_loader = backend_loader

# Update list_skills to merge:
def list_skills(self, filter_unavailable: bool = True) -> list[dict[str, str]]:
    skills = []

    # Workspace skills (highest priority)
    # ... existing workspace logic ...

    # Built-in skills
    # ... existing builtin logic ...

    # Backend DB skills (lowest priority, dedup by name)
    if self._backend_loader:
        backend_skills = self._backend_loader.list_skills(filter_unavailable)
        existing_names = {s["name"] for s in skills}
        for s in backend_skills:
            if s["name"] not in existing_names:
                skills.append(s)

    if filter_unavailable:
        return [s for s in skills if self._check_requirements(self._get_skill_meta(s["name"]))]
    return skills
```

**Step 4:** Run tests

```bash
conda activate pythinker && cd backend && pytest tests/nanobot/test_backend_skill_loader.py -v
```

**Step 5:** Commit

```bash
git add backend/nanobot/agent/backend_skill_loader.py backend/nanobot/agent/skills.py tests/nanobot/test_backend_skill_loader.py
git commit -m "feat(skills): bridge nanobot SkillsLoader to backend skill DB"
```

---

### Task 1.2: Wire BackendSkillLoader in Nanobot Agent Factory

**Goal:** When nanobot agents are created inside Docker, they automatically get backend skills.

**Files:**
- Modify: `backend/app/core/sandbox_manager.py` (or wherever nanobot agent is initialized)
- Modify: `backend/app/domain/services/runtime/skill_discovery_middleware.py`

**Step 1:** Identify the nanobot agent initialization point

Search for where `SkillsLoader` is instantiated in the backend codebase.

**Step 2:** Pass BackendSkillLoader to SkillsLoader at agent creation

```python
# Wherever nanobot agent is created:
from nanobot.agent.skills import SkillsLoader
from nanobot.agent.backend_skill_loader import BackendSkillLoader
from app.application.services.skill_service import get_skill_service

skill_service = get_skill_service()
backend_loader = BackendSkillLoader(skill_service=skill_service)
skills_loader = SkillsLoader(
    workspace=sandbox_workspace,
    backend_loader=backend_loader,
)
```

**Step 3:** Commit

```bash
git add backend/app/core/sandbox_manager.py
git commit -m "feat(skills): wire backend skill loader into nanobot agent creation"
```

---

## Phase 2: OpenClaw Hub Integration at Code Level (HIGH)

### Task 2.1: ClawHub Service for Backend Skill Import

**Goal:** Create a domain service that interfaces with ClawHub API/CLI to search and import skills directly into the backend.

**Files:**
- Create: `backend/app/domain/services/clawhub_service.py`
- Create: `backend/tests/domain/services/test_clawhub_service.py`

**Step 1:** Write tests

```python
# tests/domain/services/test_clawhub_service.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.domain.services.clawhub_service import ClawHubService, ClawHubSearchResult


@pytest.fixture
def clawhub_service():
    return ClawHubService()


@pytest.mark.asyncio
async def test_search_skills_returns_results(clawhub_service):
    with patch("app.domain.services.clawhub_service.asyncio.create_subprocess_exec") as mock_subprocess:
        mock_process = AsyncMock()
        mock_process.stdout.read.return_value = b'[{"slug":"web-research","name":"Web Research","description":"Deep research tool","downloads":1500,"rating":4.5}]'
        mock_process.returncode = 0
        mock_subprocess.return_value = mock_process

        results = await clawhub_service.search("web scraping")
        assert len(results) == 1
        assert results[0].slug == "web-research"
        assert results[0].rating == 4.5


@pytest.mark.asyncio
async def test_install_skill_downloads_and_parses(clawhub_service):
    # Test that install downloads a skill and returns parsed SKILL.md content
    with patch.object(clawhub_service, "_run_clawhub", new_callable=AsyncMock) as mock_run:
        # Simulate successful install
        mock_run.return_value = True

        with patch.object(clawhub_service, "_read_installed_skill", new_callable=AsyncMock) as mock_read:
            mock_read.return_value = "---\nname: web-research\ndescription: Research tool\n---\n\n# Instructions\n\nUse search tools."

            result = await clawhub_service.install("web-research", workdir="/tmp/test")
            assert result is not None
            assert "web-research" in result.name
```

**Step 2:** Implement ClawHubService

```python
# backend/app/domain/services/clawhub_service.py
"""ClawHub integration service for searching and importing community skills.

ClawHub is the public skill registry for AI agents (https://clawhub.ai).
Skills follow the AgentSkills standard (SKILL.md format with YAML frontmatter).
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.domain.models.skill import Skill, SkillCategory, SkillSource

logger = logging.getLogger(__name__)


@dataclass
class ClawHubSearchResult:
    """A skill result from ClawHub search."""

    slug: str
    name: str
    description: str
    downloads: int = 0
    rating: float = 0.0
    author: str | None = None
    tags: list[str] = field(default_factory=list)
    version: str = "1.0.0"


class ClawHubService:
    """Service for interacting with ClawHub skill registry.

    Uses the ClawHub CLI (npx clawhub@latest) for search and install operations.
    """

    async def search(
        self,
        query: str,
        limit: int = 10,
    ) -> list[ClawHubSearchResult]:
        """Search ClawHub for skills matching a query.

        Args:
            query: Natural language search query.
            limit: Maximum results to return.

        Returns:
            List of search results.
        """
        stdout = await self._run_clawhub(
            "search", query, "--limit", str(limit), "--format", "json"
        )

        if not stdout:
            return []

        try:
            data = json.loads(stdout)
            if isinstance(data, list):
                return [
                    ClawHubSearchResult(
                        slug=item.get("slug", ""),
                        name=item.get("name", item.get("slug", "")),
                        description=item.get("description", ""),
                        downloads=item.get("downloads", 0),
                        rating=item.get("rating", 0.0),
                        author=item.get("author"),
                        tags=item.get("tags", []),
                        version=item.get("version", "1.0.0"),
                    )
                    for item in data[:limit]
                ]
        except (json.JSONDecodeError, TypeError, KeyError) as exc:
            logger.warning("Failed to parse ClawHub search results: %s", exc)

        return []

    async def install(
        self,
        slug: str,
        workdir: Path | str | None = None,
    ) -> Skill | None:
        """Install a skill from ClawHub and convert to Pythinker Skill model.

        Args:
            slug: ClawHub skill slug.
            workdir: Target directory for installation.

        Returns:
            Skill model or None if installation failed.
        """
        workdir_path = Path(workdir) if workdir else Path("/tmp/clawhub-skills")
        workdir_path.mkdir(parents=True, exist_ok=True)

        success = await self._run_clawhub(
            "install", slug, "--workdir", str(workdir_path)
        )

        if not success:
            logger.error("ClawHub install failed for skill: %s", slug)
            return None

        return await self._read_installed_skill(workdir_path, slug)

    async def list_installed(
        self,
        workdir: Path | str | None = None,
    ) -> list[str]:
        """List installed ClawHub skills.

        Args:
            workdir: Working directory.

        Returns:
            List of installed skill slugs.
        """
        stdout = await self._run_clawhub("list", "--workdir", str(workdir or ""))
        if not stdout:
            return []

        return [line.strip() for line in stdout.strip().split("\n") if line.strip()]

    async def update_all(
        self,
        workdir: Path | str | None = None,
    ) -> bool:
        """Update all installed ClawHub skills.

        Args:
            workdir: Working directory.

        Returns:
            True if update succeeded.
        """
        return await self._run_clawhub("update", "--all", "--workdir", str(workdir or ""))

    async def _run_clawhub(self, *args: str) -> str | None:
        """Execute a ClawHub CLI command.

        Returns:
            stdout content, or None if command failed.
        """
        cmd = [
            shutil.which("npx") or "npx",
            "--yes",
            "clawhub@latest",
            *args,
        ]

        logger.debug("Running ClawHub: %s", " ".join(cmd))

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60)

            if process.returncode != 0:
                logger.warning("ClawHub CLI error: %s", stderr.decode())
                return None

            return stdout.decode().strip()
        except FileNotFoundError:
            logger.error("npx not found — Node.js is required for ClawHub integration")
            return None
        except asyncio.TimeoutError:
            logger.error("ClawHub CLI timed out")
            return None
        except Exception as exc:
            logger.error("ClawHub CLI failed: %s", exc)
            return None

    async def _read_installed_skill(
        self,
        workdir: Path,
        slug: str,
    ) -> Skill | None:
        """Read an installed skill from the workspace and convert to Skill model.

        Args:
            workdir: Working directory where skill was installed.
            slug: Skill slug.

        Returns:
            Skill model or None.
        """
        skill_md_path = workdir / "skills" / slug / "SKILL.md"
        if not skill_md_path.exists():
            logger.warning("SKILL.md not found after install: %s", skill_md_path)
            return None

        try:
            content = skill_md_path.read_text(encoding="utf-8")
            return Skill.from_skill_md(
                content=content,
                category=SkillCategory.CUSTOM,
                source=SkillSource.COMMUNITY,
            )
        except Exception as exc:
            logger.error("Failed to parse installed skill %s: %s", slug, exc)
            return None


# Singleton
_clawhub_service: ClawHubService | None = None


def get_clawhub_service() -> ClawHubService:
    """Get the singleton ClawHub service."""
    global _clawhub_service
    if _clawhub_service is None:
        _clawhub_service = ClawHubService()
    return _clawhub_service
```

**Step 3:** Run tests

```bash
conda activate pythinker && cd backend && pytest tests/domain/services/test_clawhub_service.py -v
```

**Step 4:** Commit

```bash
git add backend/app/domain/services/clawhub_service.py backend/tests/domain/services/test_clawhub_service.py
git commit -m "feat(skills): add ClawHub integration service for skill search/install"
```

---

### Task 2.2: ClawHub API Routes

**Goal:** Expose ClawHub search/install as REST API endpoints so the frontend can browse and install skills.

**Files:**
- Create: `backend/app/interfaces/api/clawhub_routes.py`
- Modify: `backend/app/interfaces/api/__init__.py` (or router registration)

**Step 1:** Implement routes

```python
# backend/app/interfaces/api/clawhub_routes.py
"""API routes for ClawHub skill marketplace integration."""

import logging
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.domain.models.skill import SkillCategory, SkillSource
from app.domain.models.user import User
from app.domain.services.clawhub_service import get_clawhub_service
from app.interfaces.dependencies import get_current_user
from app.interfaces.schemas.base import APIResponse

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/clawhub", tags=["clawhub"])


class ClawHubSkillResponse(BaseModel):
    """Response for a ClawHub search result."""

    slug: str
    name: str
    description: str
    downloads: int = 0
    rating: float = 0.0
    author: str | None = None
    tags: list[str] = Field(default_factory=list)
    version: str = "1.0.0"
    installed: bool = False


class ClawHubSearchResponse(BaseModel):
    """Response for ClawHub search."""

    skills: list[ClawHubSkillResponse]
    total: int


class ClawHubInstallRequest(BaseModel):
    """Request to install a skill from ClawHub."""

    slug: str = Field(..., description="ClawHub skill slug to install")
    enable_after_install: bool = Field(default=True)


class ClawHubInstallResponse(BaseModel):
    """Response after installing a skill from ClawHub."""

    installed: bool
    skill_id: str | None = None
    name: str | None = None
    message: str


@router.get("/search", response_model=APIResponse[ClawHubSearchResponse])
async def search_clawhub(
    q: str,
    limit: int = 10,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ClawHubSearchResponse]:
    """Search ClawHub for community skills."""
    service = get_clawhub_service()
    results = await service.search(q, limit=min(limit, 50))

    return APIResponse.success(
        ClawHubSearchResponse(
            skills=[
                ClawHubSkillResponse(
                    slug=r.slug,
                    name=r.name,
                    description=r.description,
                    downloads=r.downloads,
                    rating=r.rating,
                    author=r.author,
                    tags=r.tags,
                    version=r.version,
                )
                for r in results
            ],
            total=len(results),
        )
    )


@router.post("/install", response_model=APIResponse[ClawHubInstallResponse])
async def install_clawhub_skill(
    request: ClawHubInstallRequest,
    current_user: User = Depends(get_current_user),
) -> APIResponse[ClawHubInstallResponse]:
    """Install a skill from ClawHub into the user's skills."""
    from app.application.services.skill_service import get_skill_service
    from app.domain.services.skill_registry import invalidate_skill_caches

    service = get_clawhub_service()
    skill_service = get_skill_service()

    # Install via ClawHub CLI into a temp dir
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        skill = await service.install(request.slug, workdir=Path(tmpdir))

    if skill is None:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to install skill '{request.slug}' from ClawHub",
        )

    # Set ownership and source
    skill.owner_id = str(current_user.id)
    skill.source = SkillSource.COMMUNITY
    skill.author = skill.author or current_user.fullname
    skill.created_at = datetime.now(UTC)
    skill.updated_at = datetime.now(UTC)

    # Save to database
    created = await skill_service.create_skill(skill)

    # Invalidate caches
    await invalidate_skill_caches(created.id)

    # Optionally enable
    if request.enable_after_install:
        # Add to user's enabled skills
        from app.core.config import get_settings as get_app_settings
        from app.infrastructure.storage.mongodb import get_mongodb

        app_settings = get_app_settings()
        mongodb = get_mongodb()
        db = mongodb.client[app_settings.mongodb_database]
        settings_collection = db.get_collection("user_settings")

        settings_doc = await settings_collection.find_one({"user_id": str(current_user.id)})
        enabled_skills = settings_doc.get("enabled_skills", []) if settings_doc else []

        if created.id not in enabled_skills and len(enabled_skills) < 5:
            enabled_skills.append(created.id)
            await settings_collection.update_one(
                {"user_id": str(current_user.id)},
                {"$set": {"enabled_skills": enabled_skills}},
                upsert=True,
            )

    logger.info("User %s installed ClawHub skill: %s", current_user.id, request.slug)

    return APIResponse.success(
        ClawHubInstallResponse(
            installed=True,
            skill_id=created.id,
            name=created.name,
            message=f"Skill '{request.slug}' installed successfully from ClawHub",
        )
    )


@router.get("/installed", response_model=APIResponse[list[str]])
async def list_installed_clawhub_skills(
    current_user: User = Depends(get_current_user),
) -> APIResponse[list[str]]:
    """List skills installed from ClawHub on this instance."""
    service = get_clawhub_service()
    installed = await service.list_installed()
    return APIResponse.success(installed)
```

**Step 2:** Register the router in the main app

**Step 3:** Commit

```bash
git add backend/app/interfaces/api/clawhub_routes.py
git commit -m "feat(skills): add ClawHub REST API routes for search/install"
```

---

### Task 2.3: Frontend ClawHub Browser Component

**Goal:** Build a Vue component for browsing and installing ClawHub skills from the settings UI.

**Files:**
- Create: `frontend/src/components/settings/ClawHubBrowser.vue`
- Modify: `frontend/src/api/skills.ts` (add ClawHub API client functions)
- Modify: `frontend/src/components/settings/SkillsSettings.vue` (integrate browser)

**Step 1:** Add API client functions

```typescript
// Add to frontend/src/api/skills.ts

export interface ClawHubSkill {
  slug: string;
  name: string;
  description: string;
  downloads: number;
  rating: number;
  author: string | null;
  tags: string[];
  version: string;
}

export async function searchClawHub(query: string, limit = 10): Promise<ClawHubSkill[]> {
  const response = await apiClient.get<APIResponse<{ skills: ClawHubSkill[]; total: number }>>(
    '/clawhub/search',
    { params: { q: query, limit } }
  );
  return response.data.data.skills;
}

export async function installClawHubSkill(
  slug: string,
  enableAfterInstall = true
): Promise<{ installed: boolean; skill_id: string | null; name: string | null }> {
  const response = await apiClient.post<APIResponse<{ installed: boolean; skill_id: string | null; name: string | null }>>(
    '/clawhub/install',
    { slug, enable_after_install: enableAfterInstall }
  );
  return response.data.data;
}
```

**Step 2:** Create ClawHubBrowser component (search, results, install button)

**Step 3:** Integrate into SkillsSettings.vue "Add from official" button

**Step 4:** Commit

```bash
git add frontend/src/components/settings/ClawHubBrowser.vue frontend/src/api/skills.ts frontend/src/components/settings/SkillsSettings.vue
git commit -m "feat(skills): add ClawHub browser component for skill discovery"
```

---

## Phase 3: User Skill Workspace & Import (MEDIUM)

### Task 3.1: Skill Import from ZIP/URL/SKILL.md

**Goal:** Allow users to import skills from uploaded ZIP files, URLs, or raw SKILL.md content.

**Files:**
- Create: `backend/app/domain/services/skill_importer.py`
- Create: `backend/tests/domain/services/test_skill_importer.py`
- Modify: `backend/app/interfaces/api/skills_routes.py` (add import endpoint)

**Step 1:** Write tests for SkillImporter

```python
# tests/domain/services/test_skill_importer.py
import pytest
from pathlib import Path

from app.domain.services.skill_importer import SkillImporter


@pytest.mark.asyncio
async def test_import_from_skill_md_content():
    content = """---
name: test-import
description: A test skill for import
version: 1.0.0
category: coding
---

# Test Import Skill

This skill helps with testing.
"""
    importer = SkillImporter()
    skill = await importer.import_from_content(content, owner_id="user-123")

    assert skill is not None
    assert skill.name == "test-import"
    assert skill.description == "A test skill for import"
    assert skill.body == "# Test Import Skill\n\nThis skill helps with testing."


@pytest.mark.asyncio
async def test_import_from_url(tmp_path):
    # Mock HTTP fetch
    importer = SkillImporter()
    # ... test with mocked HTTP response
```

**Step 2:** Implement SkillImporter

```python
# backend/app/domain/services/skill_importer.py
"""Skill import service for importing skills from various sources."""

from __future__ import annotations

import io
import logging
import zipfile
from pathlib import Path

from app.domain.models.skill import Skill, SkillCategory, SkillSource

logger = logging.getLogger(__name__)


class SkillImporter:
    """Import skills from ZIP files, URLs, or raw SKILL.md content."""

    async def import_from_content(
        self,
        content: str,
        owner_id: str,
        source: SkillSource = SkillSource.CUSTOM,
    ) -> Skill | None:
        """Import a skill from raw SKILL.md content.

        Args:
            content: SKILL.md file content.
            owner_id: Owner user ID.
            source: Source type.

        Returns:
            Skill model or None if parsing failed.
        """
        try:
            return Skill.from_skill_md(
                content=content,
                category=SkillCategory.CUSTOM,
                source=source,
            )
        except Exception as exc:
            logger.error("Failed to import skill from content: %s", exc)
            return None

    async def import_from_zip(
        self,
        zip_bytes: bytes,
        owner_id: str,
    ) -> Skill | None:
        """Import a skill from a ZIP archive.

        The ZIP should contain a SKILL.md at the root or in a subdirectory.

        Args:
            zip_bytes: ZIP file bytes.
            owner_id: Owner user ID.

        Returns:
            Skill model or None if import failed.
        """
        try:
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
                # Find SKILL.md
                skill_md_name = None
                for name in zf.namelist():
                    if name.endswith("SKILL.md"):
                        skill_md_name = name
                        break

                if skill_md_name is None:
                    logger.error("No SKILL.md found in ZIP archive")
                    return None

                content = zf.read(skill_md_name).decode("utf-8")
                return await self.import_from_content(content, owner_id)
        except (zipfile.BadZipFile, KeyError, UnicodeDecodeError) as exc:
            logger.error("Failed to import skill from ZIP: %s", exc)
            return None

    async def import_from_url(
        self,
        url: str,
        owner_id: str,
    ) -> Skill | None:
        """Import a skill from a URL (SKILL.md or ZIP).

        Args:
            url: URL to fetch.
            owner_id: Owner user ID.

        Returns:
            Skill model or None.
        """
        from app.infrastructure.http.client_pool import HTTPClientPool

        pool = HTTPClientPool.get_instance()
        client = await pool.get_client()

        try:
            response = await client.get(url)
            response.raise_for_status()

            content_type = response.headers.get("content-type", "")

            if "zip" in content_type or url.endswith(".zip"):
                return await self.import_from_zip(response.content, owner_id)
            else:
                return await self.import_from_content(response.text, owner_id)
        except Exception as exc:
            logger.error("Failed to import skill from URL %s: %s", url, exc)
            return None
```

**Step 3:** Add upload/import endpoint to skills_routes.py

```python
@router.post("/import", response_model=APIResponse[SkillResponse])
async def import_skill(
    file: UploadFile | None = File(default=None),
    url: str | None = Form(default=None),
    content: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
) -> APIResponse[SkillResponse]:
    """Import a skill from a file upload, URL, or raw content."""
    importer = SkillImporter()

    if file:
        zip_bytes = await file.read()
        skill = await importer.import_from_zip(zip_bytes, str(current_user.id))
    elif url:
        skill = await importer.import_from_url(url, str(current_user.id))
    elif content:
        skill = await importer.import_from_content(content, str(current_user.id))
    else:
        raise HTTPException(status_code=400, detail="Provide file, url, or content")

    if skill is None:
        raise HTTPException(status_code=400, detail="Failed to import skill")

    skill.owner_id = str(current_user.id)
    created = await get_skill_service().create_skill(skill)
    return APIResponse.success(_skill_to_response(created, include_prompt=True))
```

**Step 4:** Commit

```bash
git add backend/app/domain/services/skill_importer.py backend/tests/domain/services/test_skill_importer.py backend/app/interfaces/api/skills_routes.py
git commit -m "feat(skills): add skill import from ZIP, URL, and raw content"
```

---

## Phase 4: Settings Skills UI Enhancement (MEDIUM)

### Task 4.1: Enable "Upload a skill" and "Add from official" buttons

**Goal:** Wire up the disabled buttons in SkillsSettings.vue to use the new import and ClawHub features.

**Files:**
- Modify: `frontend/src/components/settings/SkillsSettings.vue`
- Create: `frontend/src/components/settings/SkillImportDialog.vue`

**Step 1:** Create SkillImportDialog component

Support three import methods:
1. File upload (drag-and-drop .zip or .skill file)
2. URL input (paste a SKILL.md URL)
3. Raw content editor (paste SKILL.md markdown)

**Step 2:** Update SkillsSettings.vue to enable the disabled buttons

Replace `add-dropdown-item-disabled` with working handlers that open the import dialog or ClawHub browser.

**Step 3:** Commit

```bash
git add frontend/src/components/settings/SkillImportDialog.vue frontend/src/components/settings/SkillsSettings.vue
git commit -m "feat(frontend): enable skill import upload and ClawHub browse buttons"
```

---

## Phase 5: Skill Versioning & Updates (MEDIUM)

### Task 5.1: Add Skill Version Tracking

**Goal:** Track skill versions to enable updates from ClawHub and other sources.

**Files:**
- Modify: `backend/app/domain/models/skill.py` (add `upstream_slug`, `upstream_version`, `last_checked_at`)
- Modify: `backend/app/infrastructure/models/documents.py` (add new fields to SkillDocument)
- Create: `backend/app/domain/services/skill_updater.py`

**Step 1:** Add version tracking fields to Skill model

```python
# Add to Skill class in domain/models/skill.py:
upstream_slug: str | None = Field(
    default=None,
    description="Original slug from upstream source (ClawHub, etc.)",
)
upstream_version: str | None = Field(
    default=None,
    description="Latest known version from upstream source",
)
last_checked_at: datetime | None = Field(
    default=None,
    description="When the upstream was last checked for updates",
)
```

**Step 2:** Implement SkillUpdater service

```python
# backend/app/domain/services/skill_updater.py
"""Skill update service for checking and applying updates."""

class SkillUpdater:
    """Check for and apply skill updates from upstream sources."""

    async def check_for_updates(self) -> list[dict]:
        """Check all ClawHub-sourced skills for updates."""
        # Query skills with upstream_slug set
        # For each, query ClawHub for latest version
        # Return list of {skill_id, current_version, latest_version, has_update}

    async def update_skill(self, skill_id: str) -> Skill | None:
        """Update a single skill from its upstream source."""
        # Re-fetch from ClawHub
        # Update body, version, system_prompt_addition
        # Keep user's enabled state and config
```

**Step 3:** Commit

```bash
git add backend/app/domain/models/skill.py backend/app/infrastructure/models/documents.py backend/app/domain/services/skill_updater.py
git commit -m "feat(skills): add skill version tracking and update service"
```

---

## Phase 6: Skill Sharing & Community Features (MEDIUM)

### Task 6.1: Skill Export as SKILL.md / ZIP

**Goal:** Enable users to export their custom skills as downloadable SKILL.md or .skill ZIP files.

**Files:**
- Create: `backend/app/domain/services/skill_exporter.py`
- Modify: `backend/app/interfaces/api/skills_routes.py` (add export endpoint)

**Step 1:** Implement SkillExporter

```python
# backend/app/domain/services/skill_exporter.py
"""Skill export service for downloading skills as SKILL.md or .skill ZIP."""

class SkillExporter:
    """Export skills in standard formats."""

    def export_as_skill_md(self, skill: Skill) -> str:
        """Export skill as a SKILL.md file content."""

    def export_as_zip(self, skill: Skill) -> bytes:
        """Export skill as a .skill ZIP archive."""
```

**Step 2:** Add download endpoint

```python
@router.get("/custom/{skill_id}/export")
async def export_skill(
    skill_id: str,
    format: str = "skill_md",  # skill_md or zip
    current_user: User = Depends(get_current_user),
):
    """Export a custom skill."""
```

**Step 3:** Commit

```bash
git add backend/app/domain/services/skill_exporter.py backend/app/interfaces/api/skills_routes.py
git commit -m "feat(skills): add skill export as SKILL.md and ZIP"
```

---

## Phase 7: Improved Settings UX (LOW)

### Task 7.1: Dynamic MAX_ENABLED_SKILLS per Plan

**Goal:** Allow different max skill limits per user plan (free: 3, pro: 10, unlimited: 0).

**Files:**
- Modify: `backend/app/interfaces/api/skills_routes.py` (make MAX_ENABLED_SKILLS dynamic)
- Modify: `frontend/src/api/skills.ts` (read max from API response)
- Modify: `frontend/src/composables/useSkills.ts` (use dynamic max)

---

### Task 7.2: Skill Dependency Resolution

**Goal:** Allow skills to declare dependencies on other skills.

**Files:**
- Modify: `backend/app/domain/models/skill.py` (add `dependencies: list[str]` field)
- Modify: `backend/app/domain/services/skill_activation_framework.py` (auto-include dependencies)
- Modify: `backend/app/domain/services/skill_validator.py` (validate dependency references)

---

## Summary: Implementation Priority

| Phase | Tasks | Priority | Estimated Effort |
|-------|-------|----------|-----------------|
| Phase 1: Nanobot-Backend Bridge | 1.1, 1.2 | HIGH | 2-3 hours |
| Phase 2: OpenClaw Hub Integration | 2.1, 2.2, 2.3 | HIGH | 3-4 hours |
| Phase 3: Skill Import | 3.1 | MEDIUM | 2 hours |
| Phase 4: Settings UI Enhancement | 4.1 | MEDIUM | 2-3 hours |
| Phase 5: Skill Versioning | 5.1 | MEDIUM | 2 hours |
| Phase 6: Skill Sharing/Export | 6.1 | MEDIUM | 1-2 hours |
| Phase 7: Improved UX | 7.1, 7.2 | LOW | 2-3 hours |
| **Total** | **12 tasks** | | **~15-20 hours** |

## OpenClaw/ClawHub Integration Strategy

| Approach | How | Status |
|----------|-----|--------|
| **ClawHub CLI** (primary) | `npx clawhub@latest search/install` | Already has nanobot SKILL.md, needs backend service wrapper (Phase 2) |
| **SkillKit API** (secondary) | REST API on localhost:3737 for skill discovery | Future enhancement — can proxy through FastAPI |
| **Sundial** (federated) | Open SKILL.md format, CLI installable | Future — vendored skill import (Phase 3 covers ZIP import) |
| **skills-hub.ai** (reference) | Marketplace patterns for UI inspiration | UI inspiration only |

## Key Decisions

1. **SKILL.md is the universal format** — All sources (ClawHub, local, ZIP) normalize to SKILL.md before import
2. **Backend DB is the source of truth** — Nanobot reads from backend, not filesystem directly
3. **ClawHub CLI over API** — Use `npx clawhub@latest` rather than HTTP API for simplicity and security scanning
4. **Progressive disclosure preserved** — Existing L1/L2/L3 pattern maintained for all skill sources
5. **No new infrastructure** — Everything uses existing MongoDB, Redis, HTTP client pooling
