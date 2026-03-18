"""Tests for usage API routes."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.domain.models.agent_usage import (
    AgentRun,
    AgentRunStatus,
    AgentUsageBreakdownRow,
    AgentUsageSummary,
    AgentUsageTimeseriesPoint,
)
from app.domain.models.user import User
from app.interfaces.api.usage_routes import router
from app.interfaces.dependencies import get_current_user

pytestmark = pytest.mark.unit


def _make_user() -> User:
    return User(
        id="user-1",
        fullname="Test User",
        email="user@example.com",
    )


def _build_client() -> TestClient:
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_current_user] = lambda: _make_user()
    return TestClient(app, raise_server_exceptions=False)


def test_get_agent_usage_summary_route_uses_range_days() -> None:
    mock_service = AsyncMock()
    mock_service.get_agent_usage_summary = AsyncMock(
        return_value=AgentUsageSummary(
            run_count=3,
            completed_run_count=2,
            failed_run_count=1,
            success_rate=2 / 3,
            avg_run_duration_ms=1200.0,
            total_cost=0.42,
            total_input_tokens=300,
            total_cached_input_tokens=40,
            total_output_tokens=120,
            total_reasoning_tokens=20,
            total_tool_calls=5,
            total_mcp_calls=2,
            cache_savings_estimate=0.01,
        )
    )

    with (
        _build_client() as client,
        patch("app.interfaces.api.usage_routes.get_usage_service", return_value=mock_service),
    ):
        response = client.get("/usage/agent/summary?range=7d")

    assert response.status_code == 200
    payload = response.json()
    assert payload["data"]["run_count"] == 3
    assert payload["data"]["total_tool_calls"] == 5
    mock_service.get_agent_usage_summary.assert_awaited_once_with("user-1", days=7)


def test_get_agent_usage_detail_routes_serialize_runs_breakdowns_and_timeseries() -> None:
    mock_service = AsyncMock()
    mock_service.get_recent_agent_runs = AsyncMock(
        return_value=[
            AgentRun(
                run_id="run-1",
                user_id="user-1",
                session_id="session-1",
                status=AgentRunStatus.COMPLETED,
                started_at=datetime(2026, 3, 17, 12, 0, tzinfo=UTC),
                completed_at=datetime(2026, 3, 17, 12, 0, 5, tzinfo=UTC),
                duration_ms=5000.0,
                total_tokens=140,
                estimated_cost_usd=0.12,
                tool_call_count=2,
                mcp_call_count=1,
                primary_model="gpt-4o-mini",
                primary_provider="openai",
            )
        ]
    )
    mock_service.get_agent_usage_breakdown = AsyncMock(
        return_value=[
            AgentUsageBreakdownRow(
                key="gpt-4o-mini",
                run_count=1,
                input_tokens=100,
                cached_input_tokens=20,
                output_tokens=40,
                reasoning_tokens=12,
                cost=0.12,
                avg_duration_ms=800.0,
                error_rate=0.0,
            )
        ]
    )
    mock_service.get_agent_usage_timeseries = AsyncMock(
        return_value=[
            AgentUsageTimeseriesPoint(
                date=datetime(2026, 3, 17, 0, 0, tzinfo=UTC),
                run_count=1,
                success_count=1,
                failed_count=0,
                cost=0.12,
                input_tokens=100,
                cached_input_tokens=20,
                output_tokens=40,
                reasoning_tokens=12,
                tool_calls=2,
                mcp_calls=1,
            )
        ]
    )

    with (
        _build_client() as client,
        patch("app.interfaces.api.usage_routes.get_usage_service", return_value=mock_service),
    ):
        runs_response = client.get("/usage/agent/runs?range=30d&limit=10")
        breakdown_response = client.get("/usage/agent/breakdown?range=30d&group_by=model")
        timeseries_response = client.get("/usage/agent/timeseries?range=30d&bucket=week")

    assert runs_response.status_code == 200
    assert breakdown_response.status_code == 200
    assert timeseries_response.status_code == 200
    assert runs_response.json()["data"]["runs"][0]["run_id"] == "run-1"
    assert breakdown_response.json()["data"]["rows"][0]["key"] == "gpt-4o-mini"
    assert timeseries_response.json()["data"]["points"][0]["run_count"] == 1
    mock_service.get_recent_agent_runs.assert_awaited_once_with("user-1", days=30, limit=10)
    mock_service.get_agent_usage_breakdown.assert_awaited_once_with("user-1", days=30, group_by="model")
    mock_service.get_agent_usage_timeseries.assert_awaited_once_with("user-1", days=30, bucket="week")
