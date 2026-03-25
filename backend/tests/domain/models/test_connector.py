"""Tests for connector domain models."""

import pytest
from pydantic import ValidationError

from app.domain.models.connector import (
    MCP_BLOCKED_ENV_VARS,
    MCP_COMMAND_ALLOWLIST,
    ConnectorAuthType,
    ConnectorAvailability,
    ConnectorStatus,
    ConnectorType,
    CredentialField,
    CustomApiConfig,
    CustomMcpConfig,
    McpTemplate,
)


@pytest.mark.unit
class TestConnectorTypeEnum:
    def test_all_values(self) -> None:
        expected = {"app", "custom_api", "custom_mcp"}
        assert {t.value for t in ConnectorType} == expected


@pytest.mark.unit
class TestConnectorStatusEnum:
    def test_all_values(self) -> None:
        expected = {"connected", "disconnected", "error", "pending"}
        assert {s.value for s in ConnectorStatus} == expected


@pytest.mark.unit
class TestConnectorAuthTypeEnum:
    def test_all_values(self) -> None:
        expected = {"none", "api_key", "bearer", "basic", "oauth2"}
        assert {t.value for t in ConnectorAuthType} == expected


@pytest.mark.unit
class TestConnectorAvailabilityEnum:
    def test_all_values(self) -> None:
        expected = {"available", "coming_soon", "built_in"}
        assert {a.value for a in ConnectorAvailability} == expected


@pytest.mark.unit
class TestCredentialField:
    def test_basic_construction(self) -> None:
        field = CredentialField(key="api_key", label="API Key")
        assert field.key == "api_key"
        assert field.required is True
        assert field.secret is True

    def test_defaults(self) -> None:
        field = CredentialField(key="k", label="l")
        assert field.description == ""
        assert field.placeholder == ""


@pytest.mark.unit
class TestMcpTemplate:
    def test_basic_construction(self) -> None:
        template = McpTemplate(command="npx")
        assert template.command == "npx"
        assert template.args == []
        assert template.transport == "stdio"
        assert template.credential_fields == []


@pytest.mark.unit
class TestCustomApiConfig:
    def test_valid_url(self) -> None:
        config = CustomApiConfig(base_url="https://api.example.com")
        assert config.base_url == "https://api.example.com"

    def test_http_url_allowed(self) -> None:
        config = CustomApiConfig(base_url="http://localhost:8000")
        assert config.base_url == "http://localhost:8000"

    def test_invalid_url_raises(self) -> None:
        with pytest.raises(ValidationError):
            CustomApiConfig(base_url="ftp://example.com")

    def test_url_too_long_raises(self) -> None:
        with pytest.raises(ValidationError):
            CustomApiConfig(base_url="https://" + "a" * 2050)

    def test_url_stripped(self) -> None:
        config = CustomApiConfig(base_url="  https://api.example.com  ")
        assert config.base_url == "https://api.example.com"

    def test_headers_max_exceeded(self) -> None:
        headers = {f"Header-{i}": f"val{i}" for i in range(25)}
        with pytest.raises(ValidationError):
            CustomApiConfig(base_url="https://api.example.com", headers=headers)

    def test_default_auth_type(self) -> None:
        config = CustomApiConfig(base_url="https://api.example.com")
        assert config.auth_type == ConnectorAuthType.NONE


@pytest.mark.unit
class TestCustomMcpConfig:
    def test_valid_stdio(self) -> None:
        config = CustomMcpConfig(transport="stdio", command="npx")
        assert config.transport == "stdio"

    def test_valid_sse(self) -> None:
        config = CustomMcpConfig(transport="sse", url="http://localhost:3000")
        assert config.transport == "sse"

    def test_valid_streamable_http(self) -> None:
        config = CustomMcpConfig(transport="streamable-http", url="http://localhost:3000")
        assert config.transport == "streamable-http"

    def test_invalid_transport_raises(self) -> None:
        with pytest.raises(ValidationError):
            CustomMcpConfig(transport="websocket")


@pytest.mark.unit
class TestMcpSecurityConstants:
    def test_command_allowlist_contains_npx(self) -> None:
        assert "npx" in MCP_COMMAND_ALLOWLIST

    def test_command_allowlist_contains_python(self) -> None:
        assert "python3" in MCP_COMMAND_ALLOWLIST

    def test_command_allowlist_is_frozenset(self) -> None:
        assert isinstance(MCP_COMMAND_ALLOWLIST, frozenset)

    def test_blocked_env_vars_contains_path(self) -> None:
        assert "PATH" in MCP_BLOCKED_ENV_VARS

    def test_blocked_env_vars_contains_ld_preload(self) -> None:
        assert "LD_PRELOAD" in MCP_BLOCKED_ENV_VARS

    def test_blocked_env_vars_is_frozenset(self) -> None:
        assert isinstance(MCP_BLOCKED_ENV_VARS, frozenset)
