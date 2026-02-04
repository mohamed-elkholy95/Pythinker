"""Tests for rating API endpoints."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_submit_rating_success():
    """Should accept valid rating submission."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 4,
            },
        )
    assert response.status_code == 201
    assert response.json()["status"] == "accepted"


@pytest.mark.asyncio
async def test_submit_rating_with_feedback():
    """Should accept rating with optional feedback."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 5,
                "feedback": "Great report!",
            },
        )
    assert response.status_code == 201
    data = response.json()
    assert data["status"] == "accepted"
    assert "5/5" in data["message"]


@pytest.mark.asyncio
async def test_submit_rating_invalid_value_too_high():
    """Should reject rating values above 5."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 6,  # Invalid: must be 1-5
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_rating_invalid_value_too_low():
    """Should reject rating values below 1."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 0,  # Invalid: must be 1-5
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_rating_missing_session_id():
    """Should reject request without session_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "report_id": "report-456",
                "rating": 4,
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_rating_missing_report_id():
    """Should reject request without report_id."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "rating": 4,
            },
        )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_submit_rating_boundary_values():
    """Should accept boundary rating values (1 and 5)."""
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Test rating = 1
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 1,
            },
        )
        assert response.status_code == 201
        assert "1/5" in response.json()["message"]

        # Test rating = 5
        response = await client.post(
            "/api/v1/ratings",
            json={
                "session_id": "test-session-123",
                "report_id": "report-456",
                "rating": 5,
            },
        )
        assert response.status_code == 201
        assert "5/5" in response.json()["message"]
