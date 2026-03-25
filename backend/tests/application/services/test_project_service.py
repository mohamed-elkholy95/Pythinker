"""Tests for ProjectService application service.

Covers:
- create_project: builds Project and delegates to repo.create
- get_project: delegates to repo.get_by_id
- list_projects: delegates to repo.list_by_user, supports status filter
- update_project: returns None when not found, filters None values, skips unknown keys
- delete_project: delegates to repo.delete
- get_project_context: project not found, no files, with files, file resolution errors
- increment_session_count: delegates to repo.increment_session_count
- get_project_service singleton factory
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.application.services.project_service import ProjectService, get_project_service
from app.domain.models.file import FileInfo
from app.domain.models.project import Project, ProjectContext, ProjectStatus

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_repo() -> AsyncMock:
    return AsyncMock()


def _make_project(
    project_id: str = "proj-001",
    user_id: str = "user-abc",
    name: str = "My Project",
    instructions: str = "Be concise.",
    connector_ids: list[str] | None = None,
    file_ids: list[str] | None = None,
    skill_ids: list[str] | None = None,
    status: ProjectStatus = ProjectStatus.ACTIVE,
) -> Project:
    return Project(
        id=project_id,
        user_id=user_id,
        name=name,
        instructions=instructions,
        connector_ids=connector_ids or [],
        file_ids=file_ids or [],
        skill_ids=skill_ids or [],
        status=status,
    )


def _make_file_info(file_id: str = "f-1", filename: str = "doc.pdf", user_id: str = "user-abc") -> FileInfo:
    return FileInfo(file_id=file_id, filename=filename, user_id=user_id)


def _make_service(
    repo: AsyncMock | None = None,
    file_service_factory=None,
) -> ProjectService:
    return ProjectService(repo=repo or _make_repo(), file_service_factory=file_service_factory)


# ---------------------------------------------------------------------------
# create_project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestCreateProject:
    async def test_creates_project_with_required_fields(self) -> None:
        repo = _make_repo()
        created = _make_project(user_id="u-1", name="Alpha")
        repo.create.return_value = created

        svc = _make_service(repo=repo)
        result = await svc.create_project(user_id="u-1", name="Alpha")

        assert result is created
        repo.create.assert_awaited_once()
        project_arg: Project = repo.create.call_args.args[0]
        assert project_arg.user_id == "u-1"
        assert project_arg.name == "Alpha"

    async def test_instructions_default_to_empty_string(self) -> None:
        repo = _make_repo()
        repo.create.return_value = _make_project(instructions="")

        svc = _make_service(repo=repo)
        await svc.create_project("u-1", "Proj")

        project_arg: Project = repo.create.call_args.args[0]
        assert project_arg.instructions == ""

    async def test_connector_ids_default_to_empty_list(self) -> None:
        repo = _make_repo()
        repo.create.return_value = _make_project()

        svc = _make_service(repo=repo)
        await svc.create_project("u-1", "Proj")

        project_arg: Project = repo.create.call_args.args[0]
        assert project_arg.connector_ids == []

    async def test_connector_ids_are_passed_through(self) -> None:
        repo = _make_repo()
        repo.create.return_value = _make_project()

        svc = _make_service(repo=repo)
        await svc.create_project("u-1", "Proj", connector_ids=["conn-1", "conn-2"])

        project_arg: Project = repo.create.call_args.args[0]
        assert project_arg.connector_ids == ["conn-1", "conn-2"]

    async def test_instructions_are_passed_through(self) -> None:
        repo = _make_repo()
        repo.create.return_value = _make_project()

        svc = _make_service(repo=repo)
        await svc.create_project("u-1", "Proj", instructions="Always reply in JSON.")

        project_arg: Project = repo.create.call_args.args[0]
        assert project_arg.instructions == "Always reply in JSON."


# ---------------------------------------------------------------------------
# get_project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetProject:
    async def test_returns_project_when_found(self) -> None:
        repo = _make_repo()
        project = _make_project(project_id="p-1", user_id="u-1")
        repo.get_by_id.return_value = project

        svc = _make_service(repo=repo)
        result = await svc.get_project("p-1", "u-1")

        assert result is project
        repo.get_by_id.assert_awaited_once_with("p-1", "u-1")

    async def test_returns_none_when_not_found(self) -> None:
        repo = _make_repo()
        repo.get_by_id.return_value = None

        svc = _make_service(repo=repo)
        result = await svc.get_project("no-project", "u-1")

        assert result is None


# ---------------------------------------------------------------------------
# list_projects
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestListProjects:
    async def test_returns_projects_list(self) -> None:
        repo = _make_repo()
        projects = [_make_project(project_id="p-1"), _make_project(project_id="p-2")]
        repo.list_by_user.return_value = projects

        svc = _make_service(repo=repo)
        result = await svc.list_projects("u-1")

        assert result == projects

    async def test_passes_status_filter_to_repo(self) -> None:
        repo = _make_repo()
        repo.list_by_user.return_value = []

        svc = _make_service(repo=repo)
        await svc.list_projects("u-1", status=ProjectStatus.ARCHIVED)

        repo.list_by_user.assert_awaited_once_with("u-1", ProjectStatus.ARCHIVED, 50, 0)

    async def test_passes_limit_and_offset(self) -> None:
        repo = _make_repo()
        repo.list_by_user.return_value = []

        svc = _make_service(repo=repo)
        await svc.list_projects("u-1", limit=10, offset=20)

        repo.list_by_user.assert_awaited_once_with("u-1", None, 10, 20)

    async def test_returns_empty_list_when_no_projects(self) -> None:
        repo = _make_repo()
        repo.list_by_user.return_value = []

        svc = _make_service(repo=repo)
        result = await svc.list_projects("u-no-projects")

        assert result == []


# ---------------------------------------------------------------------------
# update_project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestUpdateProject:
    async def test_returns_none_when_project_not_found(self) -> None:
        repo = _make_repo()
        repo.get_by_id.return_value = None

        svc = _make_service(repo=repo)
        result = await svc.update_project("no-proj", "u-1", {"name": "New"})

        assert result is None
        repo.update.assert_not_awaited()

    async def test_updates_name_field(self) -> None:
        repo = _make_repo()
        project = _make_project(project_id="p-1", name="Old Name")
        repo.get_by_id.return_value = project
        updated = _make_project(project_id="p-1", name="New Name")
        repo.update.return_value = updated

        svc = _make_service(repo=repo)
        result = await svc.update_project("p-1", "u-1", {"name": "New Name"})

        assert result is updated
        repo.update.assert_awaited_once()

    async def test_filters_out_none_values(self) -> None:
        repo = _make_repo()
        project = _make_project(project_id="p-1", name="Keep", instructions="Keep instructions")
        repo.get_by_id.return_value = project
        repo.update.return_value = project

        svc = _make_service(repo=repo)
        await svc.update_project("p-1", "u-1", {"name": None, "instructions": "Updated"})

        project_arg: Project = repo.update.call_args.args[0]
        # name should be unchanged since None was filtered
        assert project_arg.name == "Keep"
        assert project_arg.instructions == "Updated"

    async def test_filters_out_unknown_keys(self) -> None:
        repo = _make_repo()
        project = _make_project(project_id="p-1", name="Original")
        repo.get_by_id.return_value = project
        repo.update.return_value = project

        svc = _make_service(repo=repo)
        # unknown_field does not exist on Project
        await svc.update_project("p-1", "u-1", {"unknown_field": "value", "name": "Changed"})

        project_arg: Project = repo.update.call_args.args[0]
        assert project_arg.name == "Changed"
        assert not hasattr(project_arg, "unknown_field")

    async def test_updated_at_is_refreshed(self) -> None:
        repo = _make_repo()
        old_time = datetime(2024, 1, 1, tzinfo=UTC)
        project = _make_project(project_id="p-1")
        project.updated_at = old_time
        repo.get_by_id.return_value = project
        repo.update.return_value = project

        svc = _make_service(repo=repo)
        await svc.update_project("p-1", "u-1", {"name": "Changed"})

        project_arg: Project = repo.update.call_args.args[0]
        assert project_arg.updated_at > old_time


# ---------------------------------------------------------------------------
# delete_project
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestDeleteProject:
    async def test_returns_true_on_success(self) -> None:
        repo = _make_repo()
        repo.delete.return_value = True

        svc = _make_service(repo=repo)
        result = await svc.delete_project("p-1", "u-1")

        assert result is True
        repo.delete.assert_awaited_once_with("p-1", "u-1")

    async def test_returns_false_when_not_found(self) -> None:
        repo = _make_repo()
        repo.delete.return_value = False

        svc = _make_service(repo=repo)
        result = await svc.delete_project("no-proj", "u-1")

        assert result is False


# ---------------------------------------------------------------------------
# get_project_context
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestGetProjectContext:
    async def test_returns_none_when_project_not_found(self) -> None:
        repo = _make_repo()
        repo.get_by_id.return_value = None

        svc = _make_service(repo=repo)
        result = await svc.get_project_context("no-proj", "u-1")

        assert result is None

    async def test_returns_context_with_no_files(self) -> None:
        repo = _make_repo()
        project = _make_project(instructions="Do X", file_ids=[])
        repo.get_by_id.return_value = project

        svc = _make_service(repo=repo)
        result = await svc.get_project_context("p-1", "u-1")

        assert isinstance(result, ProjectContext)
        assert result.instructions == "Do X"
        assert result.files == []

    async def test_returns_context_with_resolved_files(self) -> None:
        repo = _make_repo()
        project = _make_project(file_ids=["f-1", "f-2"])
        repo.get_by_id.return_value = project

        info1 = _make_file_info(file_id="f-1", filename="a.txt")
        info2 = _make_file_info(file_id="f-2", filename="b.txt")

        file_service_mock = AsyncMock()
        file_service_mock.get_file_info.side_effect = [info1, info2]

        svc = _make_service(repo=repo, file_service_factory=lambda: file_service_mock)
        result = await svc.get_project_context("p-1", "u-1")

        assert len(result.files) == 2
        file_ids = {f.file_id for f in result.files}
        assert file_ids == {"f-1", "f-2"}

    async def test_skips_file_when_get_file_info_returns_none(self) -> None:
        repo = _make_repo()
        project = _make_project(file_ids=["f-1", "f-missing"])
        repo.get_by_id.return_value = project

        info1 = _make_file_info(file_id="f-1")
        file_service_mock = AsyncMock()
        file_service_mock.get_file_info.side_effect = [info1, None]

        svc = _make_service(repo=repo, file_service_factory=lambda: file_service_mock)
        result = await svc.get_project_context("p-1", "u-1")

        assert len(result.files) == 1
        assert result.files[0].file_id == "f-1"

    async def test_skips_file_when_resolution_raises_exception(self) -> None:
        repo = _make_repo()
        project = _make_project(file_ids=["f-err", "f-ok"])
        repo.get_by_id.return_value = project

        good_info = _make_file_info(file_id="f-ok")
        file_service_mock = AsyncMock()
        file_service_mock.get_file_info.side_effect = [RuntimeError("storage error"), good_info]

        svc = _make_service(repo=repo, file_service_factory=lambda: file_service_mock)
        result = await svc.get_project_context("p-1", "u-1")

        assert len(result.files) == 1
        assert result.files[0].file_id == "f-ok"

    async def test_file_ids_without_factory_produces_empty_files(self) -> None:
        repo = _make_repo()
        project = _make_project(file_ids=["f-1", "f-2"])
        repo.get_by_id.return_value = project

        # No file_service_factory provided
        svc = _make_service(repo=repo, file_service_factory=None)
        result = await svc.get_project_context("p-1", "u-1")

        assert isinstance(result, ProjectContext)
        assert result.files == []

    async def test_context_includes_connector_and_skill_ids(self) -> None:
        repo = _make_repo()
        project = _make_project(
            connector_ids=["conn-1"],
            skill_ids=["skill-a", "skill-b"],
        )
        repo.get_by_id.return_value = project

        svc = _make_service(repo=repo)
        result = await svc.get_project_context("p-1", "u-1")

        assert result.connector_ids == ["conn-1"]
        assert result.skill_ids == ["skill-a", "skill-b"]


# ---------------------------------------------------------------------------
# increment_session_count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
class TestIncrementSessionCount:
    async def test_delegates_to_repo_with_default_delta(self) -> None:
        repo = _make_repo()
        svc = _make_service(repo=repo)

        await svc.increment_session_count("p-1")

        repo.increment_session_count.assert_awaited_once_with("p-1", 1)

    async def test_passes_custom_delta(self) -> None:
        repo = _make_repo()
        svc = _make_service(repo=repo)

        await svc.increment_session_count("p-1", delta=5)

        repo.increment_session_count.assert_awaited_once_with("p-1", 5)

    async def test_returns_none(self) -> None:
        repo = _make_repo()
        repo.increment_session_count.return_value = None

        svc = _make_service(repo=repo)
        result = await svc.increment_session_count("p-1")

        assert result is None


# ---------------------------------------------------------------------------
# get_project_service singleton factory
# ---------------------------------------------------------------------------


class TestGetProjectServiceFactory:
    def setup_method(self) -> None:
        import app.application.services.project_service as _mod

        _mod._project_service = None

    def test_returns_project_service_instance(self) -> None:
        import app.application.services.project_service as _mod

        with patch.object(_mod, "MongoProjectRepository", return_value=MagicMock()):
            svc = get_project_service()
            assert isinstance(svc, ProjectService)

    def test_returns_same_instance_on_repeated_calls(self) -> None:
        import app.application.services.project_service as _mod

        with patch.object(_mod, "MongoProjectRepository", return_value=MagicMock()):
            svc1 = get_project_service()
            svc2 = get_project_service()
            assert svc1 is svc2

    def test_creates_new_instance_when_factory_changes(self) -> None:
        import app.application.services.project_service as _mod

        def factory_a():
            return MagicMock()

        def factory_b():
            return MagicMock()

        with patch.object(_mod, "MongoProjectRepository", return_value=MagicMock()):
            svc1 = get_project_service(file_service_factory=factory_a)
            svc2 = get_project_service(file_service_factory=factory_b)
            assert svc1 is not svc2
