import asyncio
from datetime import UTC, datetime

import pytest

from app.application.services.canvas_service import CanvasService
from app.domain.models.canvas import CanvasElement, CanvasPage, CanvasProject, CanvasVersion, ElementType


class InMemoryCanvasRepo:
    def __init__(self, project: CanvasProject) -> None:
        self._projects: dict[str, CanvasProject] = {project.id: project.model_copy(deep=True)}

    async def save(self, project: CanvasProject) -> CanvasProject:
        self._projects[project.id] = project.model_copy(deep=True)
        return project.model_copy(deep=True)

    async def find_by_id(self, project_id: str) -> CanvasProject | None:
        project = self._projects.get(project_id)
        return project.model_copy(deep=True) if project else None

    async def find_by_user_id(self, user_id: str, skip: int = 0, limit: int = 50) -> list[CanvasProject]:
        projects = [p.model_copy(deep=True) for p in self._projects.values() if p.user_id == user_id]
        return projects[skip : skip + limit]

    async def update(self, project_id: str, project: CanvasProject) -> CanvasProject | None:
        # Simulate I/O latency so overlapping read-modify-write operations can race.
        await asyncio.sleep(0.01)
        if project_id not in self._projects:
            return None
        self._projects[project_id] = project.model_copy(deep=True)
        return self._projects[project_id].model_copy(deep=True)

    async def delete(self, project_id: str) -> bool:
        if project_id not in self._projects:
            return False
        del self._projects[project_id]
        return True

    async def count_by_user_id(self, user_id: str) -> int:
        return len([p for p in self._projects.values() if p.user_id == user_id])

    async def save_version(self, version: CanvasVersion) -> CanvasVersion:
        return version

    async def get_versions(self, project_id: str, limit: int = 20) -> list[CanvasVersion]:
        return []

    async def get_version(self, project_id: str, version: int) -> CanvasVersion | None:
        return None

    async def count_versions(self, project_id: str) -> int:
        return 0


def _build_project(project_id: str) -> CanvasProject:
    return CanvasProject(
        id=project_id,
        user_id="user-1",
        session_id="session-1",
        name="Concurrent Canvas",
        width=1920.0,
        height=1080.0,
        background="#FFFFFF",
        pages=[
            CanvasPage(
                id="page-1",
                name="Page 1",
                width=1920.0,
                height=1080.0,
                background="#FFFFFF",
                elements=[],
            )
        ],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _build_rect(element_id: str, index: int) -> CanvasElement:
    return CanvasElement(
        id=element_id,
        type=ElementType.RECTANGLE,
        name=f"rect-{index}",
        x=float(index * 10),
        y=float(index * 10),
        width=100.0,
        height=80.0,
        fill={"type": "solid", "color": "#111111"},
    )


@pytest.mark.asyncio
async def test_add_element_avoids_lost_updates_under_concurrency() -> None:
    project = _build_project("project-concurrency")
    repo = InMemoryCanvasRepo(project)
    service = CanvasService(canvas_repo=repo)

    total_elements = 25
    add_tasks = [service.add_element(project.id, _build_rect(f"el-{index}", index)) for index in range(total_elements)]

    await asyncio.gather(*add_tasks)

    updated_project = await service.get_project(project.id)
    assert updated_project is not None
    stored_ids = {element.id for element in updated_project.pages[0].elements}
    assert len(stored_ids) == total_elements
    assert all(f"el-{index}" in stored_ids for index in range(total_elements))
