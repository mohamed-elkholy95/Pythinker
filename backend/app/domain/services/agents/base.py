import json
import logging
import asyncio
import uuid
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional, AsyncGenerator, Tuple
from app.domain.external.llm import LLM
from app.domain.models.agent import Agent
from app.domain.models.memory import Memory
from app.domain.models.message import Message
from app.domain.services.tools.base import BaseTool
from app.domain.models.tool_result import ToolResult
from app.domain.models.event import (
    BaseEvent,
    ToolEvent,
    ToolStatus,
    ErrorEvent,
    MessageEvent,
    DoneEvent,
    StreamEvent,
)
from app.domain.repositories.agent_repository import AgentRepository
from app.domain.utils.json_parser import JsonParser
from app.domain.services.agents.stuck_detector import StuckDetector
from app.domain.services.agents.token_manager import TokenManager
from app.domain.services.agents.error_handler import ErrorHandler, TokenLimitExceeded, ErrorType

logger = logging.getLogger(__name__)

# Tools that are safe to execute in parallel (read-only, no side effects)
SAFE_PARALLEL_TOOLS = {
    "info_search_web",
    "file_read",
    "file_search",
    "file_list_directory",
    "browser_get_content",  # Fast text-only fetch
    "browser_view",
    "browser_screenshot",
}

# Maximum number of concurrent tool executions
MAX_CONCURRENT_TOOLS = 3
class BaseAgent(ABC):
    """
    Base agent class, defining the basic behavior of the agent
    """

    name: str = ""
    system_prompt: str = ""
    format: Optional[str] = None
    max_iterations: int = 100
    max_retries: int = 3
    retry_interval: float = 0.3  # Faster retry with exponential backoff
    retry_backoff: float = 1.5  # Backoff multiplier (0.3s -> 0.45s -> 0.67s)
    tool_choice: Optional[str] = None

    def __init__(
        self,
        agent_id: str,
        agent_repository: AgentRepository,
        llm: LLM,
        json_parser: JsonParser,
        tools: List[BaseTool] = []
    ):
        self._agent_id = agent_id
        self._repository = agent_repository
        self.llm = llm
        self.json_parser = json_parser
        self.tools = tools
        self.memory = None

        # Initialize reliability components
        self._stuck_detector = StuckDetector(window_size=5, threshold=3)
        self._token_manager = TokenManager(model_name=getattr(llm, 'model_name', 'gpt-4'))
        self._error_handler = ErrorHandler()
    
    def get_available_tools(self) -> Optional[List[Dict[str, Any]]]:
        """Get all available tools list"""
        available_tools = []
        for tool in self.tools:
            available_tools.extend(tool.get_tools())
        return available_tools
    
    def get_tool(self, function_name: str) -> BaseTool:
        """Get specified tool"""
        for tool in self.tools:
            if tool.has_function(function_name):
                return tool
        raise ValueError(f"Unknown tool: {function_name}")

    async def invoke_tool(self, tool: BaseTool, function_name: str, arguments: Dict[str, Any]) -> ToolResult:
        """Invoke specified tool, with retry mechanism and exponential backoff"""

        retries = 0
        current_interval = self.retry_interval
        last_error = ""
        while retries <= self.max_retries:
            try:
                return await tool.invoke_function(function_name, **arguments)
            except Exception as e:
                last_error = str(e)
                retries += 1
                if retries <= self.max_retries:
                    await asyncio.sleep(current_interval)
                    current_interval *= self.retry_backoff  # Exponential backoff
                else:
                    logger.exception(f"Tool execution failed, {function_name}, {arguments}")
                    break

        return ToolResult(success=False, message=last_error)

    def _can_parallelize_tools(self, tool_calls: List[Dict]) -> bool:
        """Check if all tool calls in the list can be executed in parallel"""
        if len(tool_calls) <= 1:
            return False
        return all(
            tc.get("function", {}).get("name") in SAFE_PARALLEL_TOOLS
            for tc in tool_calls
        )

    async def _invoke_tool_with_semaphore(
        self,
        semaphore: asyncio.Semaphore,
        tool_call: Dict,
        function_args: Dict[str, Any]
    ) -> Tuple[Dict, BaseTool, ToolResult]:
        """Invoke a single tool with semaphore limiting concurrent executions"""
        async with semaphore:
            function_name = tool_call["function"]["name"]
            tool = self.get_tool(function_name)
            result = await self.invoke_tool(tool, function_name, function_args)
            return tool_call, tool, result
    
    async def execute(self, request: str, format: Optional[str] = None) -> AsyncGenerator[BaseEvent, None]:
        format = format or self.format
        # Don't use json_object format when tools are available - causes empty responses
        # Only enforce JSON format after tool calling is complete
        has_tools = bool(self.get_available_tools())
        initial_format = None if has_tools else format
        message = await self.ask(request, initial_format)
        for _ in range(self.max_iterations):
            if not message.get("tool_calls"):
                break

            tool_calls = message["tool_calls"]
            tool_responses = []

            # Check if we can execute tools in parallel
            if self._can_parallelize_tools(tool_calls):
                # Parse all arguments first
                parsed_calls = []
                for tool_call in tool_calls[:MAX_CONCURRENT_TOOLS]:  # Limit parallel calls
                    if not tool_call.get("function"):
                        continue
                    function_name = tool_call["function"]["name"]
                    tool_call_id = tool_call["id"] or str(uuid.uuid4())
                    function_args = await self.json_parser.parse(tool_call["function"]["arguments"])
                    tool = self.get_tool(function_name)

                    # Emit CALLING events for all parallel tools
                    yield ToolEvent(
                        status=ToolStatus.CALLING,
                        tool_call_id=tool_call_id,
                        tool_name=tool.name,
                        function_name=function_name,
                        function_args=function_args
                    )
                    parsed_calls.append((tool_call, tool_call_id, function_args, tool))

                # Execute all tools concurrently with semaphore
                semaphore = asyncio.Semaphore(MAX_CONCURRENT_TOOLS)
                tasks = []
                for tool_call, tool_call_id, function_args, tool in parsed_calls:
                    function_name = tool_call["function"]["name"]
                    tasks.append(
                        self._execute_parallel_tool(
                            semaphore, tool, function_name, function_args,
                            tool_call_id
                        )
                    )

                results = await asyncio.gather(*tasks, return_exceptions=True)

                # Process results and emit CALLED events
                for (tool_call, tool_call_id, function_args, tool), result in zip(parsed_calls, results):
                    function_name = tool_call["function"]["name"]
                    if isinstance(result, Exception):
                        result = ToolResult(success=False, message=str(result))

                    yield ToolEvent(
                        status=ToolStatus.CALLED,
                        tool_call_id=tool_call_id,
                        tool_name=tool.name,
                        function_name=function_name,
                        function_args=function_args,
                        function_result=result
                    )

                    tool_responses.append({
                        "role": "tool",
                        "function_name": function_name,
                        "tool_call_id": tool_call_id,
                        "content": result.model_dump_json() if hasattr(result, 'model_dump_json') else str(result)
                    })
            else:
                # Sequential execution for non-parallelizable tools (original behavior)
                for tool_call in tool_calls:
                    if not tool_call.get("function"):
                        continue

                    function_name = tool_call["function"]["name"]
                    tool_call_id = tool_call["id"] or str(uuid.uuid4())
                    function_args = await self.json_parser.parse(tool_call["function"]["arguments"])

                    tool = self.get_tool(function_name)

                    # Generate event before tool call
                    yield ToolEvent(
                        status=ToolStatus.CALLING,
                        tool_call_id=tool_call_id,
                        tool_name=tool.name,
                        function_name=function_name,
                        function_args=function_args
                    )

                    result = await self.invoke_tool(tool, function_name, function_args)

                    # Generate event after tool call
                    yield ToolEvent(
                        status=ToolStatus.CALLED,
                        tool_call_id=tool_call_id,
                        tool_name=tool.name,
                        function_name=function_name,
                        function_args=function_args,
                        function_result=result
                    )

                    tool_responses.append({
                        "role": "tool",
                        "function_name": function_name,
                        "tool_call_id": tool_call_id,
                        "content": result.model_dump_json()
                    })

            message = await self.ask_with_messages(tool_responses)
        else:
            yield ErrorEvent(error="Maximum iteration count reached, failed to complete the task")

        yield MessageEvent(message=message["content"])

    async def _execute_parallel_tool(
        self,
        semaphore: asyncio.Semaphore,
        tool: BaseTool,
        function_name: str,
        function_args: Dict[str, Any],
        tool_call_id: str
    ) -> ToolResult:
        """Execute a single tool with semaphore limiting concurrent executions"""
        async with semaphore:
            return await self.invoke_tool(tool, function_name, function_args)
    
    async def _ensure_memory(self):
        if not self.memory:
            self.memory = await self._repository.get_memory(self._agent_id, self.name)
    
    async def _add_to_memory(self, messages: List[Dict[str, Any]]) -> None:
        """Update memory and save to repository"""
        await self._ensure_memory()
        if self.memory.empty:
            self.memory.add_message({
                "role": "system", "content": self.system_prompt,
            })
        self.memory.add_messages(messages)
        await self._repository.save_memory(self._agent_id, self.name, self.memory)
    
    async def _roll_back_memory(self) -> None:
        await self._ensure_memory()
        self.memory.roll_back()
        await self._repository.save_memory(self._agent_id, self.name, self.memory)

    async def ask_with_messages(self, messages: List[Dict[str, Any]], format: Optional[str] = None) -> Dict[str, Any]:
        await self._add_to_memory(messages)

        # Check and handle token limits before making LLM call
        await self._ensure_within_token_limit()

        response_format = None
        if format:
            response_format = {"type": format}

        for retry in range(self.max_retries):
            try:
                message = await self.llm.ask(self.memory.get_messages(),
                                                tools=self.get_available_tools(),
                                                response_format=response_format,
                                                tool_choice=self.tool_choice)
            except TokenLimitExceeded as e:
                logger.warning(f"Token limit exceeded, trimming context: {e}")
                await self._handle_token_limit_exceeded()
                continue
            except Exception as e:
                error_context = self._error_handler.classify_error(e)
                if error_context.error_type == ErrorType.TOKEN_LIMIT:
                    await self._handle_token_limit_exceeded()
                    continue
                raise

            filtered_message = {}
            if message.get("role") == "assistant":
                if not message.get("content") and not message.get("tool_calls"):
                    logger.warning(f"Assistant message has no content, retry")
                    await self._add_to_memory([
                        {"role": "assistant", "content": ""},
                        {"role": "user", "content": "no thinking, please continue"}
                    ])
                    continue
                filtered_message = {
                    "role": "assistant",
                    "content": message.get("content"),
                }
                if message.get("tool_calls"):
                    tool_calls = message.get("tool_calls", [])
                    # Allow multiple tool calls for safe parallel tools
                    if self._can_parallelize_tools(tool_calls):
                        filtered_message["tool_calls"] = tool_calls[:MAX_CONCURRENT_TOOLS]
                    else:
                        filtered_message["tool_calls"] = tool_calls[:1]
            else:
                logger.warning(f"Unknown message role: {message.get('role')}")
                filtered_message = message

            # Track response for stuck detection
            is_stuck = self._stuck_detector.track_response(filtered_message)
            if is_stuck and self._stuck_detector.can_attempt_recovery():
                self._stuck_detector.record_recovery_attempt()
                recovery_prompt = self._stuck_detector.get_recovery_prompt()
                logger.warning(f"Agent stuck detected, injecting recovery prompt")
                await self._add_to_memory([
                    filtered_message,
                    {"role": "user", "content": recovery_prompt}
                ])
                continue

            await self._add_to_memory([filtered_message])
            return filtered_message
        raise Exception(f"Empty response from LLM after {self.max_retries} retries")

    async def _ensure_within_token_limit(self) -> None:
        """Ensure memory is within token limits, trim if necessary"""
        await self._ensure_memory()
        current_messages = self.memory.get_messages()

        if not self._token_manager.is_within_limit(current_messages):
            logger.warning("Memory exceeds token limit, trimming...")
            trimmed_messages, tokens_removed = self._token_manager.trim_messages(
                current_messages,
                preserve_system=True,
                preserve_recent=6
            )
            self.memory.messages = trimmed_messages
            await self._repository.save_memory(self._agent_id, self.name, self.memory)
            logger.info(f"Trimmed memory, removed {tokens_removed} tokens")

    async def _handle_token_limit_exceeded(self) -> None:
        """Handle token limit exceeded error by aggressively trimming context"""
        await self._ensure_memory()
        current_messages = self.memory.get_messages()

        # First compact verbose tool results
        self.memory.smart_compact()

        # Then trim messages
        trimmed_messages, tokens_removed = self._token_manager.trim_messages(
            self.memory.get_messages(),
            preserve_system=True,
            preserve_recent=4  # More aggressive trim
        )
        self.memory.messages = trimmed_messages
        await self._repository.save_memory(self._agent_id, self.name, self.memory)
        logger.info(f"Handled token limit by trimming {tokens_removed} tokens")

    async def ask(self, request: str, format: Optional[str] = None) -> Dict[str, Any]:
        return await self.ask_with_messages([
            {
                "role": "user", "content": request
            }
        ], format)
    
    async def roll_back(self, message: Message):
        await self._ensure_memory()
        last_message = self.memory.get_last_message()
        if (not last_message or 
            not last_message.get("tool_calls") or 
            len(last_message.get("tool_calls")) == 0):
            return
        tool_call = last_message.get("tool_calls")[0]
        function_name = tool_call.get("function", {}).get("name")
        tool_call_id = tool_call.get("id")
        if function_name == "message_ask_user":
            self.memory.add_message({
                "role": "tool",
                "tool_call_id": tool_call_id,
                "function_name": function_name,
                "content": message.model_dump_json()
            })
        else:
            self.memory.roll_back()
        await self._repository.save_memory(self._agent_id, self.name, self.memory)
    
    async def compact_memory(self) -> None:
        await self._ensure_memory()
        self.memory.compact()
        await self._repository.save_memory(self._agent_id, self.name, self.memory)

    async def ask_streaming(
        self,
        request: str,
        format: Optional[str] = None
    ) -> AsyncGenerator[BaseEvent, None]:
        """Execute a request with streaming LLM response.

        Yields StreamEvents as content chunks arrive, then MessageEvent for full response.
        Falls back to non-streaming if LLM doesn't support streaming.

        Args:
            request: The user request
            format: Optional response format

        Yields:
            StreamEvent for each content chunk, then MessageEvent with full content
        """
        # Add request to memory
        await self._add_to_memory([{"role": "user", "content": request}])
        await self._ensure_within_token_limit()

        # Check if LLM supports streaming
        if not hasattr(self.llm, 'ask_stream'):
            # Fall back to non-streaming
            response = await self.ask(request, format)
            yield MessageEvent(message=response.get("content", ""))
            return

        response_format = {"type": format} if format else None
        full_content = ""

        try:
            async for chunk in self.llm.ask_stream(
                self.memory.get_messages(),
                tools=None,  # Streaming typically used without tools
                response_format=response_format
            ):
                full_content += chunk
                yield StreamEvent(content=chunk, is_final=False)

            # Yield final stream event and message
            yield StreamEvent(content="", is_final=True)

            # Save response to memory
            await self._add_to_memory([{"role": "assistant", "content": full_content}])

            yield MessageEvent(message=full_content)

        except Exception as e:
            logger.error(f"Streaming failed: {e}")
            # Fall back to non-streaming on error
            response = await self.ask_with_messages([], format)
            yield MessageEvent(message=response.get("content", ""))
