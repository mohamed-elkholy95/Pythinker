"""Tests for CanvasService CRUD, version management, element operations, and AI-edit logic."""

from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.application.services.canvas_service import (
    CanvasAddOperation,
    CanvasArrangeOperation,
    CanvasDeleteOperation,
    CanvasEditPlan,
    CanvasModifyOperation,
    CanvasService,
)
from app.domain.exceptions.base import ConfigurationException, ResourceLimitExceeded
from app.domain.models.canvas import CanvasElement, CanvasPage, CanvasProject, CanvasVersion, ElementType

# ---------------------------------------------------------------------------
# In-memory repository double
# ---------------------------------------------------------------------------


class InMemoryCanvasRepo:
    """Full in-memory implementation of CanvasRepository for unit tests."""

    def __init__(self) -> None:
        self._projects: dict[str, CanvasProject] = {}
        self._versions: dict[str, list[CanvasVersion]] = {}

    async def save(self, project: CanvasProject) -> CanvasProject:
        self._projects[project.id] = project.model_copy(deep=True)
        return project.model_copy(deep=True)

    async def find_by_id(self, project_id: str) -> CanvasProject | None:
        p = self._projects.get(project_id)
        return p.model_copy(deep=True) if p else None

    async def find_by_session_id(self, session_id: str) -> CanvasProject | None:
        for p in self._projects.values():
            if p.session_id == session_id:
                return p.model_copy(deep=True)
        return None

    async def find_by_user_id(self, user_id: str, skip: int = 0, limit: int = 50) -> list[CanvasProject]:
        results = [p.model_copy(deep=True) for p in self._projects.values() if p.user_id == user_id]
        return results[skip : skip + limit]

    async def update(self, project_id: str, project: CanvasProject) -> CanvasProject | None:
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
        return sum(1 for p in self._projects.values() if p.user_id == user_id)

    async def save_version(self, version: CanvasVersion) -> CanvasVersion:
        self._versions.setdefault(version.project_id, []).append(version)
        return version

    async def get_versions(self, project_id: str, limit: int = 20) -> list[CanvasVersion]:
        return self._versions.get(project_id, [])[:limit]

    async def get_version(self, project_id: str, version: int) -> CanvasVersion | None:
        for v in self._versions.get(project_id, []):
            if v.version == version:
                return v
        return None

    async def count_versions(self, project_id: str) -> int:
        return len(self._versions.get(project_id, []))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_page(page_id: str = "page-1", elements: list[CanvasElement] | None = None) -> CanvasPage:
    return CanvasPage(
        id=page_id,
        name="Page 1",
        width=1920.0,
        height=1080.0,
        background="#FFFFFF",
        elements=elements or [],
    )


def _make_project(
    project_id: str = "proj-1",
    user_id: str = "user-1",
    session_id: str | None = "sess-1",
    pages: list[CanvasPage] | None = None,
) -> CanvasProject:
    return CanvasProject(
        id=project_id,
        user_id=user_id,
        session_id=session_id,
        name="Test Design",
        width=1920.0,
        height=1080.0,
        background="#FFFFFF",
        pages=pages if pages is not None else [_make_page()],
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
    )


def _make_rect(element_id: str = "el-1") -> CanvasElement:
    return CanvasElement(
        id=element_id,
        type=ElementType.RECTANGLE,
        name="Rect",
        x=10.0,
        y=20.0,
        width=100.0,
        height=50.0,
    )


def _service_with_project(project: CanvasProject | None = None) -> tuple[CanvasService, InMemoryCanvasRepo]:
    """Return a service backed by an in-memory repo, optionally pre-loaded with a project."""
    repo = InMemoryCanvasRepo()
    if project:
        repo._projects[project.id] = project.model_copy(deep=True)
    service = CanvasService(canvas_repo=repo)  # type: ignore[arg-type]
    return service, repo


# ===========================================================================
# Project CRUD
# ===========================================================================


@pytest.mark.asyncio
async def test_create_project_persists_and_returns_project() -> None:
    service, repo = _service_with_project()

    project = await service.create_project(
        user_id="user-1",
        name="My Canvas",
        width=1280.0,
        height=720.0,
        background="#000000",
        session_id="sess-42",
    )

    assert project.user_id == "user-1"
    assert project.name == "My Canvas"
    assert project.width == 1280.0
    assert project.height == 720.0
    assert project.background == "#000000"
    assert project.session_id == "sess-42"
    assert len(project.pages) == 1
    assert project.pages[0].name == "Page 1"
    assert project.id in repo._projects


@pytest.mark.asyncio
async def test_create_project_uses_defaults_when_omitted() -> None:
    service, _ = _service_with_project()

    project = await service.create_project(user_id="user-2")

    assert project.name == "Untitled Design"
    assert project.width == 1920.0
    assert project.height == 1080.0
    assert project.background == "#FFFFFF"
    assert project.session_id is None


@pytest.mark.asyncio
async def test_get_project_returns_none_for_missing_id() -> None:
    service, _ = _service_with_project()

    result = await service.get_project("nonexistent")

    assert result is None


@pytest.mark.asyncio
async def test_get_project_returns_project_by_id() -> None:
    project = _make_project()
    service, _ = _service_with_project(project)

    result = await service.get_project(project.id)

    assert result is not None
    assert result.id == project.id


@pytest.mark.asyncio
async def test_get_project_by_session_id_finds_project() -> None:
    project = _make_project(session_id="my-session")
    service, _ = _service_with_project(project)

    result = await service.get_project_by_session_id("my-session")

    assert result is not None
    assert result.session_id == "my-session"


@pytest.mark.asyncio
async def test_get_project_by_session_id_returns_none_when_not_found() -> None:
    service, _ = _service_with_project()

    result = await service.get_project_by_session_id("ghost-session")

    assert result is None


@pytest.mark.asyncio
async def test_list_projects_returns_projects_for_user() -> None:
    service, _ = _service_with_project()
    for i in range(3):
        await service.create_project(user_id="user-list", name=f"Design {i}")
    await service.create_project(user_id="other-user", name="Other Design")

    results = await service.list_projects("user-list")

    assert len(results) == 3
    assert all(p.user_id == "user-list" for p in results)


@pytest.mark.asyncio
async def test_list_projects_respects_skip_and_limit() -> None:
    service, _ = _service_with_project()
    for i in range(5):
        await service.create_project(user_id="user-page", name=f"D{i}")

    page = await service.list_projects("user-page", skip=2, limit=2)

    assert len(page) == 2


@pytest.mark.asyncio
async def test_delete_project_returns_true_and_removes_entry() -> None:
    project = _make_project()
    service, repo = _service_with_project(project)

    deleted = await service.delete_project(project.id)

    assert deleted is True
    assert project.id not in repo._projects


@pytest.mark.asyncio
async def test_delete_project_returns_false_for_missing_project() -> None:
    service, _ = _service_with_project()

    deleted = await service.delete_project("no-such-project")

    assert deleted is False


@pytest.mark.asyncio
async def test_delete_project_removes_lock_entry() -> None:
    project = _make_project()
    service, _ = _service_with_project(project)
    # Trigger lock creation
    await service.add_element(project.id, _make_rect())
    assert project.id in service._project_locks

    await service.delete_project(project.id)

    assert project.id not in service._project_locks


# ===========================================================================
# update_project — version auto-save and bump
# ===========================================================================


@pytest.mark.asyncio
async def test_update_project_bumps_version_and_saves_version_snapshot() -> None:
    project = _make_project()
    service, repo = _service_with_project(project)

    new_state = project.model_copy(deep=True)
    new_state.name = "Renamed Design"

    updated = await service.update_project(project.id, new_state)

    assert updated is not None
    assert updated.version == project.version + 1
    # An auto-save version should have been created
    assert len(repo._versions.get(project.id, [])) == 1


@pytest.mark.asyncio
async def test_update_project_returns_none_for_missing_project() -> None:
    service, _ = _service_with_project()
    phantom = _make_project(project_id="ghost")

    result = await service.update_project("ghost", phantom)

    assert result is None


@pytest.mark.asyncio
async def test_update_project_skips_version_save_when_cap_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.application.services.canvas_service as canvas_svc_module

    fake_settings = MagicMock()
    fake_settings.canvas_max_versions = 0  # Cap already at 0
    fake_settings.canvas_max_elements = 500
    monkeypatch.setattr(canvas_svc_module, "get_settings", lambda: fake_settings)

    project = _make_project()
    service, repo = _service_with_project(project)
    new_state = project.model_copy(deep=True)

    await service.update_project(project.id, new_state)

    assert len(repo._versions.get(project.id, [])) == 0


# ===========================================================================
# Version management
# ===========================================================================


@pytest.mark.asyncio
async def test_get_versions_returns_saved_versions() -> None:
    project = _make_project()
    service, repo = _service_with_project(project)
    version = CanvasVersion(
        id="ver-1",
        project_id=project.id,
        version=1,
        name="v1",
        pages=project.pages,
    )
    repo._versions[project.id] = [version]

    versions = await service.get_versions(project.id)

    assert len(versions) == 1
    assert versions[0].version == 1


@pytest.mark.asyncio
async def test_restore_version_replaces_pages_and_bumps_version() -> None:
    page_v1 = _make_page(page_id="page-v1", elements=[_make_rect("el-v1")])
    project = _make_project(pages=[_make_page()])
    service, repo = _service_with_project(project)

    saved_version = CanvasVersion(
        id="snap-1",
        project_id=project.id,
        version=1,
        name="snap",
        pages=[page_v1],
    )
    repo._versions[project.id] = [saved_version]

    restored = await service.restore_version(project.id, version=1)

    assert restored is not None
    assert restored.version == project.version + 1
    assert restored.pages[0].id == "page-v1"
    assert restored.pages[0].elements[0].id == "el-v1"


@pytest.mark.asyncio
async def test_restore_version_returns_none_for_missing_project() -> None:
    service, _ = _service_with_project()

    result = await service.restore_version("ghost-proj", version=1)

    assert result is None


@pytest.mark.asyncio
async def test_restore_version_returns_none_for_missing_version_number() -> None:
    project = _make_project()
    service, _ = _service_with_project(project)

    result = await service.restore_version(project.id, version=99)

    assert result is None


# ===========================================================================
# Element operations
# ===========================================================================


@pytest.mark.asyncio
async def test_add_element_returns_none_for_missing_project() -> None:
    service, _ = _service_with_project()

    result = await service.add_element("ghost-proj", _make_rect())

    assert result is None


@pytest.mark.asyncio
async def test_add_element_returns_none_for_out_of_range_page_index() -> None:
    project = _make_project()
    service, _ = _service_with_project(project)

    result = await service.add_element(project.id, _make_rect(), page_index=5)

    assert result is None


@pytest.mark.asyncio
async def test_add_element_raises_resource_limit_exceeded_at_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.application.services.canvas_service as canvas_svc_module

    fake_settings = MagicMock()
    fake_settings.canvas_max_elements = 1
    fake_settings.canvas_max_versions = 50
    monkeypatch.setattr(canvas_svc_module, "get_settings", lambda: fake_settings)

    page = _make_page(elements=[_make_rect("existing")])
    project = _make_project(pages=[page])
    service, _ = _service_with_project(project)

    with pytest.raises(ResourceLimitExceeded):
        await service.add_element(project.id, _make_rect("new-el"))


@pytest.mark.asyncio
async def test_modify_element_returns_none_for_missing_project() -> None:
    service, _ = _service_with_project()

    result = await service.modify_element("ghost-proj", "el-1", {"x": 5.0})

    assert result is None


@pytest.mark.asyncio
async def test_modify_element_returns_none_when_element_not_found() -> None:
    project = _make_project()
    service, _ = _service_with_project(project)

    result = await service.modify_element(project.id, "no-such-element", {"x": 5.0})

    assert result is None


@pytest.mark.asyncio
async def test_delete_elements_returns_none_for_missing_project() -> None:
    service, _ = _service_with_project()

    result = await service.delete_elements("ghost-proj", ["el-1"])

    assert result is None


# ===========================================================================
# _apply_edit_operations — all operation types
# ===========================================================================


def _make_service_with_page(elements: list[CanvasElement] | None = None) -> tuple[CanvasService, CanvasProject]:
    page = _make_page(elements=elements or [])
    project = _make_project(pages=[page])
    service, _ = _service_with_project(project)
    return service, project


def _apply(service: CanvasService, project: CanvasProject, ops: list[Any]) -> bool:
    return service._apply_edit_operations(project, ops)


def test_apply_add_rectangle_appends_element_with_correct_fields() -> None:
    service, project = _make_service_with_page()
    op = CanvasAddOperation(
        element_type=ElementType.RECTANGLE,
        x=10.0,
        y=20.0,
        width=200.0,
        height=100.0,
        fill_color="#FF0000",
        opacity=0.8,
        corner_radius=5.0,
        name="MyRect",
    )

    applied = _apply(service, project, [op])

    assert applied is True
    el = project.pages[0].elements[0]
    assert el.type == ElementType.RECTANGLE
    assert el.name == "MyRect"
    assert el.x == 10.0
    assert el.y == 20.0
    assert el.width == 200.0
    assert el.height == 100.0
    assert el.fill == {"type": "solid", "color": "#FF0000"}
    assert el.opacity == 0.8
    assert el.corner_radius == 5.0


def test_apply_add_text_element_sets_text_style_and_default_fill() -> None:
    service, project = _make_service_with_page()
    op = CanvasAddOperation(
        element_type=ElementType.TEXT,
        x=5.0,
        y=5.0,
        width=300.0,
        height=50.0,
        font_size=24.0,
    )

    _apply(service, project, [op])

    el = project.pages[0].elements[0]
    assert el.type == ElementType.TEXT
    assert el.text == "New Text"
    assert el.fill == {"type": "solid", "color": "#000000"}
    assert el.text_style is not None
    assert el.text_style["font_size"] == 24.0
    assert el.text_style["font_family"] == "Arial"


def test_apply_add_text_preserves_provided_text() -> None:
    service, project = _make_service_with_page()
    op = CanvasAddOperation(
        element_type=ElementType.TEXT,
        x=0.0,
        y=0.0,
        width=100.0,
        height=30.0,
        text="Hello World",
    )

    _apply(service, project, [op])

    assert project.pages[0].elements[0].text == "Hello World"


def test_apply_add_line_sets_points() -> None:
    service, project = _make_service_with_page()
    op = CanvasAddOperation(
        element_type=ElementType.LINE,
        x=0.0,
        y=0.0,
        width=100.0,
        height=50.0,
    )

    _apply(service, project, [op])

    el = project.pages[0].elements[0]
    assert el.points == [0.0, 0.0, 100.0, 50.0]


def test_apply_add_path_sets_points() -> None:
    service, project = _make_service_with_page()
    op = CanvasAddOperation(
        element_type=ElementType.PATH,
        x=0.0,
        y=0.0,
        width=80.0,
        height=60.0,
    )

    _apply(service, project, [op])

    el = project.pages[0].elements[0]
    assert el.points == [0.0, 0.0, 80.0, 60.0]


def test_apply_add_sets_auto_incremented_z_index() -> None:
    existing = _make_rect("el-existing")
    existing_copy = existing.model_copy(update={"z_index": 5})
    service, project = _make_service_with_page(elements=[existing_copy])
    op = CanvasAddOperation(
        element_type=ElementType.ELLIPSE,
        x=0.0,
        y=0.0,
        width=50.0,
        height=50.0,
    )

    _apply(service, project, [op])

    new_el = project.pages[0].elements[-1]
    assert new_el.z_index == 6


def test_apply_add_uses_default_opacity_when_not_provided() -> None:
    service, project = _make_service_with_page()
    op = CanvasAddOperation(
        element_type=ElementType.RECTANGLE,
        x=0.0,
        y=0.0,
        width=50.0,
        height=50.0,
    )

    _apply(service, project, [op])

    assert project.pages[0].elements[0].opacity == 1.0


def test_apply_add_skips_when_element_limit_reached(monkeypatch: pytest.MonkeyPatch) -> None:
    import app.application.services.canvas_service as canvas_svc_module

    fake_settings = MagicMock()
    fake_settings.canvas_max_elements = 1
    fake_settings.canvas_max_versions = 50
    monkeypatch.setattr(canvas_svc_module, "get_settings", lambda: fake_settings)

    service, project = _make_service_with_page(elements=[_make_rect("existing")])
    op = CanvasAddOperation(
        element_type=ElementType.RECTANGLE,
        x=0.0,
        y=0.0,
        width=50.0,
        height=50.0,
    )

    applied = _apply(service, project, [op])

    assert applied is False
    assert len(project.pages[0].elements) == 1


def test_apply_modify_updates_element_fields() -> None:
    el = _make_rect("target")
    service, project = _make_service_with_page(elements=[el])
    op = CanvasModifyOperation(
        element_id="target",
        x=99.0,
        y=88.0,
        width=200.0,
        height=150.0,
        rotation=45.0,
        opacity=0.5,
        text="Updated",
        fill_color="#00FF00",
    )

    applied = _apply(service, project, [op])

    assert applied is True
    updated = project.pages[0].elements[0]
    assert updated.x == 99.0
    assert updated.y == 88.0
    assert updated.width == 200.0
    assert updated.height == 150.0
    assert updated.rotation == 45.0
    assert updated.opacity == 0.5
    assert updated.text == "Updated"
    assert updated.fill == {"type": "solid", "color": "#00FF00"}


def test_apply_modify_font_size_creates_new_text_style_when_none() -> None:
    el = _make_rect("target")
    service, project = _make_service_with_page(elements=[el])
    op = CanvasModifyOperation(element_id="target", font_size=32.0)

    _apply(service, project, [op])

    updated = project.pages[0].elements[0]
    assert updated.text_style is not None
    assert updated.text_style["font_size"] == 32.0


def test_apply_modify_font_size_updates_existing_text_style() -> None:
    el = _make_rect("target")
    el_with_style = el.model_copy(update={"text_style": {"font_family": "Helvetica", "font_size": 16.0}})
    service, project = _make_service_with_page(elements=[el_with_style])
    op = CanvasModifyOperation(element_id="target", font_size=48.0)

    _apply(service, project, [op])

    updated = project.pages[0].elements[0]
    assert updated.text_style is not None
    assert updated.text_style["font_size"] == 48.0
    assert updated.text_style["font_family"] == "Helvetica"


def test_apply_modify_skips_when_element_not_found() -> None:
    el = _make_rect("el-present")
    service, project = _make_service_with_page(elements=[el])
    op = CanvasModifyOperation(element_id="el-absent", x=5.0)

    applied = _apply(service, project, [op])

    assert applied is False


def test_apply_delete_removes_matching_elements() -> None:
    els = [_make_rect(f"el-{i}") for i in range(3)]
    service, project = _make_service_with_page(elements=els)
    op = CanvasDeleteOperation(element_ids=["el-0", "el-2"])

    applied = _apply(service, project, [op])

    assert applied is True
    remaining_ids = {el.id for el in project.pages[0].elements}
    assert remaining_ids == {"el-1"}


def test_apply_delete_skips_when_element_ids_empty() -> None:
    el = _make_rect("el-keep")
    service, project = _make_service_with_page(elements=[el])
    op = CanvasDeleteOperation(element_ids=[])

    applied = _apply(service, project, [op])

    assert applied is False
    assert len(project.pages[0].elements) == 1


def test_apply_delete_reports_not_applied_when_no_ids_matched() -> None:
    el = _make_rect("el-keep")
    service, project = _make_service_with_page(elements=[el])
    op = CanvasDeleteOperation(element_ids=["nonexistent"])

    applied = _apply(service, project, [op])

    assert applied is False


def test_apply_arrange_bring_to_front() -> None:
    el_a = _make_rect("el-a")
    el_a_z = el_a.model_copy(update={"z_index": 1})
    el_b = _make_rect("el-b")
    el_b_z = el_b.model_copy(update={"z_index": 5})
    service, project = _make_service_with_page(elements=[el_a_z, el_b_z])
    op = CanvasArrangeOperation(element_id="el-a", direction="bring_to_front")

    applied = _apply(service, project, [op])

    assert applied is True
    result_el = next(e for e in project.pages[0].elements if e.id == "el-a")
    assert result_el.z_index == 6  # max(1, 5) + 1


def test_apply_arrange_send_to_back() -> None:
    el_a = _make_rect("el-a")
    el_a_z = el_a.model_copy(update={"z_index": 3})
    el_b = _make_rect("el-b")
    el_b_z = el_b.model_copy(update={"z_index": 7})
    service, project = _make_service_with_page(elements=[el_a_z, el_b_z])
    op = CanvasArrangeOperation(element_id="el-b", direction="send_to_back")

    applied = _apply(service, project, [op])

    assert applied is True
    result_el = next(e for e in project.pages[0].elements if e.id == "el-b")
    assert result_el.z_index == 2  # min(3, 7) - 1


def test_apply_arrange_skips_when_element_not_found() -> None:
    el = _make_rect("el-present")
    service, project = _make_service_with_page(elements=[el])
    op = CanvasArrangeOperation(element_id="el-absent", direction="bring_to_front")

    applied = _apply(service, project, [op])

    assert applied is False


def test_apply_edit_operations_returns_false_for_project_with_no_pages() -> None:
    project = _make_project(pages=[])
    service, _ = _service_with_project(project)
    op = CanvasDeleteOperation(element_ids=["el-1"])

    applied = service._apply_edit_operations(project, [op])

    assert applied is False


# ===========================================================================
# _mark_project_mutated
# ===========================================================================


def test_mark_project_mutated_increments_version_and_updates_timestamp() -> None:
    project = _make_project()
    original_version = project.version
    original_ts = project.updated_at

    CanvasService._mark_project_mutated(project)

    assert project.version == original_version + 1
    assert project.updated_at >= original_ts


# ===========================================================================
# _get_project_lock — reuses the same lock object for the same id
# ===========================================================================


@pytest.mark.asyncio
async def test_get_project_lock_returns_same_lock_for_same_project_id() -> None:
    service, _ = _service_with_project()

    lock_a = await service._get_project_lock("proj-x")
    lock_b = await service._get_project_lock("proj-x")
    lock_c = await service._get_project_lock("proj-y")

    assert lock_a is lock_b
    assert lock_a is not lock_c


# ===========================================================================
# AI operations — image generation (ConfigurationException when unconfigured)
# ===========================================================================


@pytest.mark.asyncio
async def test_generate_image_raises_when_service_not_configured() -> None:
    service, _ = _service_with_project()

    mock_service = MagicMock()
    mock_service.is_configured = False

    async def _patched_generate(prompt: str, w: int, h: int) -> list[str]:
        raise ConfigurationException("Image generation not configured (FAL_API_KEY missing)")

    mock_service.generate_image = _patched_generate

    # Inject via monkeypatching the local import inside the method
    import sys

    img_mod = sys.modules.get("app.infrastructure.external.image_generation")
    if img_mod:
        original_get = getattr(img_mod, "get_image_generation_service", None)
        img_mod.get_image_generation_service = lambda: mock_service  # type: ignore[attr-defined]
        try:
            with pytest.raises(ConfigurationException):
                await service.generate_image("a cat", 512, 512)
        finally:
            if original_get is not None:
                img_mod.get_image_generation_service = original_get  # type: ignore[attr-defined]
    else:
        pytest.skip("image_generation module not importable in this environment")


# ===========================================================================
# apply_ai_edit — returns project unchanged when no operations produced
# ===========================================================================


@pytest.mark.asyncio
async def test_apply_ai_edit_returns_none_for_missing_project() -> None:
    service, _ = _service_with_project()

    result = await service.apply_ai_edit("ghost-proj", "make it blue")

    assert result is None


@pytest.mark.asyncio
async def test_apply_ai_edit_returns_none_when_llm_unavailable() -> None:
    project = _make_project()
    service, _ = _service_with_project(project)
    service._llm = None  # Force no LLM

    import app.infrastructure.external.llm as llm_module

    original = getattr(llm_module, "get_llm", None)
    llm_module.get_llm = lambda: None  # type: ignore[attr-defined]
    try:
        result = await service.apply_ai_edit(project.id, "make it blue")
    finally:
        if original is not None:
            llm_module.get_llm = original  # type: ignore[attr-defined]

    assert result is None


@pytest.mark.asyncio
async def test_apply_ai_edit_returns_project_unchanged_when_llm_produces_no_ops() -> None:
    project = _make_project()
    service, _ = _service_with_project(project)

    mock_llm = AsyncMock()
    mock_llm.ask_structured = AsyncMock(return_value=CanvasEditPlan(operations=[]))
    # Ensure ask_structured_with_policy doesn't exist so fallback is used
    del mock_llm.ask_structured_with_policy
    service._llm = mock_llm

    result = await service.apply_ai_edit(project.id, "do nothing")

    assert result is not None
    assert result.id == project.id


@pytest.mark.asyncio
async def test_apply_ai_edit_returns_none_when_llm_raises_exception() -> None:
    project = _make_project()
    service, _ = _service_with_project(project)

    mock_llm = AsyncMock()
    mock_llm.ask_structured = AsyncMock(side_effect=RuntimeError("LLM error"))
    del mock_llm.ask_structured_with_policy
    service._llm = mock_llm

    result = await service.apply_ai_edit(project.id, "crash")

    assert result is None


@pytest.mark.asyncio
async def test_apply_ai_edit_applies_operations_and_saves_project() -> None:
    project = _make_project()
    service, repo = _service_with_project(project)

    op = CanvasAddOperation(
        element_type=ElementType.RECTANGLE,
        x=0.0,
        y=0.0,
        width=100.0,
        height=50.0,
    )
    mock_llm = AsyncMock()
    mock_llm.ask_structured = AsyncMock(return_value=CanvasEditPlan(operations=[op]))
    del mock_llm.ask_structured_with_policy
    service._llm = mock_llm

    result = await service.apply_ai_edit(project.id, "add a rectangle")

    assert result is not None
    stored = await repo.find_by_id(project.id)
    assert stored is not None
    assert len(stored.pages[0].elements) == 1
