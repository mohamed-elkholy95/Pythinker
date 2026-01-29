import asyncio
import logging
import time
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Optional, Union

from pydantic import TypeAdapter

from app.application.services.usage_service import get_usage_service
from app.domain.external.browser import Browser
from app.domain.external.file import FileStorage
from app.domain.external.llm import LLM
from app.domain.external.sandbox import Sandbox
from app.domain.external.search import SearchEngine
from app.domain.external.task import Task, TaskRunner
from app.domain.models.event import (
    AgentEvent,
    BaseEvent,
    BrowserAgentToolContent,
    BrowserToolContent,
    DoneEvent,
    ErrorEvent,
    FileToolContent,
    McpToolContent,
    MessageEvent,
    ModeChangeEvent,
    ReportEvent,
    SearchToolContent,
    ShellToolContent,
    TitleEvent,
    ToolEvent,
    ToolStatus,
    WaitEvent,
)
from app.domain.models.file import FileInfo
from app.domain.models.message import Message
from app.domain.models.search import SearchResults
from app.domain.models.session import AgentMode, SessionStatus
from app.domain.models.tool_result import ToolResult
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.repositories.mcp_repository import MCPRepository
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.agents.usage_context import UsageContextManager
from app.domain.services.flows.discuss import DiscussFlow
from app.domain.services.flows.plan_act import PlanActFlow
from app.domain.services.langgraph import LangGraphPlanActFlow
from app.domain.services.orchestration.coordinator_flow import (
    CoordinatorFlow,
    CoordinatorMode,
    create_coordinator_flow,
)
from app.domain.services.tools.mcp import MCPTool
from app.domain.utils.diff import build_unified_diff
from app.domain.utils.json_parser import JsonParser

if TYPE_CHECKING:
    from app.domain.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

# Type alias for events that contain attachments requiring storage sync
# Both MessageEvent and ReportEvent have an 'attachments' field of type Optional[List[FileInfo]]
EventWithAttachments = Union[MessageEvent, ReportEvent]

class AgentTaskRunner(TaskRunner):
    """Agent task that can be cancelled.

    Supports multiple execution modes:
    - AGENT: Plan-Act flow with optional multi-agent step dispatch
    - DISCUSS: Simple conversational flow
    - COORDINATOR: Full multi-agent swarm execution (when enabled)
    """

    def __init__(
        self,
        session_id: str,
        agent_id: str,
        user_id: str,
        llm: LLM,
        sandbox: Sandbox,
        browser: Browser,
        agent_repository: AgentRepository,
        session_repository: SessionRepository,
        json_parser: JsonParser,
        file_storage: FileStorage,
        mcp_repository: MCPRepository,
        search_engine: SearchEngine | None = None,
        mode: AgentMode = AgentMode.AGENT,
        enable_multi_agent: bool = True,
        enable_coordinator: bool = False,
        memory_service: Optional["MemoryService"] = None,
        use_langgraph_flow: bool = False,
    ):
        self._session_id = session_id
        self._agent_id = agent_id
        self._user_id = user_id
        self._llm = llm
        self._sandbox = sandbox
        self._browser = browser
        self._search_engine = search_engine
        self._repository = agent_repository
        self._session_repository = session_repository
        self._json_parser = json_parser
        self._file_storage = file_storage
        self._mcp_repository = mcp_repository
        self._mcp_tool = MCPTool()
        self._mode = mode

        # Multi-agent configuration
        self._enable_multi_agent = enable_multi_agent
        self._enable_coordinator = enable_coordinator

        # LangGraph flow configuration
        self._use_langgraph_flow = use_langgraph_flow

        # Memory service for long-term context (Phase 6: Qdrant integration)
        self._memory_service = memory_service

        # Tool metadata caches for enhanced UI
        self._tool_start_times: dict[str, float] = {}
        self._file_before_cache: dict[str, str] = {}
        self._pending_tool_calls: dict[str, dict] = {}

        # Initialize flows based on mode
        self._plan_act_flow: PlanActFlow | None = None
        self._langgraph_flow: LangGraphPlanActFlow | None = None
        self._discuss_flow: DiscussFlow | None = None
        self._coordinator_flow: CoordinatorFlow | None = None

        if mode == AgentMode.AGENT:
            if enable_coordinator:
                self._init_coordinator_flow()
            elif use_langgraph_flow:
                self._init_langgraph_flow()
            else:
                self._init_plan_act_flow()
        else:
            self._init_discuss_flow()

    def _init_plan_act_flow(self) -> None:
        """Initialize PlanActFlow for Agent mode"""
        if self._plan_act_flow is None:
            self._plan_act_flow = PlanActFlow(
                self._agent_id,
                self._repository,
                self._session_id,
                self._session_repository,
                self._llm,
                self._sandbox,
                self._browser,
                self._json_parser,
                self._mcp_tool,
                self._search_engine,
                cdp_url=self._sandbox.cdp_url,
                enable_multi_agent=self._enable_multi_agent,
                memory_service=self._memory_service,
                user_id=self._user_id,
            )
            logger.debug(
                f"Initialized PlanActFlow for agent {self._agent_id} "
                f"(multi_agent={self._enable_multi_agent}, memory_service={'enabled' if self._memory_service else 'disabled'})"
            )

    def _init_langgraph_flow(self) -> None:
        """Initialize LangGraphPlanActFlow for Agent mode with LangGraph"""
        if self._langgraph_flow is None:
            self._langgraph_flow = LangGraphPlanActFlow(
                agent_id=self._agent_id,
                agent_repository=self._repository,
                session_id=self._session_id,
                session_repository=self._session_repository,
                llm=self._llm,
                sandbox=self._sandbox,
                browser=self._browser,
                json_parser=self._json_parser,
                mcp_tool=self._mcp_tool,
                search_engine=self._search_engine,
                cdp_url=self._sandbox.cdp_url,
                enable_verification=True,
                enable_reflection=True,
                enable_checkpointing=False,  # Can be enabled when MongoDB db is passed
                memory_service=self._memory_service,
                user_id=self._user_id,
            )
            logger.info(
                f"Initialized LangGraphPlanActFlow for agent {self._agent_id} "
                f"(memory_service={'enabled' if self._memory_service else 'disabled'})"
            )

    def _init_coordinator_flow(self) -> None:
        """Initialize CoordinatorFlow for full multi-agent swarm execution"""
        if self._coordinator_flow is None:
            self._coordinator_flow = create_coordinator_flow(
                agent_id=self._agent_id,
                session_id=self._session_id,
                agent_repository=self._repository,
                session_repository=self._session_repository,
                llm=self._llm,
                sandbox=self._sandbox,
                browser=self._browser,
                json_parser=self._json_parser,
                mcp_tool=self._mcp_tool,
                search_engine=self._search_engine,
                mode=CoordinatorMode.AUTO,
            )
            logger.info(f"Initialized CoordinatorFlow for agent {self._agent_id}")

    def _init_discuss_flow(self) -> None:
        """Initialize DiscussFlow for Discuss mode"""
        if self._discuss_flow is None:
            self._discuss_flow = DiscussFlow(
                self._agent_id,
                self._repository,
                self._session_id,
                self._session_repository,
                self._llm,
                self._json_parser,
                self._search_engine,
            )
            logger.debug(f"Initialized DiscussFlow for agent {self._agent_id}")

    async def _switch_to_agent_mode(self, task_description: str) -> None:
        """Switch from Discuss mode to Agent mode"""
        logger.info(f"Switching to Agent mode for task: {task_description}")
        self._mode = AgentMode.AGENT

        # Initialize appropriate flow based on configuration
        if self._enable_coordinator:
            self._init_coordinator_flow()
        elif self._use_langgraph_flow:
            self._init_langgraph_flow()
        else:
            self._init_plan_act_flow()

        await self._session_repository.update_mode(self._session_id, AgentMode.AGENT)

    @property
    def _flow(self):
        """Get the current flow based on mode and configuration"""
        if self._mode == AgentMode.AGENT:
            # Prefer coordinator flow if enabled
            if self._enable_coordinator and self._coordinator_flow:
                return self._coordinator_flow
            # Use LangGraph flow if enabled
            if self._use_langgraph_flow and self._langgraph_flow:
                return self._langgraph_flow
            return self._plan_act_flow
        return self._discuss_flow

    async def _put_and_add_event(self, task: Task, event: AgentEvent) -> None:
        event_id = await task.output_stream.put(event.model_dump_json())
        event.id = event_id
        await self._session_repository.add_event(self._session_id, event)

    async def _pop_event(self, task: Task) -> AgentEvent:
        event_id, event_str = await task.input_stream.pop()
        if event_str is None:
            logger.warning(f"Agent {self._agent_id} received empty message")
            return None
        event = TypeAdapter(AgentEvent).validate_json(event_str)
        event.id = event_id
        return event

    async def _sync_file_to_storage(self, file_path: str) -> FileInfo | None:
        """
        Download a file from the sandbox and upload it to GridFS storage.

        This method:
        1. Validates the file_path is not empty
        2. Downloads the file content from the sandbox
        3. Validates the content is not empty
        4. Removes any existing file with the same path (to handle updates)
        5. Uploads to GridFS and registers with the session
        6. Returns a fully populated FileInfo with file_id

        Args:
            file_path: The path to the file in the sandbox (e.g., /home/ubuntu/report.md)

        Returns:
            FileInfo with valid file_id if successful, None if sync fails
        """
        # Validate input
        if not file_path or not file_path.strip():
            logger.warning(f"Agent {self._agent_id}: Cannot sync file with empty path")
            return None

        try:
            # Check if file already exists in session
            existing_file = await self._session_repository.get_file_by_path(
                self._session_id, file_path
            )

            # Download file from sandbox
            file_data = await self._sandbox.file_download(file_path)

            # Validate file content
            if file_data is None:
                logger.warning(
                    f"Agent {self._agent_id}: File download returned None for '{file_path}'"
                )
                return None

            if file_data.getbuffer().nbytes == 0:
                logger.warning(
                    f"Agent {self._agent_id}: File '{file_path}' is empty (0 bytes)"
                )
                # Still allow empty files - some use cases may need them

            # Remove existing file if present (to handle file updates)
            if existing_file and existing_file.file_id:
                logger.debug(
                    f"Agent {self._agent_id}: Removing existing file for path '{file_path}' "
                    f"(file_id={existing_file.file_id})"
                )
                await self._session_repository.remove_file(
                    self._session_id, existing_file.file_id
                )

            # Extract filename from path
            file_name = file_path.split("/")[-1]
            if not file_name:
                file_name = "unnamed_file"
                logger.warning(
                    f"Agent {self._agent_id}: Could not extract filename from '{file_path}', "
                    f"using '{file_name}'"
                )

            # Upload to GridFS storage
            file_info = await self._file_storage.upload_file(
                file_data, file_name, self._user_id
            )

            # Validate upload result
            if not file_info:
                logger.error(
                    f"Agent {self._agent_id}: File storage returned None for '{file_path}'"
                )
                return None

            if not file_info.file_id:
                logger.error(
                    f"Agent {self._agent_id}: Uploaded file has no file_id for '{file_path}'"
                )
                return None

            # Set the file_path for reference
            file_info.file_path = file_path

            # Register file with session
            await self._session_repository.add_file(self._session_id, file_info)

            logger.debug(
                f"Agent {self._agent_id}: Successfully synced file '{file_path}' "
                f"-> file_id={file_info.file_id}, size={file_data.getbuffer().nbytes} bytes"
            )

            return file_info

        except FileNotFoundError as e:
            logger.warning(
                f"Agent {self._agent_id}: File not found in sandbox: '{file_path}' - {e}"
            )
            return None
        except Exception as e:
            logger.exception(
                f"Agent {self._agent_id}: Failed to sync file '{file_path}': {e}"
            )
            return None

    async def _sync_file_to_sandbox(self, file_id: str) -> FileInfo | None:
        """Download file from storage to sandbox"""
        try:
            file_data, file_info = await self._file_storage.download_file(file_id, self._user_id)
            file_path = "/home/ubuntu/upload/" + file_info.filename
            result = await self._sandbox.file_upload(file_data, file_path)
            if result.success:
                file_info.file_path = file_path
                return file_info
        except Exception as e:
            logger.exception(f"Agent {self._agent_id} failed to sync file: {e}")

    async def _sync_event_attachments_to_storage(self, event: EventWithAttachments) -> None:
        """
        Sync event attachments to storage and update the event with resolved FileInfo objects.

        This method handles attachment syncing for any event type that has an attachments field
        (MessageEvent, ReportEvent, etc.). It:
        1. Filters out attachments with invalid/missing file_path
        2. Syncs valid attachments to GridFS storage concurrently
        3. Updates the event's attachments with fully resolved FileInfo objects (with file_id)
        4. Logs warnings for failed syncs but continues processing other attachments

        Args:
            event: An event with an attachments field (MessageEvent or ReportEvent)
        """
        synced_attachments: list[FileInfo] = []
        event_type = event.type

        try:
            if not event.attachments:
                logger.debug(f"Agent {self._agent_id}: {event_type} event has no attachments to sync")
                return

            # Filter valid attachments - must have a non-empty file_path
            valid_attachments = []
            for attachment in event.attachments:
                if attachment.file_path and attachment.file_path.strip():
                    valid_attachments.append(attachment)
                else:
                    logger.warning(
                        f"Agent {self._agent_id}: Skipping attachment with invalid file_path: "
                        f"file_id={attachment.file_id}, filename={attachment.filename}"
                    )

            if not valid_attachments:
                logger.debug(f"Agent {self._agent_id}: No valid attachments to sync for {event_type} event")
                event.attachments = []
                return

            logger.info(
                f"Agent {self._agent_id}: Syncing {len(valid_attachments)} attachments "
                f"for {event_type} event to storage"
            )

            # Sync all valid attachments concurrently
            sync_tasks = [
                self._sync_file_to_storage(attachment.file_path)
                for attachment in valid_attachments
            ]
            results = await asyncio.gather(*sync_tasks, return_exceptions=True)

            # Process results, collecting successfully synced attachments
            for i, result in enumerate(results):
                file_path = valid_attachments[i].file_path
                if isinstance(result, Exception):
                    logger.warning(
                        f"Agent {self._agent_id}: Failed to sync attachment '{file_path}': {result}"
                    )
                elif result is None:
                    logger.warning(
                        f"Agent {self._agent_id}: Sync returned None for attachment '{file_path}'"
                    )
                elif not result.file_id:
                    logger.warning(
                        f"Agent {self._agent_id}: Synced attachment '{file_path}' has no file_id"
                    )
                else:
                    synced_attachments.append(result)
                    logger.debug(
                        f"Agent {self._agent_id}: Successfully synced attachment "
                        f"'{file_path}' -> file_id={result.file_id}"
                    )
            logger.info(
                f"Agent {self._agent_id}: Successfully synced {len(synced_attachments)}/{len(valid_attachments)} "
                f"attachments for {event_type} event"
            )

        except Exception as e:
            logger.exception(
                f"Agent {self._agent_id}: Unexpected error syncing attachments for {event_type} event: {e}"
            )

        # Always update event attachments - either with synced files or empty list
        # This ensures no null file_ids remain in the event
        event.attachments = synced_attachments

    def _get_tool_execution_agent(self):
        """Return an agent instance capable of invoking tools."""
        flow = self._flow
        if hasattr(flow, "executor") and flow.executor:
            return flow.executor
        if hasattr(flow, "_agent") and flow._agent:
            return flow._agent
        if hasattr(flow, "agent") and flow.agent:
            return flow.agent
        return None

    async def execute_pending_action(
        self,
        task: Task,
        action_id: str,
        accept: bool,
    ) -> None:
        """Execute a pending tool action deterministically after confirmation."""
        session = await self._session_repository.find_by_id(self._session_id)
        if not session or not session.pending_action:
            logger.warning("No pending action found for session %s", self._session_id)
            return

        pending = session.pending_action
        if pending.get("tool_call_id") != action_id:
            logger.warning(
                "Pending action id mismatch for session %s: %s != %s",
                self._session_id,
                pending.get("tool_call_id"),
                action_id,
            )

        if not accept:
            await self._session_repository.update_pending_action(
                self._session_id,
                None,
                "rejected",
            )
            reject_event = ToolEvent(
                status=ToolStatus.CALLED,
                tool_call_id=pending.get("tool_call_id"),
                tool_name=pending.get("tool_name"),
                function_name=pending.get("function_name"),
                function_args=pending.get("function_args", {}),
                function_result=ToolResult(success=False, message="Action rejected by user."),
                security_risk=pending.get("security_risk"),
                security_reason=pending.get("security_reason"),
                security_suggestions=pending.get("security_suggestions"),
                confirmation_state="rejected",
            )
            await self._put_and_add_event(task, reject_event)
            await self._put_and_add_event(
                task,
                MessageEvent(message="Action rejected by user.", role="assistant"),
            )
            return

        agent = self._get_tool_execution_agent()
        if not agent:
            logger.error("No tool execution agent available for session %s", self._session_id)
            return

        function_name = pending.get("function_name")
        function_args = pending.get("function_args", {})
        tool_call_id = pending.get("tool_call_id")
        tool_name = pending.get("tool_name")

        calling_event = ToolEvent(
            status=ToolStatus.CALLING,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            function_name=function_name,
            function_args=function_args,
            security_risk=pending.get("security_risk"),
            security_reason=pending.get("security_reason"),
            security_suggestions=pending.get("security_suggestions"),
            confirmation_state="confirmed",
        )
        await self._handle_tool_event(calling_event)
        await self._put_and_add_event(task, calling_event)

        try:
            tool = agent.get_tool(function_name)
            result = await agent.invoke_tool(
                tool,
                function_name,
                function_args,
                skip_security=True,
            )
        except Exception as exc:
            result = ToolResult(success=False, message=str(exc))

        called_event = ToolEvent(
            status=ToolStatus.CALLED,
            tool_call_id=tool_call_id,
            tool_name=tool_name,
            function_name=function_name,
            function_args=function_args,
            function_result=result,
            security_risk=pending.get("security_risk"),
            security_reason=pending.get("security_reason"),
            security_suggestions=pending.get("security_suggestions"),
            confirmation_state="confirmed",
        )
        await self._handle_tool_event(called_event)
        await self._put_and_add_event(task, called_event)

        await self._session_repository.update_pending_action(
            self._session_id,
            None,
            "confirmed",
        )

    async def _sync_message_attachments_to_sandbox(self, event: MessageEvent) -> None:
        """Sync message attachments concurrently and update event attachments"""
        attachments: list[FileInfo] = []
        try:
            if event.attachments:
                # Sync all attachments concurrently
                sync_tasks = [
                    self._sync_file_to_sandbox(attachment.file_id)
                    for attachment in event.attachments
                ]
                results = await asyncio.gather(*sync_tasks, return_exceptions=True)

                # Process results and add to session
                add_file_tasks = []
                for result in results:
                    if isinstance(result, Exception):
                        logger.warning(f"Sandbox sync failed: {result}")
                    elif result:
                        attachments.append(result)
                        add_file_tasks.append(
                            self._session_repository.add_file(self._session_id, result)
                        )

                # Add files to session concurrently
                if add_file_tasks:
                    await asyncio.gather(*add_file_tasks, return_exceptions=True)

            event.attachments = attachments
        except Exception as e:
            logger.exception(f"Agent {self._agent_id} failed to sync attachments to event: {e}")

    @asynccontextmanager
    async def _usage_context(self):
        """Ensure LLM usage is attributed to the current user/session."""
        if self._user_id and self._session_id:
            async with UsageContextManager(
                user_id=self._user_id,
                session_id=self._session_id,
            ):
                yield
        else:
            yield

    async def _record_tool_call_usage(self) -> None:
        """Record tool call usage for usage dashboard metrics."""
        if not self._user_id:
            return
        try:
            usage_service = get_usage_service()
            await usage_service.record_tool_call(
                user_id=self._user_id,
                session_id=self._session_id,
            )
        except Exception as e:
            logger.debug(f"Failed to record tool usage for Agent {self._agent_id}: {e}")


    # TODO: refactor this function
    async def _handle_tool_event(self, event: ToolEvent):
        """Generate tool content"""
        try:
            # Common action metadata
            if event.tool_name == "shell":
                event.action_type = "run"
                event.command = event.function_args.get("command")
                event.cwd = event.function_args.get("exec_dir")
            elif event.tool_name == "code_executor":
                event.action_type = "run"
                event.command = event.function_args.get("code") or event.function_args.get("command")
            elif event.tool_name == "file":
                event.file_path = event.function_args.get("file")
                if event.function_name == "file_read":
                    event.action_type = "read"
                elif event.function_name == "file_write":
                    event.action_type = "write"
                elif event.function_name == "file_str_replace":
                    event.action_type = "edit"
                else:
                    event.action_type = "edit"
            elif event.tool_name == "browser" or event.tool_name == "browser_agent":
                event.action_type = "browse"
            elif event.tool_name == "search":
                event.action_type = "search"
            elif event.tool_name == "mcp":
                event.action_type = "call_tool"

            if event.status == ToolStatus.CALLED and event.tool_name != "message":
                await self._record_tool_call_usage()
            # Handle CALLING status for streaming preview (file_write shows content being generated)
            if event.status == ToolStatus.CALLING:
                # Track tool start time for duration measurement
                self._tool_start_times[event.tool_call_id] = time.perf_counter()

                if event.confirmation_state == "awaiting_confirmation":
                    pending_action = {
                        "tool_call_id": event.tool_call_id,
                        "tool_name": event.tool_name,
                        "function_name": event.function_name,
                        "function_args": event.function_args,
                        "security_risk": event.security_risk,
                        "security_reason": event.security_reason,
                        "security_suggestions": event.security_suggestions,
                    }
                    self._pending_tool_calls[event.tool_call_id] = pending_action
                    await self._session_repository.update_pending_action(
                        self._session_id,
                        pending_action,
                        "awaiting_confirmation",
                    )

                # Cache original file content for diff generation
                if event.tool_name == "file" and event.function_name in (
                    "file_write",
                    "file_str_replace",
                ):
                    file_path = event.function_args.get("file")
                    if file_path:
                        try:
                            before_result = await self._sandbox.file_read(file_path)
                            if before_result.success:
                                self._file_before_cache[event.tool_call_id] = before_result.data.get("content", "")
                            else:
                                self._file_before_cache[event.tool_call_id] = ""
                        except Exception:
                            self._file_before_cache[event.tool_call_id] = ""

                if event.tool_name == "file" and event.function_name == "file_write":
                    # Show the content being written for streaming preview
                    content = event.function_args.get("content", "")
                    if content:
                        event.tool_content = FileToolContent(content=content)
                        logger.debug(f"File write preview: {len(content)} chars")
            elif event.status == ToolStatus.CALLED:
                # Duration measurement
                start_time = self._tool_start_times.pop(event.tool_call_id, None)
                if start_time is not None:
                    event.duration_ms = int((time.perf_counter() - start_time) * 1000)

                if event.tool_name == "browser":
                    # Extract page content from function result if available
                    page_content = None
                    if event.function_result and hasattr(event.function_result, "data"):
                        result_data = event.function_result.data
                        if isinstance(result_data, dict):
                            # Try to get content from various possible fields
                            page_content = result_data.get("content") or result_data.get("text") or result_data.get("data")
                        elif isinstance(result_data, str):
                            page_content = result_data
                    event.tool_content = BrowserToolContent(content=page_content)
                elif event.tool_name == "search":
                    search_results: ToolResult[SearchResults] = event.function_result
                    logger.debug(f"Search tool results: {search_results}")
                    event.tool_content = SearchToolContent(
                        results=search_results.data.results
                    )
                elif event.tool_name == "shell":
                    event.observation_type = "run"
                    if event.function_result and hasattr(event.function_result, "data"):
                        data = event.function_result.data or {}
                        if isinstance(data, dict):
                            event.stdout = data.get("output")
                            event.exit_code = data.get("returncode")
                    if "id" in event.function_args:
                        shell_result = await self._sandbox.view_shell(event.function_args["id"], console=True)
                        event.tool_content = ShellToolContent(
                            console=shell_result.data.get("console", [])
                        )
                    else:
                        event.tool_content = ShellToolContent(
                            console="(No Console)"
                        )
                elif event.tool_name == "file":
                    event.observation_type = "edit"
                    if "file" in event.function_args:
                        file_path = event.function_args["file"]
                        # Read file and sync to storage concurrently
                        file_read_task = self._sandbox.file_read(file_path)
                        sync_task = self._sync_file_to_storage(file_path)
                        file_read_result, _ = await asyncio.gather(
                            file_read_task, sync_task, return_exceptions=True
                        )
                        if isinstance(file_read_result, Exception):
                            file_content = f"(Error: {file_read_result})"
                        else:
                            file_content = file_read_result.data.get("content", "")
                        event.tool_content = FileToolContent(
                            content=file_content
                        )

                        before_content = self._file_before_cache.pop(event.tool_call_id, "")
                        diff_text = build_unified_diff(before_content, file_content, file_path)
                        if diff_text:
                            event.diff = diff_text
                    else:
                        event.tool_content = FileToolContent(
                            content="(No Content)"
                        )
                elif event.tool_name == "mcp":
                    logger.debug(f"Processing MCP tool event: function_result={event.function_result}")
                    if event.function_result:
                        if hasattr(event.function_result, 'data') and event.function_result.data:
                            logger.debug(f"MCP tool result data: {event.function_result.data}")
                            event.tool_content = McpToolContent(
                                result=event.function_result.data
                            )
                        elif hasattr(event.function_result, 'success') and event.function_result.success:
                            logger.debug(f"MCP tool result (success, no data): {event.function_result}")
                            result_data = event.function_result.model_dump() if hasattr(event.function_result, 'model_dump') else str(event.function_result)
                            event.tool_content = McpToolContent(
                                result=result_data
                            )
                        else:
                            logger.debug(f"MCP tool result (fallback): {event.function_result}")
                            event.tool_content = McpToolContent(
                                result=str(event.function_result)
                            )
                    else:
                        logger.warning("MCP tool: No function_result found")
                        event.tool_content = McpToolContent(
                            result="No result available"
                        )

                    logger.debug(f"MCP tool_content set to: {event.tool_content}")
                    if event.tool_content:
                        logger.debug(f"MCP tool_content.result: {event.tool_content.result}")
                        logger.debug(f"MCP tool_content dict: {event.tool_content.model_dump()}")
                elif event.tool_name == "browser_agent":
                    logger.debug(f"Processing browser_agent tool event: function_result={event.function_result}")
                    if event.function_result:
                        result_data = event.function_result.data if hasattr(event.function_result, 'data') else {}
                        steps_taken = result_data.get('steps_taken', 0) if isinstance(result_data, dict) else 0
                        result = result_data.get('result', str(result_data)) if isinstance(result_data, dict) else str(result_data)
                        event.tool_content = BrowserAgentToolContent(
                            result=result,
                            steps_taken=steps_taken
                        )
                    else:
                        event.tool_content = BrowserAgentToolContent(
                            result="No result available",
                            steps_taken=0
                        )
                elif event.tool_name == "agent_mode":
                    # agent_mode is a control tool, no special content needed
                    logger.debug("Processing agent_mode tool event")
                elif event.tool_name == "message":
                    # message tool events don't need tool_content
                    logger.debug("Processing message tool event")
                elif event.tool_name == "code_executor":
                    event.observation_type = "run"
                    # Code execution output shown in terminal-like view
                    if event.function_result and hasattr(event.function_result, 'data'):
                        data = event.function_result.data
                        if isinstance(data, dict):
                            # Extract stdout/stderr for console display
                            console_output = []
                            if data.get('stdout'):
                                console_output.append(data['stdout'])
                            if data.get('stderr'):
                                console_output.append(f"[stderr] {data['stderr']}")
                            if data.get('exit_code') is not None:
                                console_output.append(f"[exit code: {data['exit_code']}]")
                            event.stdout = data.get("stdout")
                            event.stderr = data.get("stderr")
                            event.exit_code = data.get("exit_code")
                            event.tool_content = ShellToolContent(
                                console="\n".join(console_output) if console_output else "(No output)"
                            )
                        else:
                            event.tool_content = ShellToolContent(
                                console=str(data) if data else "(No output)"
                            )
                    else:
                        event.tool_content = ShellToolContent(
                            console="(No output)"
                        )
                else:
                    logger.warning(f"Agent {self._agent_id} received unknown tool event: {event.tool_name}")
        except Exception as e:
            logger.exception(f"Agent {self._agent_id} failed to generate tool content: {e}")

    async def run(self, task: Task) -> None:
        """Process agent's message queue and run the agent's flow"""
        try:
            logger.info(f"Agent {self._agent_id} message processing task started")

            # Initialize sandbox and MCP tool concurrently
            async def init_mcp():
                config = await self._mcp_repository.get_mcp_config()
                await self._mcp_tool.initialized(config)

            await asyncio.gather(
                self._sandbox.ensure_sandbox(),
                init_mcp(),
                return_exceptions=True
            )
            logger.debug(f"Agent {self._agent_id} concurrent initialization completed")
            while not await task.input_stream.is_empty():
                event = await self._pop_event(task)
                message = ""
                if isinstance(event, MessageEvent):
                    message = event.message or ""
                    await self._sync_message_attachments_to_sandbox(event)

                logger.info(f"Agent {self._agent_id} received new message: {message[:50]}...")

                message_obj = Message(message=message, attachments=[attachment.file_path for attachment in event.attachments])

                async for event in self._run_flow(message_obj, task):
                    # Check if task is paused (for user takeover)
                    while task.paused:
                        logger.debug(f"Agent {self._agent_id} paused, waiting for resume...")
                        await asyncio.sleep(0.5)

                    await self._put_and_add_event(task, event)
                    if isinstance(event, TitleEvent):
                        await self._session_repository.update_title(self._session_id, event.title)
                    elif isinstance(event, MessageEvent):
                        await self._session_repository.update_latest_message(self._session_id, event.message, event.timestamp)
                        await self._session_repository.increment_unread_message_count(self._session_id)
                    elif isinstance(event, WaitEvent):
                        await self._session_repository.update_status(self._session_id, SessionStatus.WAITING)
                        return
                    if not await task.input_stream.is_empty():
                        break

            await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
        except asyncio.CancelledError:
            logger.info(f"Agent {self._agent_id} task cancelled")
            await self._put_and_add_event(task, DoneEvent())
            await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
        except Exception as e:
            logger.exception(f"Agent {self._agent_id} task encountered exception: {e!s}")
            await self._put_and_add_event(task, ErrorEvent(error=f"Task error: {e!s}"))
            await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)

    async def _run_flow(self, message: Message, task: Task | None = None) -> AsyncGenerator[BaseEvent, None]:
        """Process a single message through the agent's flow and yield events

        Args:
            message: The message to process
            task: Optional task reference for pause checking
        """
        if not message.message:
            logger.warning(f"Agent {self._agent_id} received empty message")
            yield ErrorEvent(error="No message")
            return

        mode_switch_task: str | None = None

        async with self._usage_context():
            async for event in self._flow.run(message):
                # Check if task is paused (for user takeover) before processing each event
                if task and hasattr(task, 'paused'):
                    while task.paused:
                        logger.debug(f"Agent {self._agent_id} paused in flow, waiting for resume...")
                        await asyncio.sleep(0.5)

                if isinstance(event, ToolEvent):
                    # TODO: move to tool function
                    await self._handle_tool_event(event)
                elif isinstance(event, (MessageEvent, ReportEvent)):
                    # Sync attachments to storage for events that contain file references
                    # This resolves file_path to file_id for proper frontend access
                    await self._sync_event_attachments_to_storage(event)
                elif isinstance(event, ModeChangeEvent):
                    # Handle mode switch from Discuss to Agent
                    if event.mode == "agent" and self._mode == AgentMode.DISCUSS:
                        # Get the task from the discuss flow
                        if self._discuss_flow and self._discuss_flow.mode_switch_task:
                            mode_switch_task = self._discuss_flow.mode_switch_task
                        yield event
                        continue
                yield event

        # If mode switch was requested, switch to Agent mode and re-run with the task
        if mode_switch_task and self._mode == AgentMode.DISCUSS:
            logger.info(f"Executing mode switch to Agent for task: {mode_switch_task}")
            await self._switch_to_agent_mode(mode_switch_task)

            # Create a new message with the task description
            task_message = Message(message=mode_switch_task, attachments=message.attachments)

            # Run through Agent mode flow
            async with self._usage_context():
                async for event in self._flow.run(task_message):
                    # Check if task is paused (for user takeover)
                    if task and hasattr(task, 'paused'):
                        while task.paused:
                            logger.debug(f"Agent {self._agent_id} paused in mode switch flow, waiting for resume...")
                            await asyncio.sleep(0.5)

                    if isinstance(event, ToolEvent):
                        await self._handle_tool_event(event)
                    elif isinstance(event, (MessageEvent, ReportEvent)):
                        # Sync attachments to storage for events that contain file references
                        await self._sync_event_attachments_to_storage(event)
                    yield event

        logger.info(f"Agent {self._agent_id} completed processing one message")


    async def on_done(self, task: Task) -> None:
        """Called when the task is done"""
        logger.info(f"Agent {self._agent_id} task done")


    async def destroy(self) -> None:
        """Destroy the task and release resources"""
        logger.info("Starting to destroy agent task")

        # Shutdown coordinator flow if used
        if self._coordinator_flow:
            logger.debug(f"Shutting down Agent {self._agent_id}'s coordinator flow")
            await self._coordinator_flow.shutdown()

        # Destroy sandbox environment
        if self._sandbox:
            logger.debug(f"Destroying Agent {self._agent_id}'s sandbox environment")
            await self._sandbox.destroy()

        if self._mcp_tool:
            logger.debug(f"Destroying Agent {self._agent_id}'s MCP tool")
            await self._mcp_tool.cleanup()

        logger.debug(f"Agent {self._agent_id} has been fully closed and resources cleared")
