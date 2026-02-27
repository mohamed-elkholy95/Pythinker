"""Domain-specific exceptions for business rule violations.

Domain exceptions represent business rule violations and expected error
conditions that should be handled by the application layer. They replace
the anti-pattern of using ValueError for business logic failures.

ValueError should ONLY be used for:
- Invalid function arguments (type/format issues in Pydantic validators)
- Enum parsing errors
- Other genuine programming mistakes

Hierarchy:
    DomainException
    ├── ResourceNotFoundException
    │   ├── SessionNotFoundException
    │   ├── UserNotFoundException
    │   ├── AgentNotFoundException
    │   └── HandoffNotFoundException
    ├── InvalidStateException
    │   ├── InvalidSessionStateException
    │   └── InvalidUserStateException
    ├── BusinessRuleViolation
    │   └── ResourceLimitExceeded
    ├── ConfigurationException
    │   ├── AgentConfigurationException
    │   └── WorkflowConfigurationException
    ├── ToolException
    │   ├── ToolNotFoundException
    │   └── ToolExecutionException
    ├── AuthenticationException
    ├── AuthorizationException
    └── IntegrationException
        └── LLMException
"""


class DomainException(Exception):  # noqa: N818
    """Base exception for all domain errors.

    Domain exceptions represent business rule violations that are expected
    and should be handled by the application layer. They carry an error_code
    for programmatic handling and a human-readable message.
    """

    def __init__(self, message: str, error_code: str | None = None) -> None:
        self.message = message
        self.error_code = error_code or self.__class__.__name__
        super().__init__(self.message)

    def __str__(self) -> str:
        return self.message


# ── Resource Not Found ────────────────────────────────────────────────


class ResourceNotFoundException(DomainException):
    """Raised when a requested resource cannot be found."""

    def __init__(self, message: str, resource_type: str = "resource", resource_id: str = "") -> None:
        self.resource_type = resource_type
        self.resource_id = resource_id
        super().__init__(message, error_code="RESOURCE_NOT_FOUND")


class SessionNotFoundException(ResourceNotFoundException):
    """Raised when a session cannot be found."""

    def __init__(self, session_id: str) -> None:
        self.session_id = session_id
        super().__init__(
            message=f"Session {session_id} not found",
            resource_type="session",
            resource_id=session_id,
        )


class UserNotFoundException(ResourceNotFoundException):
    """Raised when a user cannot be found."""

    def __init__(self, user_id: str) -> None:
        super().__init__(
            message=f"User not found: {user_id}",
            resource_type="user",
            resource_id=user_id,
        )


class AgentNotFoundException(ResourceNotFoundException):
    """Raised when an agent cannot be found."""

    def __init__(self, agent_id: str) -> None:
        super().__init__(
            message=f"Agent {agent_id} not found",
            resource_type="agent",
            resource_id=agent_id,
        )


class HandoffNotFoundException(ResourceNotFoundException):
    """Raised when a handoff cannot be found or is not in the expected state."""

    def __init__(self, handoff_id: str, detail: str = "not found or not pending") -> None:
        super().__init__(
            message=f"Handoff {handoff_id} {detail}",
            resource_type="handoff",
            resource_id=handoff_id,
        )


class ConnectorNotFoundException(ResourceNotFoundException):
    """Raised when a connector cannot be found in the catalog."""

    def __init__(self, connector_id: str) -> None:
        super().__init__(
            message=f"Connector '{connector_id}' not found in catalog",
            resource_type="connector",
            resource_id=connector_id,
        )


class SkillNotFoundException(ResourceNotFoundException):
    """Raised when a skill cannot be found."""

    def __init__(self, skill_id: str, detail: str = "not found") -> None:
        super().__init__(
            message=f"Skill '{skill_id}' {detail}",
            resource_type="skill",
            resource_id=skill_id,
        )


class MessageNotFoundException(ResourceNotFoundException):
    """Raised when a message cannot be found."""

    def __init__(self, message_id: str) -> None:
        super().__init__(
            message=f"Message not found: {message_id}",
            resource_type="message",
            resource_id=message_id,
        )


class EventNotFoundException(ResourceNotFoundException):
    """Raised when an event cannot be found or already exists."""

    def __init__(self, event_id: str, detail: str = "not found") -> None:
        super().__init__(
            message=f"Event {event_id} {detail}",
            resource_type="event",
            resource_id=event_id,
        )


# ── Invalid State ─────────────────────────────────────────────────────


class InvalidStateException(DomainException):
    """Raised when an entity is in an invalid state for the requested operation."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="INVALID_STATE")


class InvalidSessionStateException(InvalidStateException):
    """Raised when a session is in an invalid state for the requested operation."""


class InvalidUserStateException(InvalidStateException):
    """Raised when a user account is in an invalid state."""


# ── Business Rule Violations ──────────────────────────────────────────


class BusinessRuleViolation(DomainException):
    """Raised when a business rule is violated."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="BUSINESS_RULE_VIOLATION")


class ResourceLimitExceeded(BusinessRuleViolation):
    """Raised when a resource limit is exceeded (e.g., max elements, max parallel tasks)."""


class DuplicateResourceException(BusinessRuleViolation):
    """Raised when attempting to create a resource that already exists."""


class MergeException(BusinessRuleViolation):
    """Raised when a merge operation fails due to invalid inputs."""


# ── Configuration ─────────────────────────────────────────────────────


class ConfigurationException(DomainException):
    """Raised when system or component configuration is invalid."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="CONFIGURATION_ERROR")


class AgentConfigurationException(ConfigurationException):
    """Raised when agent configuration is invalid or missing."""


class WorkflowConfigurationException(ConfigurationException):
    """Raised when workflow graph configuration is invalid."""


# ── Tools ─────────────────────────────────────────────────────────────


class ToolException(DomainException):
    """Base exception for tool-related errors."""

    def __init__(self, message: str, error_code: str = "TOOL_ERROR") -> None:
        super().__init__(message, error_code=error_code)


class ToolNotFoundException(ToolException):
    """Raised when a requested tool cannot be found."""

    def __init__(self, tool_name: str, correction: str | None = None) -> None:
        self.tool_name = tool_name
        self.correction = correction
        msg = correction or f"Tool '{tool_name}' not found"
        super().__init__(msg, error_code="TOOL_NOT_FOUND")


class ToolExecutionException(ToolException):
    """Raised when tool execution fails."""


class ToolConfigurationException(ToolException):
    """Raised when tool configuration is missing or invalid."""


# ── Authentication / Authorization ────────────────────────────────────


class AuthenticationException(DomainException):
    """Raised when authentication fails."""

    def __init__(self, message: str = "Authentication failed") -> None:
        super().__init__(message, error_code="AUTHENTICATION_FAILED")


class AuthorizationException(DomainException):
    """Raised when user lacks required permissions."""

    def __init__(self, message: str = "Insufficient permissions") -> None:
        super().__init__(message, error_code="AUTHORIZATION_FAILED")


# ── Integration ───────────────────────────────────────────────────────


class IntegrationException(DomainException):
    """Raised when external integration fails."""

    def __init__(self, message: str, service: str = "unknown") -> None:
        self.service = service
        super().__init__(message, error_code="INTEGRATION_ERROR")


class LLMException(IntegrationException):
    """Raised when LLM integration fails (API errors, parsing failures, etc.)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, service="llm")


class LLMKeysExhaustedError(LLMException):
    """Raised when all LLM API keys in a pool are exhausted or invalid.

    Defined in the domain so that domain services can catch this error without
    importing from the infrastructure layer (key_pool.APIKeysExhaustedError).
    The infrastructure APIKeysExhaustedError inherits from this class.
    """

    def __init__(self, provider: str, key_count: int) -> None:
        self.provider = provider
        self.key_count = key_count
        super().__init__(f"All {key_count} {provider} API keys exhausted")


class ImageGenerationException(IntegrationException):
    """Raised when image generation service fails or is not configured."""

    def __init__(self, message: str) -> None:
        super().__init__(message, service="image_generation")


class KnowledgeBaseException(IntegrationException):
    """Raised when knowledge base (RAG-Anything) operations fail."""

    def __init__(self, message: str) -> None:
        super().__init__(message, service="knowledge_base")


# ── Workflow / Flow ───────────────────────────────────────────────────


class FlowException(DomainException):
    """Raised when a flow/workflow encounters an error."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="FLOW_ERROR")


class ResearchFlowException(FlowException):
    """Raised when a research flow fails."""


# ── Security ──────────────────────────────────────────────────────────


class SecurityViolation(DomainException):
    """Raised when a security constraint is violated (path traversal, injection, etc.)."""

    def __init__(self, message: str) -> None:
        super().__init__(message, error_code="SECURITY_VIOLATION")
