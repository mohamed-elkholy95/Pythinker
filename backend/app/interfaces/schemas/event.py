from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.domain.models.event import (
    AgentEvent,
    MCPHealthEvent,
    MessageEvent,
    PlanEvent,
    ProgressEvent,
    ReportEvent,
    SearchToolContent,
    SkillActivationEvent,
    SkillDeliveryEvent,
    StepEvent,
    SuggestionEvent,
    ThoughtEvent,
    ToolContent,
    ToolEvent,
    ToolProgressEvent,
    ToolStatus,
    ToolStreamEvent,
    WideResearchEvent,
    WorkspaceEvent,
)
from app.domain.models.plan import ExecutionStatus
from app.domain.models.search import SearchResultItem
from app.domain.models.source_citation import SourceCitation
from app.interfaces.schemas.file import FileInfoResponse


class BaseEventData(BaseModel):
    event_id: str | None
    timestamp: int = Field(default_factory=lambda: int(datetime.now(UTC).timestamp()))

    @classmethod
    def base_event_data(cls, event: AgentEvent) -> dict:
        return {"event_id": event.id, "timestamp": int(event.timestamp.timestamp())}

    @classmethod
    def from_event(cls, event: AgentEvent) -> Self:
        return cls(**cls.base_event_data(event), **event.model_dump(exclude={"type", "id", "timestamp"}))


class CommonEventData(BaseEventData):
    model_config = ConfigDict(extra="allow")


class BaseSSEEvent(BaseModel):
    event: str
    data: BaseEventData

    @classmethod
    def from_event(cls, event: AgentEvent) -> Self:
        data_class: type[BaseEventData] = cls.__annotations__.get("data", BaseEventData)
        return cls(event=event.type, data=data_class.from_event(event))


class MessageEventData(BaseEventData):
    role: Literal["user", "assistant"]
    content: str
    attachments: list[FileInfoResponse] | None = None
    # Follow-up context from suggestion clicks
    follow_up_selected_suggestion: str | None = None
    follow_up_anchor_event_id: str | None = None
    follow_up_source: str | None = None


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
            attachments = valid_attachments or None

        return cls(
            data=MessageEventData(
                **BaseEventData.base_event_data(event),
                role=event.role,
                content=event.message,
                attachments=attachments,
                follow_up_selected_suggestion=event.follow_up_selected_suggestion,
                follow_up_anchor_event_id=event.follow_up_anchor_event_id,
                follow_up_source=event.follow_up_source,
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

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> ToolStatus:
        if isinstance(v, str):
            return ToolStatus(v)
        return v


_SEARCH_FUNCTIONS = frozenset(
    {
        "info_search_web",
        "web_search",
        "search",
        "wide_research",
        "deal_search",
        "deal_compare_prices",
        "deal_find_coupons",
    }
)


def _derive_search_content(event: ToolEvent) -> SearchToolContent | None:
    """Derive SearchToolContent from function_result when tool_content is missing.

    Ensures frontend receives search results even when tool_content was not populated
    (e.g. some execution paths only set function_result).
    """
    if event.tool_content is not None:
        return event.tool_content
    if event.status != ToolStatus.CALLED or event.function_result is None:
        return None
    func = (event.function_name or "").lower()
    if func not in _SEARCH_FUNCTIONS:
        return None
    fr = event.function_result

    # ToolResult object (agent path)
    success = getattr(fr, "success", None)
    data = getattr(fr, "data", None)
    # Plain dict (fast_path style, e.g. {"success": True, "results": [...]})
    if success is None and isinstance(fr, dict):
        success = fr.get("success", False)
        data = fr.get("data") or fr  # data may be nested or the dict itself

    if not success:
        return None

    results_list: list[SearchResultItem] = []
    # data from ToolResult (SearchResults model or dict)
    if data is not None:
        if hasattr(data, "results") and data.results:
            results_list = [
                SearchResultItem(
                    title=getattr(r, "title", None) or "No title",
                    link=getattr(r, "link", None) or "",
                    snippet=getattr(r, "snippet", None) or "",
                )
                for r in data.results[:10]
            ]
        elif isinstance(data, dict):
            if data.get("results"):
                for r in data["results"][:10]:
                    t = r.get("title", "No title") if isinstance(r, dict) else (getattr(r, "title", None) or "No title")
                    lnk = r.get("link", "") if isinstance(r, dict) else (getattr(r, "link", None) or "")
                    snip = r.get("snippet", "") if isinstance(r, dict) else (getattr(r, "snippet", None) or "")
                    results_list.append(SearchResultItem(title=t, link=lnk, snippet=snip))
            elif data.get("sources"):
                for s in data["sources"][:10]:
                    results_list.append(
                        SearchResultItem(
                            title=s.get("title", "No title"),
                            link=s.get("url", s.get("link", "")),
                            snippet=s.get("snippet", ""),
                        )
                    )

    # Deal-specific extraction: deals list → SearchResultItems
    if not results_list and isinstance(data, dict):
        deals = data.get("deals", [])
        for d in deals[:10]:
            results_list.append(
                SearchResultItem(
                    title=f"{d.get('store', 'Unknown')} — ${d.get('price', 0):.2f}",
                    link=d.get("url", d.get("product_url", "")),
                    snippet=d.get("title", d.get("product_name", "")),
                )
            )
        # Coupon extraction fallback
        if not results_list:
            coupons = data.get("coupons", [])
            for c in coupons[:10]:
                results_list.append(
                    SearchResultItem(
                        title=c.get("code", "No code"),
                        link=c.get("source", ""),
                        snippet=c.get("description", ""),
                    )
                )

    if not results_list:
        return None
    return SearchToolContent(results=results_list)


class ToolSSEEvent(BaseSSEEvent):
    event: Literal["tool"] = "tool"
    data: ToolEventData

    @classmethod
    async def from_event_async(cls, event: ToolEvent) -> Self:
        content: ToolContent | None = event.tool_content
        if content is None:
            content = _derive_search_content(event)
        return cls(
            data=ToolEventData(
                **BaseEventData.base_event_data(event),
                tool_call_id=event.tool_call_id,
                name=event.tool_name,
                status=event.status,
                function=event.function_name,
                args=event.function_args,
                content=content,
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


class ToolStreamEventData(BaseEventData):
    """SSE data for streaming partial tool content during LLM generation."""

    tool_call_id: str
    tool_name: str
    function_name: str
    partial_content: str
    content_type: str = "text"
    is_final: bool = False


class ToolStreamSSEEvent(BaseSSEEvent):
    event: Literal["tool_stream"] = "tool_stream"
    data: ToolStreamEventData

    @classmethod
    def from_event(cls, event: ToolStreamEvent) -> Self:
        return cls(
            data=ToolStreamEventData(
                **BaseEventData.base_event_data(event),
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                function_name=event.function_name,
                partial_content=event.partial_content,
                content_type=event.content_type,
                is_final=event.is_final,
            )
        )


class ToolProgressEventData(BaseEventData):
    """SSE data for tool execution progress updates."""

    tool_call_id: str
    tool_name: str
    function_name: str
    progress_percent: int  # 0-100
    current_step: str
    steps_completed: int = 0
    steps_total: int | None = None
    elapsed_ms: float = 0
    estimated_remaining_ms: float | None = None


class ToolProgressSSEEvent(BaseSSEEvent):
    event: Literal["tool_progress"] = "tool_progress"
    data: ToolProgressEventData

    @classmethod
    def from_event(cls, event: ToolProgressEvent) -> Self:
        return cls(
            data=ToolProgressEventData(
                **BaseEventData.base_event_data(event),
                tool_call_id=event.tool_call_id,
                tool_name=event.tool_name,
                function_name=event.function_name,
                progress_percent=event.progress_percent,
                current_step=event.current_step,
                steps_completed=event.steps_completed,
                steps_total=event.steps_total,
                elapsed_ms=event.elapsed_ms,
                estimated_remaining_ms=event.estimated_remaining_ms,
            )
        )


class DoneSSEEvent(BaseSSEEvent):
    event: Literal["done"] = "done"


class WaitEventData(BaseEventData):
    wait_reason: str | None = None
    suggest_user_takeover: str | None = None


class WaitSSEEvent(BaseSSEEvent):
    event: Literal["wait"] = "wait"
    data: WaitEventData


class ErrorEventData(BaseEventData):
    error: str
    error_type: str | None = None
    recoverable: bool = True
    retry_hint: str | None = None
    error_code: str | None = None
    error_category: str | None = None
    severity: str = "error"
    retry_after_ms: int | None = None
    can_resume: bool = False
    checkpoint_event_id: str | None = None
    details: dict[str, Any] | None = None


class ErrorSSEEvent(BaseSSEEvent):
    event: Literal["error"] = "error"
    data: ErrorEventData


class StepEventData(BaseEventData):
    status: ExecutionStatus
    id: str
    description: str
    phase_id: str | None = None  # Parent phase ID; when set, step is in plan-act flow (hide fast-search UI)
    step_type: str | None = None  # StepType value for routing

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> ExecutionStatus:
        if isinstance(v, str):
            return ExecutionStatus(v)
        return v


class StepSSEEvent(BaseSSEEvent):
    event: Literal["step"] = "step"
    data: StepEventData

    @classmethod
    def from_event(cls, event: StepEvent) -> Self:
        phase_id = event.phase_id or event.step.phase_id
        step_type_val = event.step_type
        if step_type_val is None and event.step.step_type is not None:
            step_type_val = event.step.step_type.value
        return cls(
            data=StepEventData(
                **BaseEventData.base_event_data(event),
                status=event.step.status,
                id=event.step.id,
                description=event.step.description,
                phase_id=phase_id,
                step_type=step_type_val,
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
                steps=[
                    StepEventData(
                        **BaseEventData.base_event_data(event),
                        status=step.status,
                        id=step.id,
                        description=step.description,
                    )
                    for step in event.plan.steps
                ],
            )
        )


class ReportEventData(BaseEventData):
    id: str
    title: str
    content: str
    attachments: list[FileInfoResponse] | None = None
    sources: list[SourceCitation] | None = None


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
            attachments = valid_attachments or None

        return cls(
            data=ReportEventData(
                **BaseEventData.base_event_data(event),
                id=event.id,
                title=event.title,
                content=event.content,
                attachments=attachments,
                sources=event.sources,
            )
        )


class SuggestionEventData(BaseEventData):
    suggestions: list[str]
    source: str | None = None
    anchor_event_id: str | None = None
    anchor_excerpt: str | None = None


class SuggestionSSEEvent(BaseSSEEvent):
    event: Literal["suggestion"] = "suggestion"
    data: SuggestionEventData

    @classmethod
    def from_event(cls, event: "SuggestionEvent") -> Self:  # type: ignore[name-defined]
        return cls(
            data=SuggestionEventData(
                **BaseEventData.base_event_data(event),
                suggestions=event.suggestions,
                source=event.source,
                anchor_event_id=event.anchor_event_id,
                anchor_excerpt=event.anchor_excerpt,
            )
        )


class ModeChangeEventData(BaseEventData):
    mode: str
    reason: str | None = None


class ModeChangeSSEEvent(BaseSSEEvent):
    event: Literal["mode_change"] = "mode_change"
    data: ModeChangeEventData


class StreamEventData(BaseEventData):
    content: str
    is_final: bool = False
    phase: str | None = None


class StreamSSEEvent(BaseSSEEvent):
    event: Literal["stream"] = "stream"
    data: StreamEventData


class CommonSSEEvent(BaseSSEEvent):
    event: str
    data: CommonEventData


class SkillPackageFileEventData(BaseModel):
    """File data within a skill delivery event for SSE"""

    path: str
    content: str
    size: int


class SkillDeliveryEventData(BaseEventData):
    """Skill delivery event data for SSE"""

    package_id: str
    name: str
    description: str
    version: str = "1.0.0"
    icon: str = "puzzle"
    category: str = "custom"
    author: str | None = None
    file_tree: dict[str, Any] = Field(default_factory=dict)
    files: list[SkillPackageFileEventData] = Field(default_factory=list)
    file_id: str | None = None
    skill_id: str | None = None


class SkillDeliverySSEEvent(BaseSSEEvent):
    event: Literal["skill_delivery"] = "skill_delivery"
    data: SkillDeliveryEventData

    @classmethod
    def from_event(cls, event: SkillDeliveryEvent) -> Self:
        return cls(
            data=SkillDeliveryEventData(
                **BaseEventData.base_event_data(event),
                package_id=event.package_id,
                name=event.name,
                description=event.description,
                version=event.version,
                icon=event.icon,
                category=event.category,
                author=event.author,
                file_tree=event.file_tree,
                files=[
                    SkillPackageFileEventData(
                        path=f.path,
                        content=f.content,
                        size=f.size,
                    )
                    for f in event.files
                ],
                file_id=event.file_id,
                skill_id=event.skill_id,
            )
        )


class ProgressEventData(BaseEventData):
    """Planning progress event data"""

    phase: str  # PlanningPhase value
    message: str
    estimated_steps: int | None = None
    progress_percent: int | None = None
    estimated_duration_seconds: int | None = None
    complexity_category: str | None = None
    wait_elapsed_seconds: int | None = None
    wait_stage: str | None = None


class ProgressSSEEvent(BaseSSEEvent):
    event: Literal["progress"] = "progress"
    data: ProgressEventData

    @classmethod
    def from_event(cls, event: ProgressEvent) -> Self:
        return cls(
            data=ProgressEventData(
                **BaseEventData.base_event_data(event),
                phase=event.phase.value,
                message=event.message,
                estimated_steps=event.estimated_steps,
                progress_percent=event.progress_percent,
                estimated_duration_seconds=event.estimated_duration_seconds,
                complexity_category=event.complexity_category,
                wait_elapsed_seconds=event.wait_elapsed_seconds,
                wait_stage=event.wait_stage,
            )
        )


class WideResearchEventData(BaseEventData):
    """Wide research progress event data"""

    research_id: str
    topic: str
    status: str  # WideResearchStatus value
    total_queries: int
    completed_queries: int = 0
    sources_found: int = 0
    search_types: list[str] = Field(default_factory=list)
    current_query: str | None = None
    errors: list[str] = Field(default_factory=list)


class WideResearchSSEEvent(BaseSSEEvent):
    event: Literal["wide_research"] = "wide_research"
    data: WideResearchEventData

    @classmethod
    def from_event(cls, event: WideResearchEvent) -> Self:
        return cls(
            data=WideResearchEventData(
                **BaseEventData.base_event_data(event),
                research_id=event.research_id,
                topic=event.topic,
                status=event.status.value,
                total_queries=event.total_queries,
                completed_queries=event.completed_queries,
                sources_found=event.sources_found,
                search_types=event.search_types,
                current_query=event.current_query,
                errors=event.errors,
            )
        )


class SkillActivationEventData(BaseEventData):
    """Skill activation event data"""

    skill_ids: list[str] = Field(default_factory=list)
    skill_names: list[str] = Field(default_factory=list)
    tool_restrictions: list[str] | None = None
    prompt_chars: int = 0
    activation_sources: dict[str, list[str]] = Field(default_factory=dict)
    command_skill_id: str | None = None
    auto_trigger_enabled: bool = False


class SkillActivationSSEEvent(BaseSSEEvent):
    event: Literal["skill_activation"] = "skill_activation"
    data: SkillActivationEventData

    @classmethod
    def from_event(cls, event: SkillActivationEvent) -> Self:
        return cls(
            data=SkillActivationEventData(
                **BaseEventData.base_event_data(event),
                skill_ids=event.skill_ids,
                skill_names=event.skill_names,
                tool_restrictions=event.tool_restrictions,
                prompt_chars=event.prompt_chars,
                activation_sources=event.activation_sources,
                command_skill_id=event.command_skill_id,
                auto_trigger_enabled=event.auto_trigger_enabled,
            )
        )


class ThoughtEventData(BaseEventData):
    """Thought/chain-of-thought event data"""

    status: str  # ThoughtStatus value
    thought_type: str | None = None
    content: str | None = None
    confidence: float | None = None
    step_name: str | None = None
    chain_id: str | None = None
    is_final: bool = False


class ThoughtSSEEvent(BaseSSEEvent):
    event: Literal["thought"] = "thought"
    data: ThoughtEventData

    @classmethod
    def from_event(cls, event: ThoughtEvent) -> Self:
        return cls(
            data=ThoughtEventData(
                **BaseEventData.base_event_data(event),
                status=event.status.value,
                thought_type=event.thought_type,
                content=event.content,
                confidence=event.confidence,
                step_name=event.step_name,
                chain_id=event.chain_id,
                is_final=event.is_final,
            )
        )


class WorkspaceEventData(BaseEventData):
    """Workspace lifecycle event data for SSE."""

    action: str  # "initialized", "organized", "validated", "deliverables_ready"
    workspace_type: str | None = None  # "research", "code_project", "data_analysis"
    structure: dict[str, str] | None = None  # folder_name -> purpose
    files_organized: int = 0
    deliverables_count: int = 0
    workspace_path: str | None = None


class WorkspaceSSEEvent(BaseSSEEvent):
    event: Literal["workspace"] = "workspace"
    data: WorkspaceEventData

    @classmethod
    def from_event(cls, event: WorkspaceEvent) -> Self:
        return cls(
            data=WorkspaceEventData(
                **BaseEventData.base_event_data(event),
                action=event.action,
                workspace_type=event.workspace_type,
                structure=event.structure,
                files_organized=event.files_organized,
                deliverables_count=event.deliverables_count,
                workspace_path=event.workspace_path,
            )
        )


class MCPHealthEventData(BaseEventData):
    """SSE data for MCP server health status."""

    server_name: str
    healthy: bool
    degraded: bool = False
    error: str | None = None
    tools_available: int = 0
    avg_response_time_ms: float = 0.0
    success_rate: float = 1.0
    last_check: str | None = None  # ISO format timestamp


class MCPHealthSSEEvent(BaseSSEEvent):
    event: Literal["mcp_health"] = "mcp_health"
    data: MCPHealthEventData

    @classmethod
    def from_event(cls, event: MCPHealthEvent) -> Self:
        return cls(
            data=MCPHealthEventData(
                **BaseEventData.base_event_data(event),
                server_name=event.server_name,
                healthy=event.healthy,
                error=event.error,
                tools_available=event.tools_available,
            )
        )


AgentSSEEvent = (
    CommonSSEEvent
    | PlanSSEEvent
    | MessageSSEEvent
    | TitleSSEEvent
    | ToolSSEEvent
    | ToolStreamSSEEvent
    | ToolProgressSSEEvent
    | StepSSEEvent
    | DoneSSEEvent
    | ErrorSSEEvent
    | WaitSSEEvent
    | ReportSSEEvent
    | SkillDeliverySSEEvent
    | SuggestionSSEEvent
    | ModeChangeSSEEvent
    | StreamSSEEvent
    | ProgressSSEEvent
    | WideResearchSSEEvent
    | SkillActivationSSEEvent
    | ThoughtSSEEvent
    | WorkspaceSSEEvent
    | MCPHealthSSEEvent
)


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
            if hasattr(sse_event_class, "__annotations__") and "event" in sse_event_class.__annotations__:
                event_field = sse_event_class.__annotations__["event"]
                if hasattr(event_field, "__args__") and len(event_field.__args__) > 0:
                    event_type = event_field.__args__[0]  # Get Literal value

                    # Get data class from sse_event_class
                    data_class = None
                    if hasattr(sse_event_class, "__annotations__") and "data" in sse_event_class.__annotations__:
                        data_class = sse_event_class.__annotations__["data"]

                    mapping[event_type] = EventMapping(
                        sse_event_class=sse_event_class, data_class=data_class, event_type=event_type
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
            if hasattr(sse_event_class, "from_event_async"):
                sse_event = await sse_event_class.from_event_async(event)
            else:
                sse_event = sse_event_class.from_event(event)
            return sse_event
        # If no matching type found, return wrapped event with event type
        return CommonSSEEvent(event=event.type, data=CommonEventData.from_event(event))

    @staticmethod
    async def events_to_sse_events(events: list[AgentEvent]) -> list[AgentSSEEvent]:
        """Create SSE event list from event list"""
        return list(
            filter(lambda x: x is not None, [await EventMapper.event_to_sse_event(event) for event in events if event])
        )
