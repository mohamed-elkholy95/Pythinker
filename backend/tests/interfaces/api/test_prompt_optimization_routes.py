"""Tests for prompt optimization admin API routes.

Uses a minimal FastAPI app with just the prompt-optimization router
and dependency overrides — no lifespan, no MongoDB, no Redis.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.models.prompt_optimization import (
    OptimizationRun,
    OptimizationRunStatus,
    OptimizerType,
)
from app.domain.models.prompt_profile import (
    PromptPatch,
    PromptProfile,
    PromptTarget,
)
from app.domain.models.user import User, UserRole
from app.interfaces.api.prompt_optimization_routes import router
from app.interfaces.dependencies import (
    get_prompt_optimization_service,
    require_admin_user,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_admin_user() -> User:
    return User(
        id="admin-1",
        fullname="Admin User",
        email="admin@test.com",
        role=UserRole.ADMIN,
    )


def _make_profile(
    profile_id: str = "prof-001",
    is_active: bool = False,
) -> PromptProfile:
    return PromptProfile(
        id=profile_id,
        name="Test Profile",
        version="1.0.0",
        source_run_id="run-abc",
        patches=[
            PromptPatch(
                target=PromptTarget.PLANNER,
                profile_id=profile_id,
                variant_id="v1-planner",
                patch_text="Optimized planner prompt",
            ),
        ],
        validation_summary={"planner_optimized": 0.7},
        is_active=is_active,
    )


def _make_run(
    run_id: str = "run-001",
    status: OptimizationRunStatus = OptimizationRunStatus.PENDING,
) -> OptimizationRun:
    return OptimizationRun(
        id=run_id,
        target=PromptTarget.PLANNER,
        optimizer=OptimizerType.MIPROV2_LIGHT,
        status=status,
        config={"auto": "light"},
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_service() -> AsyncMock:
    """Create a mock PromptOptimizationService."""
    svc = AsyncMock()
    svc.start_run = AsyncMock(return_value=_make_run())
    svc.get_run = AsyncMock(return_value=_make_run())
    svc.list_runs = AsyncMock(return_value=[_make_run()])
    svc.get_profile = AsyncMock(return_value=_make_profile())
    svc.list_profiles = AsyncMock(return_value=[_make_profile()])
    svc.activate_profile = AsyncMock(return_value=_make_profile(is_active=True))
    svc.rollback_profile = AsyncMock(return_value=None)
    return svc


@pytest.fixture
def client(mock_service: AsyncMock) -> TestClient:
    """Minimal FastAPI TestClient with only the prompt-optimization router."""
    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[require_admin_user] = lambda: _make_admin_user()
    app.dependency_overrides[get_prompt_optimization_service] = lambda: mock_service

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


# ---------------------------------------------------------------------------
# POST /runs — start run
# ---------------------------------------------------------------------------


class TestStartRun:
    def test_start_run_success(self, client: TestClient, mock_service: AsyncMock) -> None:
        resp = client.post(
            "/api/v1/prompt-optimization/runs",
            json={"target": "planner", "optimizer": "miprov2_light"},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["id"] == "run-001"
        assert data["target"] == "planner"
        assert data["status"] == "pending"
        mock_service.start_run.assert_awaited_once()

    def test_start_run_invalid_target(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/prompt-optimization/runs",
            json={"target": "invalid_target"},
        )
        assert resp.status_code == 422

    def test_start_run_with_auto_mode(
        self,
        client: TestClient,
        mock_service: AsyncMock,
    ) -> None:
        resp = client.post(
            "/api/v1/prompt-optimization/runs",
            json={"target": "execution", "optimizer": "miprov2", "auto": "heavy"},
        )
        assert resp.status_code == 201
        call_kwargs = mock_service.start_run.call_args
        assert call_kwargs.kwargs["config"]["auto"] == "heavy"

    def test_start_run_invalid_auto_mode(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/prompt-optimization/runs",
            json={"target": "planner", "auto": "extreme"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /runs — list runs
# ---------------------------------------------------------------------------


class TestListRuns:
    def test_list_runs_success(self, client: TestClient, mock_service: AsyncMock) -> None:
        resp = client.get("/api/v1/prompt-optimization/runs")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert len(data["runs"]) == 1

    def test_list_runs_with_limit(self, client: TestClient, mock_service: AsyncMock) -> None:
        resp = client.get("/api/v1/prompt-optimization/runs?limit=5")
        assert resp.status_code == 200
        mock_service.list_runs.assert_awaited_once_with(limit=5)

    def test_list_runs_invalid_limit(self, client: TestClient) -> None:
        resp = client.get("/api/v1/prompt-optimization/runs?limit=0")
        assert resp.status_code == 422

    def test_list_runs_limit_too_large(self, client: TestClient) -> None:
        resp = client.get("/api/v1/prompt-optimization/runs?limit=200")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /runs/{run_id} — get run
# ---------------------------------------------------------------------------


class TestGetRun:
    def test_get_run_found(self, client: TestClient, mock_service: AsyncMock) -> None:
        resp = client.get("/api/v1/prompt-optimization/runs/run-001")
        assert resp.status_code == 200
        assert resp.json()["id"] == "run-001"

    def test_get_run_not_found(self, client: TestClient, mock_service: AsyncMock) -> None:
        mock_service.get_run = AsyncMock(return_value=None)
        resp = client.get("/api/v1/prompt-optimization/runs/nonexistent")
        assert resp.status_code == 404

    def test_get_run_response_shape(self, client: TestClient, mock_service: AsyncMock) -> None:
        resp = client.get("/api/v1/prompt-optimization/runs/run-001")
        data = resp.json()
        assert "id" in data
        assert "target" in data
        assert "optimizer" in data
        assert "status" in data
        assert "created_at" in data


# ---------------------------------------------------------------------------
# GET /profiles — list profiles
# ---------------------------------------------------------------------------


class TestListProfiles:
    def test_list_profiles_success(self, client: TestClient, mock_service: AsyncMock) -> None:
        resp = client.get("/api/v1/prompt-optimization/profiles")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1

    def test_list_profiles_with_limit(
        self,
        client: TestClient,
        mock_service: AsyncMock,
    ) -> None:
        resp = client.get("/api/v1/prompt-optimization/profiles?limit=10")
        assert resp.status_code == 200
        mock_service.list_profiles.assert_awaited_once_with(limit=10)


# ---------------------------------------------------------------------------
# GET /profiles/{profile_id} — get profile
# ---------------------------------------------------------------------------


class TestGetProfile:
    def test_get_profile_found(self, client: TestClient, mock_service: AsyncMock) -> None:
        resp = client.get("/api/v1/prompt-optimization/profiles/prof-001")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == "prof-001"
        assert data["name"] == "Test Profile"
        assert len(data["patches"]) == 1
        assert data["targets"] == ["planner"]

    def test_get_profile_not_found(self, client: TestClient, mock_service: AsyncMock) -> None:
        mock_service.get_profile = AsyncMock(return_value=None)
        resp = client.get("/api/v1/prompt-optimization/profiles/nonexistent")
        assert resp.status_code == 404

    def test_get_profile_response_shape(
        self,
        client: TestClient,
        mock_service: AsyncMock,
    ) -> None:
        resp = client.get("/api/v1/prompt-optimization/profiles/prof-001")
        data = resp.json()
        required_fields = [
            "id",
            "name",
            "version",
            "created_at",
            "source_run_id",
            "is_active",
            "targets",
            "validation_summary",
            "patches",
        ]
        for field in required_fields:
            assert field in data, f"Missing field: {field}"


class TestActivateProfile:
    def test_activate_success(self, client: TestClient, mock_service: AsyncMock) -> None:
        resp = client.post("/api/v1/prompt-optimization/profiles/prof-001/activate")
        assert resp.status_code == 200
        data = resp.json()
        assert data["is_active"] is True
        mock_service.activate_profile.assert_awaited_once_with("prof-001")

    def test_activate_not_found(self, client: TestClient, mock_service: AsyncMock) -> None:
        mock_service.activate_profile = AsyncMock(
            side_effect=ValueError("PromptProfile not found: missing"),
        )
        resp = client.post("/api/v1/prompt-optimization/profiles/missing/activate")
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()


class TestRollbackProfile:
    def test_rollback_success(self, client: TestClient, mock_service: AsyncMock) -> None:
        resp = client.post("/api/v1/prompt-optimization/profiles/prof-001/rollback")
        assert resp.status_code == 204
        mock_service.rollback_profile.assert_awaited_once_with("prof-001")

    def test_rollback_not_found(self, client: TestClient, mock_service: AsyncMock) -> None:
        mock_service.rollback_profile = AsyncMock(
            side_effect=ValueError("PromptProfile not found: missing"),
        )
        resp = client.post("/api/v1/prompt-optimization/profiles/missing/rollback")
        assert resp.status_code == 404
