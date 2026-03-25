"""Tests for domain exception hierarchy.

Covers construction, message formatting, error_code values,
inheritance relationships, and special attributes for every
exception class defined in app.domain.exceptions.base.
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

# ---------------------------------------------------------------------------
# DomainException — base class
# ---------------------------------------------------------------------------


class TestDomainException:
    def test_construction_with_message_only(self) -> None:
        exc = DomainException("something went wrong")
        assert exc.message == "something went wrong"

    def test_default_error_code_is_class_name(self) -> None:
        exc = DomainException("msg")
        assert exc.error_code == "DomainException"

    def test_custom_error_code(self) -> None:
        exc = DomainException("msg", error_code="MY_CODE")
        assert exc.error_code == "MY_CODE"

    def test_str_returns_message(self) -> None:
        exc = DomainException("readable message")
        assert str(exc) == "readable message"

    def test_is_exception_subclass(self) -> None:
        exc = DomainException("msg")
        assert isinstance(exc, Exception)

    def test_can_be_raised_and_caught(self) -> None:
        with pytest.raises(DomainException) as exc_info:
            raise DomainException("raised")
        assert exc_info.value.message == "raised"


# ---------------------------------------------------------------------------
# ResourceNotFoundException
# ---------------------------------------------------------------------------


class TestResourceNotFoundException:
    def test_construction_message_only(self) -> None:
        exc = ResourceNotFoundException("not found")
        assert exc.message == "not found"

    def test_default_resource_type(self) -> None:
        exc = ResourceNotFoundException("not found")
        assert exc.resource_type == "resource"

    def test_default_resource_id(self) -> None:
        exc = ResourceNotFoundException("not found")
        assert exc.resource_id == ""

    def test_custom_resource_type_and_id(self) -> None:
        exc = ResourceNotFoundException("oops", resource_type="widget", resource_id="w-42")
        assert exc.resource_type == "widget"
        assert exc.resource_id == "w-42"

    def test_error_code(self) -> None:
        exc = ResourceNotFoundException("oops")
        assert exc.error_code == "RESOURCE_NOT_FOUND"

    def test_is_domain_exception(self) -> None:
        exc = ResourceNotFoundException("oops")
        assert isinstance(exc, DomainException)

    def test_str_returns_message(self) -> None:
        exc = ResourceNotFoundException("custom msg")
        assert str(exc) == "custom msg"


# ---------------------------------------------------------------------------
# SessionNotFoundException
# ---------------------------------------------------------------------------


class TestSessionNotFoundException:
    def test_construction(self) -> None:
        exc = SessionNotFoundException("sess-123")
        assert "sess-123" in exc.message

    def test_message_format(self) -> None:
        exc = SessionNotFoundException("sess-abc")
        assert exc.message == "Session sess-abc not found"

    def test_session_id_attribute(self) -> None:
        exc = SessionNotFoundException("sess-xyz")
        assert exc.session_id == "sess-xyz"

    def test_resource_type(self) -> None:
        exc = SessionNotFoundException("s1")
        assert exc.resource_type == "session"

    def test_resource_id(self) -> None:
        exc = SessionNotFoundException("s1")
        assert exc.resource_id == "s1"

    def test_error_code(self) -> None:
        exc = SessionNotFoundException("s1")
        assert exc.error_code == "RESOURCE_NOT_FOUND"

    def test_inheritance(self) -> None:
        exc = SessionNotFoundException("s1")
        assert isinstance(exc, ResourceNotFoundException)
        assert isinstance(exc, DomainException)


# ---------------------------------------------------------------------------
# UserNotFoundException
# ---------------------------------------------------------------------------


class TestUserNotFoundException:
    def test_message_format(self) -> None:
        exc = UserNotFoundException("user-99")
        assert exc.message == "User not found: user-99"

    def test_resource_type(self) -> None:
        exc = UserNotFoundException("u1")
        assert exc.resource_type == "user"

    def test_resource_id(self) -> None:
        exc = UserNotFoundException("u1")
        assert exc.resource_id == "u1"

    def test_inheritance(self) -> None:
        exc = UserNotFoundException("u1")
        assert isinstance(exc, ResourceNotFoundException)
        assert isinstance(exc, DomainException)


# ---------------------------------------------------------------------------
# AgentNotFoundException
# ---------------------------------------------------------------------------


class TestAgentNotFoundException:
    def test_message_format(self) -> None:
        exc = AgentNotFoundException("agent-7")
        assert exc.message == "Agent agent-7 not found"

    def test_resource_type(self) -> None:
        exc = AgentNotFoundException("a1")
        assert exc.resource_type == "agent"

    def test_resource_id(self) -> None:
        exc = AgentNotFoundException("a1")
        assert exc.resource_id == "a1"

    def test_inheritance(self) -> None:
        exc = AgentNotFoundException("a1")
        assert isinstance(exc, ResourceNotFoundException)


# ---------------------------------------------------------------------------
# HandoffNotFoundException
# ---------------------------------------------------------------------------


class TestHandoffNotFoundException:
    def test_default_detail(self) -> None:
        exc = HandoffNotFoundException("h-1")
        assert exc.message == "Handoff h-1 not found or not pending"

    def test_custom_detail(self) -> None:
        exc = HandoffNotFoundException("h-2", detail="already completed")
        assert exc.message == "Handoff h-2 already completed"

    def test_resource_type(self) -> None:
        exc = HandoffNotFoundException("h-1")
        assert exc.resource_type == "handoff"

    def test_resource_id(self) -> None:
        exc = HandoffNotFoundException("h-1")
        assert exc.resource_id == "h-1"

    def test_inheritance(self) -> None:
        exc = HandoffNotFoundException("h-1")
        assert isinstance(exc, ResourceNotFoundException)


# ---------------------------------------------------------------------------
# ConnectorNotFoundException
# ---------------------------------------------------------------------------


class TestConnectorNotFoundException:
    def test_message_format(self) -> None:
        exc = ConnectorNotFoundException("telegram")
        assert exc.message == "Connector 'telegram' not found in catalog"

    def test_resource_type(self) -> None:
        exc = ConnectorNotFoundException("slack")
        assert exc.resource_type == "connector"

    def test_resource_id(self) -> None:
        exc = ConnectorNotFoundException("slack")
        assert exc.resource_id == "slack"

    def test_inheritance(self) -> None:
        exc = ConnectorNotFoundException("c1")
        assert isinstance(exc, ResourceNotFoundException)


# ---------------------------------------------------------------------------
# SkillNotFoundException
# ---------------------------------------------------------------------------


class TestSkillNotFoundException:
    def test_default_detail(self) -> None:
        exc = SkillNotFoundException("summarize")
        assert exc.message == "Skill 'summarize' not found"

    def test_custom_detail(self) -> None:
        exc = SkillNotFoundException("summarize", detail="disabled")
        assert exc.message == "Skill 'summarize' disabled"

    def test_resource_type(self) -> None:
        exc = SkillNotFoundException("s1")
        assert exc.resource_type == "skill"

    def test_inheritance(self) -> None:
        exc = SkillNotFoundException("s1")
        assert isinstance(exc, ResourceNotFoundException)


# ---------------------------------------------------------------------------
# MessageNotFoundException
# ---------------------------------------------------------------------------


class TestMessageNotFoundException:
    def test_message_format(self) -> None:
        exc = MessageNotFoundException("msg-42")
        assert exc.message == "Message not found: msg-42"

    def test_resource_type(self) -> None:
        exc = MessageNotFoundException("m1")
        assert exc.resource_type == "message"

    def test_resource_id(self) -> None:
        exc = MessageNotFoundException("m1")
        assert exc.resource_id == "m1"

    def test_inheritance(self) -> None:
        exc = MessageNotFoundException("m1")
        assert isinstance(exc, ResourceNotFoundException)


# ---------------------------------------------------------------------------
# EventNotFoundException
# ---------------------------------------------------------------------------


class TestEventNotFoundException:
    def test_default_detail(self) -> None:
        exc = EventNotFoundException("evt-1")
        assert exc.message == "Event evt-1 not found"

    def test_custom_detail(self) -> None:
        exc = EventNotFoundException("evt-1", detail="already processed")
        assert exc.message == "Event evt-1 already processed"

    def test_resource_type(self) -> None:
        exc = EventNotFoundException("e1")
        assert exc.resource_type == "event"

    def test_inheritance(self) -> None:
        exc = EventNotFoundException("e1")
        assert isinstance(exc, ResourceNotFoundException)


# ---------------------------------------------------------------------------
# InvalidStateException
# ---------------------------------------------------------------------------


class TestInvalidStateException:
    def test_construction(self) -> None:
        exc = InvalidStateException("bad state")
        assert exc.message == "bad state"

    def test_error_code(self) -> None:
        exc = InvalidStateException("bad state")
        assert exc.error_code == "INVALID_STATE"

    def test_str(self) -> None:
        exc = InvalidStateException("bad state")
        assert str(exc) == "bad state"

    def test_inheritance(self) -> None:
        exc = InvalidStateException("bad state")
        assert isinstance(exc, DomainException)


class TestInvalidSessionStateException:
    def test_construction(self) -> None:
        exc = InvalidSessionStateException("session is closed")
        assert exc.message == "session is closed"

    def test_error_code_inherited(self) -> None:
        exc = InvalidSessionStateException("x")
        assert exc.error_code == "INVALID_STATE"

    def test_inheritance(self) -> None:
        exc = InvalidSessionStateException("x")
        assert isinstance(exc, InvalidStateException)
        assert isinstance(exc, DomainException)


class TestInvalidUserStateException:
    def test_construction(self) -> None:
        exc = InvalidUserStateException("user suspended")
        assert exc.message == "user suspended"

    def test_error_code_inherited(self) -> None:
        exc = InvalidUserStateException("x")
        assert exc.error_code == "INVALID_STATE"

    def test_inheritance(self) -> None:
        exc = InvalidUserStateException("x")
        assert isinstance(exc, InvalidStateException)
        assert isinstance(exc, DomainException)


# ---------------------------------------------------------------------------
# BusinessRuleViolation
# ---------------------------------------------------------------------------


class TestBusinessRuleViolation:
    def test_construction(self) -> None:
        exc = BusinessRuleViolation("limit exceeded")
        assert exc.message == "limit exceeded"

    def test_error_code(self) -> None:
        exc = BusinessRuleViolation("x")
        assert exc.error_code == "BUSINESS_RULE_VIOLATION"

    def test_inheritance(self) -> None:
        exc = BusinessRuleViolation("x")
        assert isinstance(exc, DomainException)


class TestResourceLimitExceeded:
    def test_construction(self) -> None:
        exc = ResourceLimitExceeded("too many tasks")
        assert exc.message == "too many tasks"

    def test_error_code_inherited(self) -> None:
        exc = ResourceLimitExceeded("x")
        assert exc.error_code == "BUSINESS_RULE_VIOLATION"

    def test_inheritance(self) -> None:
        exc = ResourceLimitExceeded("x")
        assert isinstance(exc, BusinessRuleViolation)
        assert isinstance(exc, DomainException)


class TestDuplicateResourceException:
    def test_construction(self) -> None:
        exc = DuplicateResourceException("already exists")
        assert exc.message == "already exists"

    def test_inheritance(self) -> None:
        exc = DuplicateResourceException("x")
        assert isinstance(exc, BusinessRuleViolation)


class TestMergeException:
    def test_construction(self) -> None:
        exc = MergeException("merge failed")
        assert exc.message == "merge failed"

    def test_inheritance(self) -> None:
        exc = MergeException("x")
        assert isinstance(exc, BusinessRuleViolation)


# ---------------------------------------------------------------------------
# ConfigurationException
# ---------------------------------------------------------------------------


class TestConfigurationException:
    def test_construction(self) -> None:
        exc = ConfigurationException("bad config")
        assert exc.message == "bad config"

    def test_error_code(self) -> None:
        exc = ConfigurationException("x")
        assert exc.error_code == "CONFIGURATION_ERROR"

    def test_inheritance(self) -> None:
        exc = ConfigurationException("x")
        assert isinstance(exc, DomainException)


class TestAgentConfigurationException:
    def test_construction(self) -> None:
        exc = AgentConfigurationException("missing model")
        assert exc.message == "missing model"

    def test_error_code_inherited(self) -> None:
        exc = AgentConfigurationException("x")
        assert exc.error_code == "CONFIGURATION_ERROR"

    def test_inheritance(self) -> None:
        exc = AgentConfigurationException("x")
        assert isinstance(exc, ConfigurationException)
        assert isinstance(exc, DomainException)


class TestWorkflowConfigurationException:
    def test_construction(self) -> None:
        exc = WorkflowConfigurationException("invalid graph")
        assert exc.message == "invalid graph"

    def test_inheritance(self) -> None:
        exc = WorkflowConfigurationException("x")
        assert isinstance(exc, ConfigurationException)


# ---------------------------------------------------------------------------
# ToolException
# ---------------------------------------------------------------------------


class TestToolException:
    def test_construction_default_error_code(self) -> None:
        exc = ToolException("tool broke")
        assert exc.error_code == "TOOL_ERROR"

    def test_construction_custom_error_code(self) -> None:
        exc = ToolException("tool broke", error_code="MY_TOOL_ERR")
        assert exc.error_code == "MY_TOOL_ERR"

    def test_message(self) -> None:
        exc = ToolException("tool broke")
        assert exc.message == "tool broke"

    def test_inheritance(self) -> None:
        exc = ToolException("x")
        assert isinstance(exc, DomainException)


class TestToolNotFoundException:
    def test_construction_without_correction(self) -> None:
        exc = ToolNotFoundException("search_web")
        assert exc.tool_name == "search_web"
        assert exc.correction is None
        assert exc.message == "Tool 'search_web' not found"

    def test_construction_with_correction(self) -> None:
        exc = ToolNotFoundException("searchweb", correction="Did you mean search_web?")
        assert exc.tool_name == "searchweb"
        assert exc.correction == "Did you mean search_web?"
        assert exc.message == "Did you mean search_web?"

    def test_error_code(self) -> None:
        exc = ToolNotFoundException("t1")
        assert exc.error_code == "TOOL_NOT_FOUND"

    def test_inheritance(self) -> None:
        exc = ToolNotFoundException("t1")
        assert isinstance(exc, ToolException)
        assert isinstance(exc, DomainException)


class TestToolExecutionException:
    def test_construction(self) -> None:
        exc = ToolExecutionException("execution failed")
        assert exc.message == "execution failed"

    def test_inheritance(self) -> None:
        exc = ToolExecutionException("x")
        assert isinstance(exc, ToolException)


class TestToolConfigurationException:
    def test_construction(self) -> None:
        exc = ToolConfigurationException("missing key")
        assert exc.message == "missing key"

    def test_inheritance(self) -> None:
        exc = ToolConfigurationException("x")
        assert isinstance(exc, ToolException)


# ---------------------------------------------------------------------------
# AuthenticationException
# ---------------------------------------------------------------------------


class TestAuthenticationException:
    def test_default_message(self) -> None:
        exc = AuthenticationException()
        assert exc.message == "Authentication failed"

    def test_custom_message(self) -> None:
        exc = AuthenticationException("token expired")
        assert exc.message == "token expired"

    def test_error_code(self) -> None:
        exc = AuthenticationException()
        assert exc.error_code == "AUTHENTICATION_FAILED"

    def test_str_default(self) -> None:
        exc = AuthenticationException()
        assert str(exc) == "Authentication failed"

    def test_inheritance(self) -> None:
        exc = AuthenticationException()
        assert isinstance(exc, DomainException)


# ---------------------------------------------------------------------------
# AuthorizationException
# ---------------------------------------------------------------------------


class TestAuthorizationException:
    def test_default_message(self) -> None:
        exc = AuthorizationException()
        assert exc.message == "Insufficient permissions"

    def test_custom_message(self) -> None:
        exc = AuthorizationException("admin only")
        assert exc.message == "admin only"

    def test_error_code(self) -> None:
        exc = AuthorizationException()
        assert exc.error_code == "AUTHORIZATION_FAILED"

    def test_str_default(self) -> None:
        exc = AuthorizationException()
        assert str(exc) == "Insufficient permissions"

    def test_inheritance(self) -> None:
        exc = AuthorizationException()
        assert isinstance(exc, DomainException)


# ---------------------------------------------------------------------------
# IntegrationException
# ---------------------------------------------------------------------------


class TestIntegrationException:
    def test_construction_default_service(self) -> None:
        exc = IntegrationException("integration broke")
        assert exc.service == "unknown"

    def test_construction_custom_service(self) -> None:
        exc = IntegrationException("broke", service="stripe")
        assert exc.service == "stripe"

    def test_message(self) -> None:
        exc = IntegrationException("integration broke")
        assert exc.message == "integration broke"

    def test_error_code(self) -> None:
        exc = IntegrationException("x")
        assert exc.error_code == "INTEGRATION_ERROR"

    def test_inheritance(self) -> None:
        exc = IntegrationException("x")
        assert isinstance(exc, DomainException)


# ---------------------------------------------------------------------------
# LLMException
# ---------------------------------------------------------------------------


class TestLLMException:
    def test_construction(self) -> None:
        exc = LLMException("model timeout")
        assert exc.message == "model timeout"

    def test_service_attribute(self) -> None:
        exc = LLMException("model timeout")
        assert exc.service == "llm"

    def test_error_code_inherited(self) -> None:
        exc = LLMException("x")
        assert exc.error_code == "INTEGRATION_ERROR"

    def test_inheritance(self) -> None:
        exc = LLMException("x")
        assert isinstance(exc, IntegrationException)
        assert isinstance(exc, DomainException)


# ---------------------------------------------------------------------------
# LLMKeysExhaustedError
# ---------------------------------------------------------------------------


class TestLLMKeysExhaustedError:
    def test_construction(self) -> None:
        exc = LLMKeysExhaustedError(provider="openai", key_count=3)
        assert exc.provider == "openai"
        assert exc.key_count == 3

    def test_message_format(self) -> None:
        exc = LLMKeysExhaustedError(provider="anthropic", key_count=2)
        assert exc.message == "All 2 anthropic API keys exhausted"

    def test_service_attribute(self) -> None:
        exc = LLMKeysExhaustedError(provider="openai", key_count=1)
        assert exc.service == "llm"

    def test_inheritance(self) -> None:
        exc = LLMKeysExhaustedError(provider="openai", key_count=1)
        assert isinstance(exc, LLMException)
        assert isinstance(exc, IntegrationException)
        assert isinstance(exc, DomainException)

    def test_single_key(self) -> None:
        exc = LLMKeysExhaustedError(provider="openai", key_count=1)
        assert "1" in exc.message
        assert "openai" in exc.message


# ---------------------------------------------------------------------------
# ImageGenerationException
# ---------------------------------------------------------------------------


class TestImageGenerationException:
    def test_construction(self) -> None:
        exc = ImageGenerationException("service unavailable")
        assert exc.message == "service unavailable"

    def test_service_attribute(self) -> None:
        exc = ImageGenerationException("x")
        assert exc.service == "image_generation"

    def test_inheritance(self) -> None:
        exc = ImageGenerationException("x")
        assert isinstance(exc, IntegrationException)


# ---------------------------------------------------------------------------
# KnowledgeBaseException
# ---------------------------------------------------------------------------


class TestKnowledgeBaseException:
    def test_construction(self) -> None:
        exc = KnowledgeBaseException("index error")
        assert exc.message == "index error"

    def test_service_attribute(self) -> None:
        exc = KnowledgeBaseException("x")
        assert exc.service == "knowledge_base"

    def test_inheritance(self) -> None:
        exc = KnowledgeBaseException("x")
        assert isinstance(exc, IntegrationException)


# ---------------------------------------------------------------------------
# FlowException
# ---------------------------------------------------------------------------


class TestFlowException:
    def test_construction(self) -> None:
        exc = FlowException("flow broke")
        assert exc.message == "flow broke"

    def test_error_code(self) -> None:
        exc = FlowException("x")
        assert exc.error_code == "FLOW_ERROR"

    def test_inheritance(self) -> None:
        exc = FlowException("x")
        assert isinstance(exc, DomainException)


class TestResearchFlowException:
    def test_construction(self) -> None:
        exc = ResearchFlowException("research failed")
        assert exc.message == "research failed"

    def test_error_code_inherited(self) -> None:
        exc = ResearchFlowException("x")
        assert exc.error_code == "FLOW_ERROR"

    def test_inheritance(self) -> None:
        exc = ResearchFlowException("x")
        assert isinstance(exc, FlowException)
        assert isinstance(exc, DomainException)


# ---------------------------------------------------------------------------
# SandboxCrashError
# ---------------------------------------------------------------------------


class TestSandboxCrashError:
    def test_default_message(self) -> None:
        exc = SandboxCrashError()
        assert exc.message == "Sandbox is in FAILED state - cannot execute tools"

    def test_custom_message(self) -> None:
        exc = SandboxCrashError("container OOM killed")
        assert exc.message == "container OOM killed"

    def test_error_code(self) -> None:
        exc = SandboxCrashError()
        assert exc.error_code == "SANDBOX_CRASH"

    def test_str_default(self) -> None:
        exc = SandboxCrashError()
        assert str(exc) == "Sandbox is in FAILED state - cannot execute tools"

    def test_inheritance(self) -> None:
        exc = SandboxCrashError()
        assert isinstance(exc, DomainException)


# ---------------------------------------------------------------------------
# SecurityViolation
# ---------------------------------------------------------------------------


class TestSecurityViolation:
    def test_construction(self) -> None:
        exc = SecurityViolation("path traversal detected")
        assert exc.message == "path traversal detected"

    def test_error_code(self) -> None:
        exc = SecurityViolation("x")
        assert exc.error_code == "SECURITY_VIOLATION"

    def test_inheritance(self) -> None:
        exc = SecurityViolation("x")
        assert isinstance(exc, DomainException)

    def test_str(self) -> None:
        exc = SecurityViolation("injection attempt")
        assert str(exc) == "injection attempt"


# ---------------------------------------------------------------------------
# Cross-cutting: catchability via base types
# ---------------------------------------------------------------------------


class TestCrossCuttingCatchability:
    def test_session_not_found_caught_as_resource_not_found(self) -> None:
        with pytest.raises(ResourceNotFoundException):
            raise SessionNotFoundException("s-1")

    def test_session_not_found_caught_as_domain_exception(self) -> None:
        with pytest.raises(DomainException):
            raise SessionNotFoundException("s-1")

    def test_llm_keys_exhausted_caught_as_llm_exception(self) -> None:
        with pytest.raises(LLMException):
            raise LLMKeysExhaustedError(provider="openai", key_count=2)

    def test_llm_keys_exhausted_caught_as_integration_exception(self) -> None:
        with pytest.raises(IntegrationException):
            raise LLMKeysExhaustedError(provider="openai", key_count=2)

    def test_tool_not_found_caught_as_tool_exception(self) -> None:
        with pytest.raises(ToolException):
            raise ToolNotFoundException("my_tool")

    def test_research_flow_caught_as_flow_exception(self) -> None:
        with pytest.raises(FlowException):
            raise ResearchFlowException("failed")

    def test_resource_limit_caught_as_business_rule_violation(self) -> None:
        with pytest.raises(BusinessRuleViolation):
            raise ResourceLimitExceeded("too many")

    def test_invalid_session_state_caught_as_invalid_state(self) -> None:
        with pytest.raises(InvalidStateException):
            raise InvalidSessionStateException("closed")
