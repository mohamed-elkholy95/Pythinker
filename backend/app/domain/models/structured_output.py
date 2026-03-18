from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Generic, TypeVar

from pydantic import BaseModel

if TYPE_CHECKING:
    from app.domain.services.validation.schema_profile import SchemaComplexityProfile

T = TypeVar("T", bound=BaseModel)


class OutputTier(StrEnum):
    A = "A"
    B = "B"
    C = "C"


class StructuredOutputStrategy(StrEnum):
    ANTHROPIC_OUTPUT_CONFIG = "anthropic_output_config"
    OPENAI_STRICT_JSON_SCHEMA = "openai_strict_json_schema"
    OPENAI_STRICT_FUNCTION = "openai_strict_function"
    INSTRUCTOR_TOOLS_STRICT = "instructor_tools_strict"
    INSTRUCTOR_JSON_SCHEMA = "instructor_json_schema"
    INSTRUCTOR_MD_JSON = "instructor_md_json"
    LENIENT_JSON_OBJECT = "lenient_json_object"
    PROMPT_BASED_JSON = "prompt_based_json"
    UNSUPPORTED = "unsupported"


class StopReason(StrEnum):
    SUCCESS = "success"
    REFUSAL = "refusal"
    TRUNCATED = "truncated"
    CONTENT_FILTER = "content_filter"
    SCHEMA_INVALID = "schema_invalid"
    TRANSPORT_ERROR = "transport_error"
    TIMEOUT = "timeout"
    UNSUPPORTED = "unsupported"


class ErrorCategory(StrEnum):
    TRANSPORT = "transport"
    SCHEMA = "schema"
    SAFETY = "safety"
    TIMEOUT = "timeout"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class StructuredOutputRequest(Generic[T]):
    request_id: str
    schema_model: type[T]
    tier: OutputTier
    messages: list[dict[str, Any]]
    max_schema_retries: int = 3
    max_transport_retries: int = 3
    complexity_profile: SchemaComplexityProfile | None = None


@dataclass(frozen=True)
class StructuredOutputResult(Generic[T]):
    parsed: T | None
    strategy_used: StructuredOutputStrategy
    stop_reason: StopReason
    refusal_message: str | None
    error_type: ErrorCategory | None
    attempts: int
    latency_ms: float
    request_id: str
    tier: OutputTier


class StructuredOutputError(Exception):
    stop_reason: StopReason
    error_category: ErrorCategory

    def __init__(self, message: str, *, stop_reason: StopReason, error_category: ErrorCategory):
        super().__init__(message)
        self.stop_reason = stop_reason
        self.error_category = error_category


class StructuredRefusalError(StructuredOutputError):
    def __init__(self, message: str):
        super().__init__(message, stop_reason=StopReason.REFUSAL, error_category=ErrorCategory.SAFETY)


class StructuredTruncationError(StructuredOutputError):
    def __init__(self, message: str):
        super().__init__(message, stop_reason=StopReason.TRUNCATED, error_category=ErrorCategory.SCHEMA)


class StructuredContentFilterError(StructuredOutputError):
    def __init__(self, message: str):
        super().__init__(message, stop_reason=StopReason.CONTENT_FILTER, error_category=ErrorCategory.SAFETY)


class StructuredSchemaValidationError(StructuredOutputError):
    def __init__(self, message: str):
        super().__init__(message, stop_reason=StopReason.SCHEMA_INVALID, error_category=ErrorCategory.SCHEMA)


class StructuredOutputExhaustedError(StructuredOutputError):
    def __init__(self, message: str):
        super().__init__(message, stop_reason=StopReason.TRANSPORT_ERROR, error_category=ErrorCategory.TRANSPORT)


class StructuredOutputUnsupportedError(StructuredOutputError):
    def __init__(self, message: str):
        super().__init__(message, stop_reason=StopReason.UNSUPPORTED, error_category=ErrorCategory.UNSUPPORTED)
