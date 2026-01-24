from typing import Optional, AsyncGenerator, List, Union
import asyncio
import logging
from pydantic import TypeAdapter
from app.domain.models.message import Message
from app.domain.models.event import (
    BaseEvent,
    ErrorEvent,
    TitleEvent,
    MessageEvent,
    DoneEvent,
    ToolEvent,
    WaitEvent,
    FileToolContent,
    ShellToolContent,
    SearchToolContent,
    BrowserToolContent,
    BrowserAgentToolContent,
    ToolStatus,
    AgentEvent,
    McpToolContent,
    ModeChangeEvent,
    SuggestionEvent,
    ReportEvent,
)

# Type alias for events that contain attachments requiring storage sync
# Both MessageEvent and ReportEvent have an 'attachments' field of type Optional[List[FileInfo]]
EventWithAttachments = Union[MessageEvent, ReportEvent]
from app.domain.services.flows.plan_act import PlanActFlow
from app.domain.services.flows.discuss import DiscussFlow
from app.domain.external.sandbox import Sandbox
from app.domain.external.browser import Browser
from app.domain.external.search import SearchEngine
from app.domain.external.llm import LLM
from app.domain.external.file import FileStorage
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.external.task import TaskRunner, Task
from app.domain.repositories.session_repository import SessionRepository
from app.domain.repositories.mcp_repository import MCPRepository
from app.domain.models.session import SessionStatus, AgentMode
from app.domain.models.file import FileInfo
from app.domain.utils.json_parser import JsonParser
from app.domain.services.tools.mcp import MCPTool
from app.domain.models.tool_result import ToolResult
from app.domain.models.search import SearchResults

logger = logging.getLogger(__name__)

class AgentTaskRunner(TaskRunner):
    """Agent task that can be cancelled"""
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
        search_engine: Optional[SearchEngine] = None,
        mode: AgentMode = AgentMode.AGENT,
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

        # Initialize flows based on mode
        self._plan_act_flow: Optional[PlanActFlow] = None
        self._discuss_flow: Optional[DiscussFlow] = None

        if mode == AgentMode.AGENT:
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
            )
            logger.debug(f"Initialized PlanActFlow for agent {self._agent_id}")

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
        self._init_plan_act_flow()
        await self._session_repository.update_mode(self._session_id, AgentMode.AGENT)

    @property
    def _flow(self):
        """Get the current flow based on mode"""
        if self._mode == AgentMode.AGENT:
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
            return
        event = TypeAdapter(AgentEvent).validate_json(event_str)
        event.id = event_id
        return event
    
    async def _get_browser_screenshot(self) -> str:
        screenshot = await self._browser.screenshot()
        result = await self._file_storage.upload_file(screenshot, "screenshot.png", self._user_id)
        return result.file_id

    async def _sync_file_to_storage(self, file_path: str) -> Optional[FileInfo]:
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

            if len(file_data) == 0:
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
                f"-> file_id={file_info.file_id}, size={len(file_data)} bytes"
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
    
    async def _sync_file_to_sandbox(self, file_id: str) -> Optional[FileInfo]:
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
        synced_attachments: List[FileInfo] = []
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
    
    async def _sync_message_attachments_to_sandbox(self, event: MessageEvent) -> None:
        """Sync message attachments concurrently and update event attachments"""
        attachments: List[FileInfo] = []
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
    

    # TODO: refactor this function
    async def _handle_tool_event(self, event: ToolEvent):
        """Generate tool content"""
        try:
            if event.status == ToolStatus.CALLED:
                if event.tool_name == "browser":
                    event.tool_content = BrowserToolContent(screenshot=await self._get_browser_screenshot())
                elif event.tool_name == "search":
                    search_results: ToolResult[SearchResults] = event.function_result
                    logger.debug(f"Search tool results: {search_results}")
                    event.tool_content = SearchToolContent(results=search_results.data.results)
                elif event.tool_name == "shell":
                    if "id" in event.function_args:
                        shell_result = await self._sandbox.view_shell(event.function_args["id"], console=True)
                        event.tool_content = ShellToolContent(console=shell_result.data.get("console", []))
                    else:
                        event.tool_content = ShellToolContent(console="(No Console)")
                elif event.tool_name == "file":
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
                        event.tool_content = FileToolContent(content=file_content)
                    else:
                        event.tool_content = FileToolContent(content="(No Content)")
                elif event.tool_name == "mcp":
                    logger.debug(f"Processing MCP tool event: function_result={event.function_result}")
                    if event.function_result:
                        if hasattr(event.function_result, 'data') and event.function_result.data:
                            logger.debug(f"MCP tool result data: {event.function_result.data}")
                            event.tool_content = McpToolContent(result=event.function_result.data)
                        elif hasattr(event.function_result, 'success') and event.function_result.success:
                            logger.debug(f"MCP tool result (success, no data): {event.function_result}")
                            result_data = event.function_result.model_dump() if hasattr(event.function_result, 'model_dump') else str(event.function_result)
                            event.tool_content = McpToolContent(result=result_data)
                        else:
                            logger.debug(f"MCP tool result (fallback): {event.function_result}")
                            event.tool_content = McpToolContent(result=str(event.function_result))
                    else:
                        logger.warning("MCP tool: No function_result found")
                        event.tool_content = McpToolContent(result="No result available")

                    logger.debug(f"MCP tool_content set to: {event.tool_content}")
                    if event.tool_content:
                        logger.debug(f"MCP tool_content.result: {event.tool_content.result}")
                        logger.debug(f"MCP tool_content dict: {event.tool_content.model_dump()}")
                elif event.tool_name == "browser_agent":
                    # Handle browser agent tool results with screenshot
                    logger.debug(f"Processing browser_agent tool event: function_result={event.function_result}")
                    screenshot_id = await self._get_browser_screenshot()
                    if event.function_result:
                        result_data = event.function_result.data if hasattr(event.function_result, 'data') else {}
                        steps_taken = result_data.get('steps_taken', 0) if isinstance(result_data, dict) else 0
                        result = result_data.get('result', str(result_data)) if isinstance(result_data, dict) else str(result_data)
                        event.tool_content = BrowserAgentToolContent(
                            result=result,
                            steps_taken=steps_taken,
                            screenshot=screenshot_id
                        )
                    else:
                        event.tool_content = BrowserAgentToolContent(
                            result="No result available",
                            steps_taken=0,
                            screenshot=screenshot_id
                        )
                elif event.tool_name == "agent_mode":
                    # agent_mode is a control tool, no special content needed
                    logger.debug(f"Processing agent_mode tool event")
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
                
                async for event in self._run_flow(message_obj):
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
            logger.exception(f"Agent {self._agent_id} task encountered exception: {str(e)}")
            await self._put_and_add_event(task, ErrorEvent(error=f"Task error: {str(e)}"))
            await self._session_repository.update_status(self._session_id, SessionStatus.COMPLETED)
    
    async def _run_flow(self, message: Message) -> AsyncGenerator[BaseEvent, None]:
        """Process a single message through the agent's flow and yield events"""
        if not message.message:
            logger.warning(f"Agent {self._agent_id} received empty message")
            yield ErrorEvent(error="No message")
            return

        mode_switch_task: Optional[str] = None

        async for event in self._flow.run(message):
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
            async for event in self._flow.run(task_message):
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
        logger.info(f"Starting to destroy agent task")
        
        # Destroy sandbox environment
        if self._sandbox:
            logger.debug(f"Destroying Agent {self._agent_id}'s sandbox environment")
            await self._sandbox.destroy()
        
        if self._mcp_tool:
            logger.debug(f"Destroying Agent {self._agent_id}'s MCP tool")
            await self._mcp_tool.cleanup()
        
        logger.debug(f"Agent {self._agent_id} has been fully closed and resources cleared")
