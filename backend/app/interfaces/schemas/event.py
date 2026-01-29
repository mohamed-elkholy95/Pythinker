from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Self, Union

from pydantic import BaseModel, Field

from app.domain.models.event import (
    AgentEvent,
    DeepResearchEvent,
    MessageEvent,
    PlanEvent,
    ReportEvent,
    StepEvent,
    ToolContent,
    ToolEvent,
    ToolStatus,
)
from app.domain.models.plan import ExecutionStatus
from app.interfaces.schemas.file import FileInfoResponse


class BaseEventData(BaseModel):
    event_id: str | None
    timestamp: datetime = Field(default_factory=lambda: datetime.now())

    class Config:
        json_encoders = {
            datetime: lambda v: int(v.timestamp())
        }

    @classmethod
    def base_event_data(cls, event: AgentEvent) -> dict:
        return {
            "event_id": event.id,
            "timestamp": int(event.timestamp.timestamp())
        }

    @classmethod
    def from_event(cls, event: AgentEvent) -> Self:
        return cls(
            **cls.base_event_data(event),
            **event.model_dump(exclude={"type", "id", "timestamp"})
        )

class CommonEventData(BaseEventData):
    class Config:
        json_encoders = {
            datetime: lambda v: int(v.timestamp())
        }
        extra = "allow"

class BaseSSEEvent(BaseModel):
    event: str
    data: BaseEventData

    @classmethod
    def from_event(cls, event: AgentEvent) -> Self:
        data_class: type[BaseEventData] = cls.__annotations__.get('data', BaseEventData)
        return cls(
            event=event.type,
            data=data_class.from_event(event)
        )

class MessageEventData(BaseEventData):
    role: Literal["user", "assistant"]
    content: str
    attachments: list[FileInfoResponse] | None = None

class MessageSSEEvent(BaseSSEEvent):
    event: Literal["message"] = "message"
    data: MessageEventData

    @classmethod
    async def from_event_async(cls, event: MessageEvent) -> Self:
        # Convert attachments, filtering out any that fail validation (return None)
        attachments = None
        if event.attachments:
            converted = [await FileInfoResponse.from_file_info(att) for att in event.attachments]
            # Filter out None values (invalid attachments)
            valid_attachments = [att for att in converted if att is not None]
            attachments = valid_attachments if valid_attachments else None

        return cls(
            data=MessageEventData(
                **BaseEventData.base_event_data(event),
                role=event.role,
                content=event.message,
                attachments=attachments
            )
        )

class ToolEventData(BaseEventData):
    tool_call_id: str
    name: str
    status: ToolStatus
    function: str
    args: dict[str, Any]
    content: ToolContent | None = None
    # Action/observation metadata
    action_type: str | None = None
    observation_type: str | None = None
    command: str | None = None
    cwd: str | None = None
    stdout: str | None = None
    stderr: str | None = None
    exit_code: int | None = None
    file_path: str | None = None
    diff: str | None = None
    runtime_status: str | None = None
    # Security/confirmation metadata
    security_risk: str | None = None
    security_reason: str | None = None
    security_suggestions: list[str] | None = None
    confirmation_state: str | None = None

class ToolSSEEvent(BaseSSEEvent):
    event: Literal["tool"] = "tool"
    data: ToolEventData

    @classmethod
    async def from_event_async(cls, event: ToolEvent) -> Self:
        return cls(
            data=ToolEventData(
                **BaseEventData.base_event_data(event),
                tool_call_id=event.tool_call_id,
                name=event.tool_name,
                status=event.status,
                function=event.function_name,
                args=event.function_args,
                content=event.tool_content,
                action_type=event.action_type,
                observation_type=event.observation_type,
                command=event.command,
                cwd=event.cwd,
                stdout=event.stdout,
                stderr=event.stderr,
                exit_code=event.exit_code,
                file_path=event.file_path,
                diff=event.diff,
                runtime_status=event.runtime_status,
                security_risk=event.security_risk,
                security_reason=event.security_reason,
                security_suggestions=event.security_suggestions,
                confirmation_state=event.confirmation_state,
            )
        )

class DoneSSEEvent(BaseSSEEvent):
    event: Literal["done"] = "done"

class WaitSSEEvent(BaseSSEEvent):
    event: Literal["wait"] = "wait"

class ErrorEventData(BaseEventData):
    error: str

class ErrorSSEEvent(BaseSSEEvent):
    event: Literal["error"] = "error"
    data: ErrorEventData

class StepEventData(BaseEventData):
    status: ExecutionStatus
    id: str
    description: str

class StepSSEEvent(BaseSSEEvent):
    event: Literal["step"] = "step"
    data: StepEventData

    @classmethod
    def from_event(cls, event: StepEvent) -> Self:
        return cls(
            data=StepEventData(
                **BaseEventData.base_event_data(event),
                status=event.step.status,
                id=event.step.id,
                description=event.step.description
            )
        )

class TitleEventData(BaseEventData):
    title: str

class TitleSSEEvent(BaseSSEEvent):
    event: Literal["title"] = "title"
    data: TitleEventData

class PlanEventData(BaseEventData):
    steps: list[StepEventData]

class PlanSSEEvent(BaseSSEEvent):
    event: Literal["plan"] = "plan"
    data: PlanEventData

    @classmethod
    def from_event(cls, event: PlanEvent) -> Self:
        return cls(
            data=PlanEventData(
                **BaseEventData.base_event_data(event),
                steps=[StepEventData(
                    **BaseEventData.base_event_data(event),
                    status=step.status,
                    id=step.id,
                    description=step.description
                ) for step in event.plan.steps]
            )
        )

class ReportEventData(BaseEventData):
    id: str
    title: str
    content: str
    attachments: list[FileInfoResponse] | None = None

class ReportSSEEvent(BaseSSEEvent):
    event: Literal["report"] = "report"
    data: ReportEventData

    @classmethod
    async def from_event_async(cls, event: ReportEvent) -> Self:
        # Convert attachments, filtering out any that fail validation (return None)
        attachments = None
        if event.attachments:
            converted = [await FileInfoResponse.from_file_info(att) for att in event.attachments]
            # Filter out None values (invalid attachments)
            valid_attachments = [att for att in converted if att is not None]
            attachments = valid_attachments if valid_attachments else None

        return cls(
            data=ReportEventData(
                **BaseEventData.base_event_data(event),
                id=event.id,
                title=event.title,
                content=event.content,
                attachments=attachments
            )
        )

class SuggestionEventData(BaseEventData):
    suggestions: list[str]

class SuggestionSSEEvent(BaseSSEEvent):
    event: Literal["suggestion"] = "suggestion"
    data: SuggestionEventData

class ModeChangeEventData(BaseEventData):
    mode: str
    reason: str | None = None

class ModeChangeSSEEvent(BaseSSEEvent):
    event: Literal["mode_change"] = "mode_change"
    data: ModeChangeEventData

class StreamEventData(BaseEventData):
    content: str
    is_final: bool = False

class StreamSSEEvent(BaseSSEEvent):
    event: Literal["stream"] = "stream"
    data: StreamEventData

class CommonSSEEvent(BaseSSEEvent):
    event: str
    data: CommonEventData


class DeepResearchQueryEventData(BaseModel):
    """Individual query data for SSE event"""
    id: str
    query: str
    status: str  # DeepResearchQueryStatus value
    result: list[dict] | None = None
    started_at: int | None = None  # Unix timestamp
    completed_at: int | None = None  # Unix timestamp


class DeepResearchEventData(BaseEventData):
    """Deep research progress event data"""
    research_id: str
    status: str  # DeepResearchStatus value
    total_queries: int
    completed_queries: int
    queries: list[DeepResearchQueryEventData]
    auto_run: bool = False


class DeepResearchSSEEvent(BaseSSEEvent):
    event: Literal["deep_research"] = "deep_research"
    data: DeepResearchEventData

    @classmethod
    def from_event(cls, event: DeepResearchEvent) -> Self:
        return cls(
            data=DeepResearchEventData(
                **BaseEventData.base_event_data(event),
                research_id=event.research_id,
                status=event.status.value,
                total_queries=event.total_queries,
                completed_queries=event.completed_queries,
                queries=[
                    DeepResearchQueryEventData(
                        id=q.id,
                        query=q.query,
                        status=q.status.value,
                        result=q.result,
                        started_at=int(q.started_at.timestamp()) if q.started_at else None,
                        completed_at=int(q.completed_at.timestamp()) if q.completed_at else None,
                    )
                    for q in event.queries
                ],
                auto_run=event.auto_run,
            )
        )


AgentSSEEvent = Union[
    CommonSSEEvent,
    PlanSSEEvent,
    MessageSSEEvent,
    TitleSSEEvent,
    ToolSSEEvent,
    StepSSEEvent,
    DoneSSEEvent,
    ErrorSSEEvent,
    WaitSSEEvent,
    ReportSSEEvent,
    SuggestionSSEEvent,
    ModeChangeSSEEvent,
    StreamSSEEvent,
    DeepResearchSSEEvent,
]

@dataclass
class EventMapping:
    """Data class to store event type mapping information"""
    sse_event_class: type[BaseEventData]
    data_class: type[BaseEventData]
    event_type: str

class EventMapper:
    """Map AgentEvent to SSEEvent"""

    _cached_mapping: dict[str, EventMapping] | None = None

    @staticmethod
    def _get_event_type_mapping() -> dict[str, EventMapping]:
        """Dynamically get mapping from event type to SSE event class with caching"""
        if EventMapper._cached_mapping is not None:
            return EventMapper._cached_mapping

        from typing import get_args

        # Get all subclasses of AgentSSEEvent Union
        sse_event_classes = get_args(AgentSSEEvent)
        mapping = {}

        for sse_event_class in sse_event_classes:
            # Skip base class
            if sse_event_class == BaseSSEEvent:
                continue

            # Get event type
            if hasattr(sse_event_class, '__annotations__') and 'event' in sse_event_class.__annotations__:
                event_field = sse_event_class.__annotations__['event']
                if hasattr(event_field, '__args__') and len(event_field.__args__) > 0:
                    event_type = event_field.__args__[0]  # Get Literal value

                    # Get data class from sse_event_class
                    data_class = None
                    if hasattr(sse_event_class, '__annotations__') and 'data' in sse_event_class.__annotations__:
                        data_class = sse_event_class.__annotations__['data']

                    mapping[event_type] = EventMapping(
                        sse_event_class=sse_event_class,
                        data_class=data_class,
                        event_type=event_type
                    )

        # Cache the mapping
        EventMapper._cached_mapping = mapping
        return mapping

    @staticmethod
    async def event_to_sse_event(event: AgentEvent) -> AgentSSEEvent:
        # Get mapping dynamically
        event_type_mapping = EventMapper._get_event_type_mapping()

        # Find matching SSE event class
        event_mapping = event_type_mapping.get(event.type)

        if event_mapping:
            # Prioritize from_event_async class method if exists, otherwise use from_event
            sse_event_class = event_mapping.sse_event_class
            if hasattr(sse_event_class, 'from_event_async'):
                sse_event = await sse_event_class.from_event_async(event)
            else:
                sse_event = sse_event_class.from_event(event)
            return sse_event
        # If no matching type found, return wrapped event with event type
        return CommonSSEEvent(
            event=event.type,
            data=CommonEventData.from_event(event)
        )

    @staticmethod
    async def events_to_sse_events(events: list[AgentEvent]) -> list[AgentSSEEvent]:
        """Create SSE event list from event list"""
        return list(filter(lambda x: x is not None, [
            await EventMapper.event_to_sse_event(event) for event in events if event
        ]))
