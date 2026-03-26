"""Tests for domain exception hierarchy (app.domain.exceptions.base).

Covers the full exception hierarchy, inheritance chains, error codes,
attributes, and string representations.
"""

import pytest

from app.domain.exceptions.base import (
    AgentConfigurationException,
    AgentNotFoundException,
    AuthenticationException,
    AuthorizationException,
    BusinessRuleViolation,
    ConfigurationException,
    ConnectorNotFoundException,
    DomainException,
    DuplicateResourceException,
    EventNotFoundException,
    FlowException,
    HandoffNotFoundException,
    ImageGenerationException,
    IntegrationException,
    InvalidSessionStateException,
    InvalidStateException,
    InvalidUserStateException,
    KnowledgeBaseException,
    LLMException,
    LLMKeysExhaustedError,
    MergeException,
    MessageNotFoundException,
    ResearchFlowException,
    ResourceLimitExceeded,
    ResourceNotFoundException,
    SandboxCrashError,
    SecurityViolation,
    SessionNotFoundException,
    SkillNotFoundException,
    ToolConfigurationException,
    ToolException,
    ToolExecutionException,
    ToolNotFoundException,
    UserNotFoundException,
    WorkflowConfigurationException,
)

# ── DomainException ──────────────────────────────────────────────────


class TestDomainException:
    """Tests for the base DomainException."""

    def test_message(self) -> None:
        exc = DomainException("something failed")
        assert exc.message == "something failed"
        assert str(exc) == "something failed"

    def test_default_error_code(self) -> None:
        exc = DomainException("test")
        assert exc.error_code == "DomainException"

    def test_custom_error_code(self) -> None:
        exc = DomainException("test", error_code="CUSTOM_CODE")
        assert exc.error_code == "CUSTOM_CODE"

    def test_is_exception(self) -> None:
        exc = DomainException("test")
        assert isinstance(exc, Exception)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(DomainException, match="test error"):
            raise DomainException("test error")


# ── ResourceNotFoundException ────────────────────────────────────────


class TestResourceNotFoundException:
    """Tests for ResourceNotFoundException and subclasses."""

    def test_base_resource_not_found(self) -> None:
        exc = ResourceNotFoundException("Resource missing", "widget", "123")
        assert exc.message == "Resource missing"
        assert exc.resource_type == "widget"
        assert exc.resource_id == "123"
        assert exc.error_code == "RESOURCE_NOT_FOUND"
        assert isinstance(exc, DomainException)

    def test_default_resource_type(self) -> None:
        exc = ResourceNotFoundException("not found")
        assert exc.resource_type == "resource"
        assert exc.resource_id == ""

    def test_session_not_found(self) -> None:
        exc = SessionNotFoundException("abc123")
        assert exc.session_id == "abc123"
        assert exc.resource_type == "session"
        assert exc.resource_id == "abc123"
        assert "abc123" in str(exc)
        assert isinstance(exc, ResourceNotFoundException)

    def test_user_not_found(self) -> None:
        exc = UserNotFoundException("user42")
        assert "user42" in str(exc)
        assert exc.resource_type == "user"
        assert isinstance(exc, ResourceNotFoundException)

    def test_agent_not_found(self) -> None:
        exc = AgentNotFoundException("agent-7")
        assert "agent-7" in str(exc)
        assert exc.resource_type == "agent"
        assert isinstance(exc, ResourceNotFoundException)

    def test_handoff_not_found(self) -> None:
        exc = HandoffNotFoundException("hoff-1")
        assert "hoff-1" in str(exc)
        assert exc.resource_type == "handoff"
        assert isinstance(exc, ResourceNotFoundException)

    def test_handoff_custom_detail(self) -> None:
        exc = HandoffNotFoundException("hoff-1", detail="already completed")
        assert "already completed" in str(exc)

    def test_connector_not_found(self) -> None:
        exc = ConnectorNotFoundException("slack-connector")
        assert "slack-connector" in str(exc)
        assert exc.resource_type == "connector"
        assert isinstance(exc, ResourceNotFoundException)

    def test_skill_not_found(self) -> None:
        exc = SkillNotFoundException("search")
        assert "search" in str(exc)
        assert exc.resource_type == "skill"

    def test_skill_custom_detail(self) -> None:
        exc = SkillNotFoundException("search", detail="disabled")
        assert "disabled" in str(exc)

    def test_message_not_found(self) -> None:
        exc = MessageNotFoundException("msg-99")
        assert "msg-99" in str(exc)
        assert exc.resource_type == "message"

    def test_event_not_found(self) -> None:
        exc = EventNotFoundException("evt-1")
        assert "evt-1" in str(exc)
        assert exc.resource_type == "event"

    def test_event_custom_detail(self) -> None:
        exc = EventNotFoundException("evt-1", detail="already exists")
        assert "already exists" in str(exc)


# ── InvalidStateException ────────────────────────────────────────────


class TestInvalidStateException:
    """Tests for InvalidStateException and subclasses."""

    def test_invalid_state(self) -> None:
        exc = InvalidStateException("Cannot transition")
        assert exc.message == "Cannot transition"
        assert exc.error_code == "INVALID_STATE"
        assert isinstance(exc, DomainException)

    def test_invalid_session_state(self) -> None:
        exc = InvalidSessionStateException("Session already completed")
        assert isinstance(exc, InvalidStateException)
        assert isinstance(exc, DomainException)

    def test_invalid_user_state(self) -> None:
        exc = InvalidUserStateException("Account suspended")
        assert isinstance(exc, InvalidStateException)


# ── BusinessRuleViolation ────────────────────────────────────────────


class TestBusinessRuleViolation:
    """Tests for BusinessRuleViolation and subclasses."""

    def test_business_rule_violation(self) -> None:
        exc = BusinessRuleViolation("Cannot exceed limit")
        assert exc.error_code == "BUSINESS_RULE_VIOLATION"
        assert isinstance(exc, DomainException)

    def test_resource_limit_exceeded(self) -> None:
        exc = ResourceLimitExceeded("Max 10 items")
        assert isinstance(exc, BusinessRuleViolation)

    def test_duplicate_resource(self) -> None:
        exc = DuplicateResourceException("Already exists")
        assert isinstance(exc, BusinessRuleViolation)

    def test_merge_exception(self) -> None:
        exc = MergeException("Cannot merge incompatible types")
        assert isinstance(exc, BusinessRuleViolation)


# ── ConfigurationException ───────────────────────────────────────────


class TestConfigurationException:
    """Tests for ConfigurationException and subclasses."""

    def test_configuration_exception(self) -> None:
        exc = ConfigurationException("Missing config")
        assert exc.error_code == "CONFIGURATION_ERROR"
        assert isinstance(exc, DomainException)

    def test_agent_configuration(self) -> None:
        exc = AgentConfigurationException("Agent config invalid")
        assert isinstance(exc, ConfigurationException)

    def test_workflow_configuration(self) -> None:
        exc = WorkflowConfigurationException("Invalid graph")
        assert isinstance(exc, ConfigurationException)


# ── ToolException ────────────────────────────────────────────────────


class TestToolException:
    """Tests for ToolException and subclasses."""

    def test_tool_exception(self) -> None:
        exc = ToolException("tool failed")
        assert exc.error_code == "TOOL_ERROR"
        assert isinstance(exc, DomainException)

    def test_tool_exception_custom_code(self) -> None:
        exc = ToolException("tool failed", error_code="CUSTOM")
        assert exc.error_code == "CUSTOM"

    def test_tool_not_found(self) -> None:
        exc = ToolNotFoundException("web_search")
        assert exc.tool_name == "web_search"
        assert exc.correction is None
        assert exc.error_code == "TOOL_NOT_FOUND"
        assert isinstance(exc, ToolException)

    def test_tool_not_found_with_correction(self) -> None:
        exc = ToolNotFoundException("serach", correction="Did you mean 'search'?")
        assert exc.tool_name == "serach"
        assert exc.correction == "Did you mean 'search'?"
        assert "Did you mean" in str(exc)

    def test_tool_execution_exception(self) -> None:
        exc = ToolExecutionException("Execution failed")
        assert isinstance(exc, ToolException)

    def test_tool_configuration_exception(self) -> None:
        exc = ToolConfigurationException("Config missing")
        assert isinstance(exc, ToolException)


# ── Auth ─────────────────────────────────────────────────────────────


class TestAuthExceptions:
    """Tests for authentication/authorization exceptions."""

    def test_authentication_default_message(self) -> None:
        exc = AuthenticationException()
        assert exc.message == "Authentication failed"
        assert exc.error_code == "AUTHENTICATION_FAILED"
        assert isinstance(exc, DomainException)

    def test_authentication_custom_message(self) -> None:
        exc = AuthenticationException("Invalid token")
        assert exc.message == "Invalid token"

    def test_authorization_default_message(self) -> None:
        exc = AuthorizationException()
        assert exc.message == "Insufficient permissions"
        assert exc.error_code == "AUTHORIZATION_FAILED"

    def test_authorization_custom_message(self) -> None:
        exc = AuthorizationException("Admin required")
        assert exc.message == "Admin required"


# ── IntegrationException ─────────────────────────────────────────────


class TestIntegrationException:
    """Tests for IntegrationException and subclasses."""

    def test_integration_exception(self) -> None:
        exc = IntegrationException("Service unavailable", service="redis")
        assert exc.service == "redis"
        assert exc.error_code == "INTEGRATION_ERROR"
        assert isinstance(exc, DomainException)

    def test_integration_default_service(self) -> None:
        exc = IntegrationException("error")
        assert exc.service == "unknown"

    def test_llm_exception(self) -> None:
        exc = LLMException("API rate limited")
        assert exc.service == "llm"
        assert isinstance(exc, IntegrationException)

    def test_llm_keys_exhausted(self) -> None:
        exc = LLMKeysExhaustedError("openai", 3)
        assert exc.provider == "openai"
        assert exc.key_count == 3
        assert "3" in str(exc)
        assert "openai" in str(exc)
        assert isinstance(exc, LLMException)

    def test_image_generation_exception(self) -> None:
        exc = ImageGenerationException("DALL-E unavailable")
        assert exc.service == "image_generation"
        assert isinstance(exc, IntegrationException)

    def test_knowledge_base_exception(self) -> None:
        exc = KnowledgeBaseException("RAG failed")
        assert exc.service == "knowledge_base"
        assert isinstance(exc, IntegrationException)


# ── Flow / Workflow ──────────────────────────────────────────────────


class TestFlowExceptions:
    """Tests for flow/workflow exceptions."""

    def test_flow_exception(self) -> None:
        exc = FlowException("Flow failed")
        assert exc.error_code == "FLOW_ERROR"
        assert isinstance(exc, DomainException)

    def test_research_flow_exception(self) -> None:
        exc = ResearchFlowException("Research timed out")
        assert isinstance(exc, FlowException)


# ── Security ─────────────────────────────────────────────────────────


class TestSecurityExceptions:
    """Tests for security-related exceptions."""

    def test_sandbox_crash_default_message(self) -> None:
        exc = SandboxCrashError()
        assert "FAILED state" in exc.message
        assert exc.error_code == "SANDBOX_CRASH"
        assert isinstance(exc, DomainException)

    def test_sandbox_crash_custom_message(self) -> None:
        exc = SandboxCrashError("OOM killed")
        assert exc.message == "OOM killed"

    def test_security_violation(self) -> None:
        exc = SecurityViolation("Path traversal detected")
        assert exc.error_code == "SECURITY_VIOLATION"
        assert isinstance(exc, DomainException)


# ── Inheritance chains ───────────────────────────────────────────────


class TestInheritanceChains:
    """Verify full inheritance chains for catching exceptions at various levels."""

    def test_session_not_found_catches(self) -> None:
        exc = SessionNotFoundException("x")
        assert isinstance(exc, SessionNotFoundException)
        assert isinstance(exc, ResourceNotFoundException)
        assert isinstance(exc, DomainException)
        assert isinstance(exc, Exception)

    def test_llm_keys_exhausted_catches(self) -> None:
        exc = LLMKeysExhaustedError("openai", 1)
        assert isinstance(exc, LLMKeysExhaustedError)
        assert isinstance(exc, LLMException)
        assert isinstance(exc, IntegrationException)
        assert isinstance(exc, DomainException)

    def test_tool_not_found_catches(self) -> None:
        exc = ToolNotFoundException("x")
        assert isinstance(exc, ToolNotFoundException)
        assert isinstance(exc, ToolException)
        assert isinstance(exc, DomainException)

    def test_catch_all_domain_exceptions(self) -> None:
        """All domain exceptions should be catchable via DomainException."""
        exceptions = [
            SessionNotFoundException("x"),
            InvalidSessionStateException("x"),
            BusinessRuleViolation("x"),
            ConfigurationException("x"),
            ToolException("x"),
            AuthenticationException(),
            AuthorizationException(),
            IntegrationException("x"),
            FlowException("x"),
            SandboxCrashError(),
            SecurityViolation("x"),
        ]
        for exc in exceptions:
            assert isinstance(exc, DomainException), f"{type(exc).__name__} not DomainException"
