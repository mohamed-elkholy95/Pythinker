"""Unit tests for workspace API routes.

NOTE: These tests require a full FastAPI TestClient with proper configuration.
They are skipped by default because they require API keys and database connections.
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import status

from app.domain.models.session import AgentMode, Session, SessionStatus
from app.domain.services.workspace.workspace_templates import (
    RESEARCH_TEMPLATE,
)

# Skip all tests in this module - they require full app configuration
pytestmark = pytest.mark.skip(reason="Requires full app configuration with API keys")


class TestWorkspaceRoutes:
    """Test workspace API routes."""

    @pytest.fixture
    def mock_user(self):
        """Create a mock user."""
        from app.domain.models.user import User

        return User(
            id="user-123",
            fullname="Test User",
            email="test@example.com",
            password_hash="hashed",
        )

    @pytest.fixture
    def test_session(self, mock_user):
        """Create a test session."""
        return Session(
            agent_id="agent-123",
            user_id=mock_user.id,
            mode=AgentMode.AGENT,
            status=SessionStatus.PENDING,
        )

    @pytest.fixture
    def test_session_with_workspace(self, test_session):
        """Create a test session with workspace structure."""
        test_session.workspace_structure = {
            "inputs": "Input files and data sources",
            "research": "Research findings and notes",
            "analysis": "Analysis results",
            "deliverables": "Final reports",
            "logs": "Execution logs",
        }
        return test_session

    # List templates endpoint tests
    @pytest.mark.asyncio
    async def test_list_templates_success(self, client, auth_headers):
        """Test listing all workspace templates."""
        response = client.get("/api/v1/workspace/templates", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["success"] is True
        assert "templates" in data["data"]
        templates = data["data"]["templates"]

        # Should have 4 templates
        assert len(templates) == 4

        # Verify template structure
        for template in templates:
            assert "name" in template
            assert "description" in template
            assert "folders" in template
            assert "trigger_keywords" in template
            assert isinstance(template["folders"], dict)
            assert isinstance(template["trigger_keywords"], list)

    @pytest.mark.asyncio
    async def test_list_templates_contains_all_templates(self, client, auth_headers):
        """Test that list templates returns all expected templates."""
        response = client.get("/api/v1/workspace/templates", headers=auth_headers)

        data = response.json()
        templates = data["data"]["templates"]
        template_names = [t["name"] for t in templates]

        assert "research" in template_names
        assert "data_analysis" in template_names
        assert "code_project" in template_names
        assert "document_generation" in template_names

    @pytest.mark.asyncio
    async def test_list_templates_unauthorized(self, client):
        """Test listing templates without authentication."""
        response = client.get("/api/v1/workspace/templates")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_list_templates_template_details(self, client, auth_headers):
        """Test that templates contain correct details."""
        response = client.get("/api/v1/workspace/templates", headers=auth_headers)

        data = response.json()
        templates = data["data"]["templates"]

        # Find research template
        research = next((t for t in templates if t["name"] == "research"), None)
        assert research is not None

        # Verify research template details
        assert research["description"] == RESEARCH_TEMPLATE.description
        assert research["folders"] == RESEARCH_TEMPLATE.folders
        assert set(research["trigger_keywords"]) == set(RESEARCH_TEMPLATE.trigger_keywords)

    # Get specific template endpoint tests
    @pytest.mark.asyncio
    async def test_get_template_by_name_research(self, client, auth_headers):
        """Test getting research template by name."""
        response = client.get("/api/v1/workspace/templates/research", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["success"] is True
        template = data["data"]

        assert template["name"] == "research"
        assert template["description"] == RESEARCH_TEMPLATE.description
        assert "inputs" in template["folders"]
        assert "research" in template["folders"]
        assert "deliverables" in template["folders"]
        assert len(template["trigger_keywords"]) > 0

    @pytest.mark.asyncio
    async def test_get_template_by_name_data_analysis(self, client, auth_headers):
        """Test getting data analysis template by name."""
        response = client.get("/api/v1/workspace/templates/data_analysis", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        template = data["data"]

        assert template["name"] == "data_analysis"
        assert "data" in template["folders"]
        assert "analysis" in template["folders"]
        assert "notebooks" in template["folders"]

    @pytest.mark.asyncio
    async def test_get_template_by_name_code_project(self, client, auth_headers):
        """Test getting code project template by name."""
        response = client.get("/api/v1/workspace/templates/code_project", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        template = data["data"]

        assert template["name"] == "code_project"
        assert "src" in template["folders"]
        assert "tests" in template["folders"]
        assert "docs" in template["folders"]

    @pytest.mark.asyncio
    async def test_get_template_by_name_document_generation(self, client, auth_headers):
        """Test getting document generation template by name."""
        response = client.get("/api/v1/workspace/templates/document_generation", headers=auth_headers)

        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        template = data["data"]

        assert template["name"] == "document_generation"
        assert "drafts" in template["folders"]
        assert "final" in template["folders"]

    @pytest.mark.asyncio
    async def test_get_template_not_found(self, client, auth_headers):
        """Test getting non-existent template."""
        response = client.get("/api/v1/workspace/templates/nonexistent", headers=auth_headers)

        assert response.status_code == status.HTTP_404_NOT_FOUND

        data = response.json()
        assert "not found" in data["detail"].lower()

    @pytest.mark.asyncio
    async def test_get_template_unauthorized(self, client):
        """Test getting template without authentication."""
        response = client.get("/api/v1/workspace/templates/research")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_template_case_sensitivity(self, client, auth_headers):
        """Test template name case sensitivity."""
        # Assuming template names are lowercase
        response = client.get("/api/v1/workspace/templates/RESEARCH", headers=auth_headers)

        # Should either work (case-insensitive) or return 404
        assert response.status_code in [status.HTTP_200_OK, status.HTTP_404_NOT_FOUND]

    # Get session workspace endpoint tests
    @pytest.mark.asyncio
    async def test_get_session_workspace_with_structure(self, client, auth_headers, test_session_with_workspace):
        """Test getting session workspace when workspace is initialized."""
        with patch("app.interfaces.dependencies.get_agent_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_session = AsyncMock(return_value=test_session_with_workspace)
            mock_get_service.return_value = mock_service

            response = client.get(
                f"/api/v1/workspace/sessions/{test_session_with_workspace.id}",
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            assert data["success"] is True
            workspace = data["data"]

            assert workspace["session_id"] == test_session_with_workspace.id
            assert workspace["workspace_structure"] is not None
            assert "inputs" in workspace["workspace_structure"]
            assert workspace["workspace_root"] == f"/workspace/{test_session_with_workspace.id}"

    @pytest.mark.asyncio
    async def test_get_session_workspace_without_structure(self, client, auth_headers, test_session):
        """Test getting session workspace when workspace is not initialized."""
        with patch("app.interfaces.dependencies.get_agent_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_session = AsyncMock(return_value=test_session)
            mock_get_service.return_value = mock_service

            response = client.get(
                f"/api/v1/workspace/sessions/{test_session.id}",
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_200_OK

            data = response.json()
            workspace = data["data"]

            assert workspace["session_id"] == test_session.id
            assert workspace["workspace_structure"] is None
            assert workspace["workspace_root"] is None

    @pytest.mark.asyncio
    async def test_get_session_workspace_not_found(self, client, auth_headers):
        """Test getting workspace for non-existent session."""
        with patch("app.interfaces.dependencies.get_agent_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_session = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service

            response = client.get(
                "/api/v1/workspace/sessions/nonexistent-session",
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND

    @pytest.mark.asyncio
    async def test_get_session_workspace_unauthorized(self, client):
        """Test getting session workspace without authentication."""
        response = client.get("/api/v1/workspace/sessions/session-123")

        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    @pytest.mark.asyncio
    async def test_get_session_workspace_wrong_user(self, client, auth_headers, test_session):
        """Test getting workspace for session belonging to different user."""
        with patch("app.interfaces.dependencies.get_agent_service") as mock_get_service:
            mock_service = MagicMock()
            # Return None when user doesn't own session
            mock_service.get_session = AsyncMock(return_value=None)
            mock_get_service.return_value = mock_service

            response = client.get(
                f"/api/v1/workspace/sessions/{test_session.id}",
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_404_NOT_FOUND

    # Response format tests
    @pytest.mark.asyncio
    async def test_list_templates_response_format(self, client, auth_headers):
        """Test that list templates response has correct format."""
        response = client.get("/api/v1/workspace/templates", headers=auth_headers)

        data = response.json()

        # Check APIResponse wrapper
        assert "success" in data
        assert "data" in data
        assert "message" in data

        assert data["success"] is True
        assert data["message"] is None or isinstance(data["message"], str)

    @pytest.mark.asyncio
    async def test_get_template_response_format(self, client, auth_headers):
        """Test that get template response has correct format."""
        response = client.get("/api/v1/workspace/templates/research", headers=auth_headers)

        data = response.json()

        # Check APIResponse wrapper
        assert "success" in data
        assert "data" in data
        assert "message" in data

    @pytest.mark.asyncio
    async def test_get_session_workspace_response_format(self, client, auth_headers, test_session):
        """Test that get session workspace response has correct format."""
        with patch("app.interfaces.dependencies.get_agent_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_session = AsyncMock(return_value=test_session)
            mock_get_service.return_value = mock_service

            response = client.get(
                f"/api/v1/workspace/sessions/{test_session.id}",
                headers=auth_headers,
            )

            data = response.json()

            # Check APIResponse wrapper
            assert "success" in data
            assert "data" in data
            assert "message" in data

            # Check workspace response structure
            workspace = data["data"]
            assert "session_id" in workspace
            assert "workspace_structure" in workspace
            assert "workspace_root" in workspace

    # Error handling tests
    @pytest.mark.asyncio
    async def test_list_templates_handles_internal_error(self, client, auth_headers):
        """Test that list templates handles internal errors gracefully."""
        with patch("app.domain.services.workspace.get_all_templates") as mock_get_all:
            mock_get_all.side_effect = Exception("Internal error")

            response = client.get("/api/v1/workspace/templates", headers=auth_headers)

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_get_template_handles_internal_error(self, client, auth_headers):
        """Test that get template handles internal errors gracefully."""
        with patch("app.domain.services.workspace.get_template") as mock_get:
            mock_get.side_effect = Exception("Internal error")

            response = client.get("/api/v1/workspace/templates/research", headers=auth_headers)

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    @pytest.mark.asyncio
    async def test_get_session_workspace_handles_internal_error(self, client, auth_headers):
        """Test that get session workspace handles internal errors gracefully."""
        with patch("app.interfaces.dependencies.get_agent_service") as mock_get_service:
            mock_service = MagicMock()
            mock_service.get_session = AsyncMock(side_effect=Exception("Internal error"))
            mock_get_service.return_value = mock_service

            response = client.get(
                "/api/v1/workspace/sessions/session-123",
                headers=auth_headers,
            )

            assert response.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR

    # OpenAPI/Swagger documentation tests
    @pytest.mark.asyncio
    async def test_workspace_routes_in_openapi_schema(self, client):
        """Test that workspace routes are documented in OpenAPI schema."""
        response = client.get("/openapi.json")

        assert response.status_code == status.HTTP_200_OK

        schema = response.json()
        paths = schema.get("paths", {})

        # Check that workspace endpoints are documented
        assert "/api/v1/workspace/templates" in paths
        assert "/api/v1/workspace/templates/{template_name}" in paths
        assert "/api/v1/workspace/sessions/{session_id}" in paths

    @pytest.mark.asyncio
    async def test_workspace_routes_have_tags(self, client):
        """Test that workspace routes have correct tags."""
        response = client.get("/openapi.json")

        schema = response.json()
        paths = schema.get("paths", {})

        # Check workspace tag
        templates_path = paths.get("/api/v1/workspace/templates", {})
        get_method = templates_path.get("get", {})
        assert "workspace" in get_method.get("tags", [])

    # Integration tests
    @pytest.mark.asyncio
    async def test_full_workflow_list_then_get_template(self, client, auth_headers):
        """Test full workflow: list templates, then get specific one."""
        # List all templates
        list_response = client.get("/api/v1/workspace/templates", headers=auth_headers)
        assert list_response.status_code == status.HTTP_200_OK

        templates = list_response.json()["data"]["templates"]
        first_template_name = templates[0]["name"]

        # Get specific template
        get_response = client.get(
            f"/api/v1/workspace/templates/{first_template_name}",
            headers=auth_headers,
        )
        assert get_response.status_code == status.HTTP_200_OK

        template = get_response.json()["data"]
        assert template["name"] == first_template_name

    # Content validation tests
    @pytest.mark.asyncio
    async def test_templates_have_non_empty_folders(self, client, auth_headers):
        """Test that all templates have at least one folder."""
        response = client.get("/api/v1/workspace/templates", headers=auth_headers)

        templates = response.json()["data"]["templates"]
        for template in templates:
            assert len(template["folders"]) > 0

    @pytest.mark.asyncio
    async def test_templates_have_non_empty_keywords(self, client, auth_headers):
        """Test that all templates have at least one trigger keyword."""
        response = client.get("/api/v1/workspace/templates", headers=auth_headers)

        templates = response.json()["data"]["templates"]
        for template in templates:
            assert len(template["trigger_keywords"]) > 0

    @pytest.mark.asyncio
    async def test_templates_have_descriptions(self, client, auth_headers):
        """Test that all templates have descriptions."""
        response = client.get("/api/v1/workspace/templates", headers=auth_headers)

        templates = response.json()["data"]["templates"]
        for template in templates:
            assert len(template["description"]) > 0

    # Performance tests
    @pytest.mark.asyncio
    async def test_list_templates_response_time(self, client, auth_headers):
        """Test that listing templates is fast."""
        import time

        start = time.time()
        response = client.get("/api/v1/workspace/templates", headers=auth_headers)
        elapsed = time.time() - start

        assert response.status_code == status.HTTP_200_OK
        # Should complete in under 100ms
        assert elapsed < 0.1

    @pytest.mark.asyncio
    async def test_get_template_response_time(self, client, auth_headers):
        """Test that getting a template is fast."""
        import time

        start = time.time()
        response = client.get("/api/v1/workspace/templates/research", headers=auth_headers)
        elapsed = time.time() - start

        assert response.status_code == status.HTTP_200_OK
        # Should complete in under 50ms
        assert elapsed < 0.05


# Fixtures for pytest
@pytest.fixture
def client():
    """Create a test client."""
    from fastapi.testclient import TestClient

    from app.main import app

    return TestClient(app)


@pytest.fixture
def auth_headers(mock_user):
    """Create authentication headers."""
    from datetime import UTC, datetime, timedelta

    import jwt

    from app.core.config import get_settings

    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + timedelta(minutes=30)

    payload = {
        "sub": mock_user.id,
        "fullname": mock_user.fullname,
        "email": mock_user.email,
        "role": mock_user.role.value,
        "is_active": mock_user.is_active,
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "type": "access",
    }

    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return {"Authorization": f"Bearer {token}"}
