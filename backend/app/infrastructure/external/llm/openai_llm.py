import asyncio
import contextlib
import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any, TypeVar

from openai import AsyncOpenAI, RateLimitError
from pydantic import BaseModel

from app.core.config import get_settings
from app.domain.external.llm import LLM
from app.domain.services.agents.error_handler import TokenLimitExceededError
from app.domain.services.agents.prompt_cache_manager import get_prompt_cache_manager
from app.domain.services.agents.token_manager import TokenManager
from app.domain.services.agents.usage_context import get_usage_context
from app.infrastructure.external.llm.factory import LLMProviderRegistry

T = TypeVar("T", bound=BaseModel)


logger = logging.getLogger(__name__)


@LLMProviderRegistry.register("openai")
class OpenAILLM(LLM):
    def __init__(self):
        settings = get_settings()

        # Detect if using Kimi Code API and add required headers
        default_headers = None
        if settings.api_base and "kimi.com" in settings.api_base:
            # Kimi Code API requires User-Agent from recognized coding agents
            default_headers = {
                "User-Agent": "claude-code/1.0",
                "X-Client-Name": "claude-code",
            }
            logger.info("Detected Kimi Code API, adding required headers")

        self.client = AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.api_base,
            default_headers=default_headers,
        )

        self._model_name = settings.model_name
        self._temperature = settings.temperature
        self._max_tokens = settings.max_tokens
        self._api_base = settings.api_base
        self._supports_stream_usage = self._detect_stream_usage_support()
        self._last_stream_metadata: dict[str, Any] | None = None

        # Detect if using local MLX server (doesn't support native tool calling)
        self._is_mlx_mode = self._detect_mlx_mode()

        # Detect if using Kimi Code API or similar with extended thinking enabled
        self._is_thinking_api = self._detect_thinking_api()

        # Initialize prompt cache manager for KV-cache optimization
        self._cache_manager = get_prompt_cache_manager(self._model_name)

        logger.info(
            f"Initialized OpenAI LLM with model: {self._model_name}, "
            f"MLX mode: {self._is_mlx_mode}, thinking API: {self._is_thinking_api}"
        )

    def _detect_stream_usage_support(self) -> bool:
        """Detect whether streaming usage metadata is supported by the API base."""
        base = (self._api_base or "").lower()
        return "openai.com" in base

    def _detect_mlx_mode(self) -> bool:
        """Detect if using local MLX server that needs text-based tool handling."""
        # Check model name for MLX community models
        if "mlx-community" in self._model_name.lower():
            return True
        # Check API base for local servers
        if self._api_base:
            local_indicators = ["localhost", "127.0.0.1", "host.docker.internal", ":8081"]
            if any(indicator in self._api_base.lower() for indicator in local_indicators):
                return True
        return False

    def _detect_thinking_api(self) -> bool:
        """Detect if using an API with extended thinking that requires reasoning_content handling.

        APIs like Kimi Code API enable extended thinking by default for Claude models.
        When replaying messages, reasoning_content must be preserved or stripped.
        """
        if not self._api_base:
            return False

        base = self._api_base.lower()

        # Kimi Code API has extended thinking enabled for Claude models
        if "kimi.com" in base or "kimi.ai" in base:
            return True

        # Check for Claude models that might have thinking enabled
        # Claude models through third-party APIs may have thinking enabled
        # Be conservative and enable thinking handling for all Claude models
        # through non-Anthropic endpoints
        model_lower = self._model_name.lower()
        return "claude" in model_lower and "anthropic.com" not in base

    async def _record_usage(self, response: Any) -> None:
        """Record usage from OpenAI response if usage context is set.

        Args:
            response: OpenAI API response containing usage info
        """
        ctx = get_usage_context()
        if not ctx:
            return

        try:
            # Extract usage from OpenAI response
            usage = getattr(response, "usage", None)
            if not usage:
                return

            prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
            completion_tokens = getattr(usage, "completion_tokens", 0) or 0

            # OpenAI uses prompt_tokens_details for cached tokens
            prompt_details = getattr(usage, "prompt_tokens_details", None)
            cached_tokens = 0
            if prompt_details:
                cached_tokens = getattr(prompt_details, "cached_tokens", 0) or 0

            # Lazy import to avoid circular dependency
            from app.application.services.usage_service import get_usage_service

            usage_service = get_usage_service()

            await usage_service.record_llm_usage(
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                model=ctx.model_override or self._model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
            )
        except Exception as e:
            logger.warning(f"Failed to record usage: {type(e).__name__}: {e}")

    async def _record_usage_counts(
        self,
        prompt_tokens: int,
        completion_tokens: int,
        cached_tokens: int = 0,
        model_override: str | None = None,
    ) -> None:
        """Record usage from explicit token counts."""
        ctx = get_usage_context()
        if not ctx:
            return

        try:
            from app.application.services.usage_service import get_usage_service

            usage_service = get_usage_service()
            model_name = model_override or ctx.model_override or self._model_name
            await usage_service.record_llm_usage(
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                model=model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=cached_tokens,
            )
        except Exception as e:
            logger.warning(f"Failed to record usage counts: {type(e).__name__}: {e}")

    async def _record_stream_usage(
        self,
        messages: list[dict[str, Any]],
        completion_text: str,
        tools: list[dict[str, Any]] | None = None,
    ) -> None:
        """Record usage for streaming responses using token estimation."""
        ctx = get_usage_context()
        if not ctx:
            return

        try:
            token_manager = TokenManager(ctx.model_override or self._model_name)
            prompt_tokens = token_manager.count_messages_tokens(messages)
            if tools:
                prompt_tokens += token_manager.count_tokens(json.dumps(tools))
            completion_tokens = token_manager.count_tokens(completion_text)

            await self._record_usage_counts(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=0,
            )
        except Exception as e:
            logger.warning(f"Failed to record streaming usage: {e}")

    def _tools_to_text(self, tools: list[dict[str, Any]]) -> str:
        """Convert OpenAI tools format to text description for MLX models."""
        if not tools:
            return ""

        tool_descriptions = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                name = func.get("name", "unknown")
                desc = func.get("description", "No description")
                params = func.get("parameters", {})

                # Format parameters
                param_str = ""
                if params.get("properties"):
                    param_parts = []
                    required = params.get("required", [])
                    for param_name, param_info in params["properties"].items():
                        param_type = param_info.get("type", "any")
                        param_desc = param_info.get("description", "")
                        is_required = param_name in required
                        req_marker = " (required)" if is_required else " (optional)"
                        param_parts.append(f"    - {param_name}: {param_type}{req_marker} - {param_desc}")
                    param_str = "\n" + "\n".join(param_parts)

                tool_descriptions.append(f"- **{name}**: {desc}{param_str}")

        return "\n".join(tool_descriptions)

    def _inject_tools_into_messages(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        """Inject tool definitions into the system prompt for MLX mode."""
        if not tools:
            return messages

        tools_text = self._tools_to_text(tools)
        tool_instruction = f"""
<available_tools>
You have access to the following tools. You MUST use these tools to complete tasks.

## CRITICAL RULES FOR TOOL CALLING:

1. **EVERY ACTION REQUIRES A TOOL CALL** - You cannot complete ANY task without calling tools.
   - To search the web: CALL info_search_web
   - To browse a website: CALL browser_agent_* tools
   - To write a file: CALL file_write
   - To read a file: CALL file_read
   - Describing an action is NOT the same as doing it!

2. **EXACT FORMAT REQUIRED** - To call a tool, output ONLY this JSON:
```json
{{"tool_call": {{"name": "TOOL_NAME", "arguments": {{"param1": "value1", "param2": "value2"}}}}}}
```

3. **ONE TOOL CALL PER RESPONSE** - Call one tool, wait for result, then call next tool.

4. **DO NOT SKIP TOOLS** - If a step requires writing a file, you MUST call file_write.
   Simply stating "I will write the file" does NOT write the file!

## EXAMPLES:

To search the web:
```json
{{"tool_call": {{"name": "info_search_web", "arguments": {{"query": "best mechanical keyboards 2025", "date_range": "past_year"}}}}}}
```

To write a markdown report:
```json
{{"tool_call": {{"name": "file_write", "arguments": {{"path": "/home/ubuntu/report.md", "content": "# Report Title\\n\\nContent here..."}}}}}}
```

To extract data from a webpage:
```json
{{"tool_call": {{"name": "browser_agent_extract", "arguments": {{"url": "https://example.com", "data_description": "product specifications"}}}}}}
```

## AVAILABLE TOOLS:
{tools_text}
</available_tools>

**REMEMBER: Output ONLY the JSON tool_call object when using a tool. No explanation before or after.**

/no_think
"""

        # Make a copy of messages
        new_messages = []
        system_found = False

        for msg in messages:
            msg_copy = dict(msg)
            if msg_copy.get("role") == "system":
                # Append tool instructions to system message
                msg_copy["content"] = msg_copy.get("content", "") + "\n\n" + tool_instruction
                system_found = True
            new_messages.append(msg_copy)

        # If no system message, add one
        if not system_found:
            new_messages.insert(0, {"role": "system", "content": tool_instruction})

        return new_messages

    def _convert_messages_for_mlx(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Convert messages with tool_calls to plain text format for MLX."""
        converted = []
        for msg in messages:
            msg_copy = dict(msg)
            role = msg_copy.get("role", "")

            # Convert assistant messages with tool_calls to plain text
            if role == "assistant" and msg_copy.get("tool_calls"):
                tool_calls = msg_copy.pop("tool_calls", [])
                content = msg_copy.get("content") or ""

                # Convert tool calls to JSON text
                for tc in tool_calls:
                    func = tc.get("function", {})
                    tool_json = {
                        "tool_call": {
                            "name": func.get("name"),
                            "arguments": json.loads(func.get("arguments", "{}"))
                            if isinstance(func.get("arguments"), str)
                            else func.get("arguments", {}),
                        }
                    }
                    content += f"\n```json\n{json.dumps(tool_json, indent=2)}\n```"

                msg_copy["content"] = content.strip() or "I'll use a tool."

            # Convert tool response messages to user messages
            elif role == "tool":
                tool_content = msg_copy.get("content", "")
                tool_name = msg_copy.get("name", "tool")
                msg_copy = {"role": "user", "content": f"[Tool Result from {tool_name}]:\n{tool_content}"}

            # Ensure content is always a string (not None)
            if msg_copy.get("content") is None:
                msg_copy["content"] = ""

            converted.append(msg_copy)

        return converted

    def _parse_tool_call_from_text(self, content: str) -> dict[str, Any] | None:
        """Parse tool call from text response for MLX mode."""
        if not content:
            return None

        # Try to find JSON tool_call in the response
        # Pattern 1 & 2: Code blocks (reliable delimiters)
        patterns = [
            r'```json\s*(\{.*?"tool_call".*?\})\s*```',  # Markdown code block
            r'```\s*(\{.*?"tool_call".*?\})\s*```',  # Generic code block
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            for match in matches:
                result = self._try_parse_tool_call_json(match)
                if result:
                    return result

        # Pattern 3: Balanced brace extraction for inline JSON (handles nested braces)
        result = self._extract_balanced_json_tool_call(content)
        if result:
            return result

        return None

    def _try_parse_tool_call_json(self, text: str) -> dict[str, Any] | None:
        """Try to parse a tool_call JSON string into a tool call dict."""
        try:
            data = json.loads(text)
            if "tool_call" in data:
                tc = data["tool_call"]
                return {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": f"call_{uuid.uuid4().hex[:8]}",
                            "type": "function",
                            "function": {
                                "name": tc.get("name"),
                                "arguments": json.dumps(tc.get("arguments", {})),
                            },
                        }
                    ],
                }
        except (json.JSONDecodeError, TypeError, AttributeError):
            pass
        return None

    def _extract_balanced_json_tool_call(self, content: str) -> dict[str, Any] | None:
        """Extract tool_call JSON using balanced brace matching (handles nested objects)."""
        search_start = 0
        while True:
            idx = content.find('"tool_call"', search_start)
            if idx == -1:
                break
            # Walk backwards to find opening brace
            brace_start = content.rfind("{", 0, idx)
            if brace_start == -1:
                search_start = idx + 1
                continue
            # Walk forward with brace counting
            depth = 0
            for i in range(brace_start, len(content)):
                if content[i] == "{":
                    depth += 1
                elif content[i] == "}":
                    depth -= 1
                    if depth == 0:
                        candidate = content[brace_start : i + 1]
                        result = self._try_parse_tool_call_json(candidate)
                        if result:
                            return result
                        break
            search_start = idx + 1
        return None

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    @property
    def last_stream_metadata(self) -> dict[str, Any] | None:
        return self._last_stream_metadata

    def _strip_reasoning_content(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Strip reasoning_content from assistant messages to avoid thinking API errors.

        When APIs like Kimi have extended thinking enabled, they expect reasoning_content
        in all assistant messages with tool_calls. Since we don't preserve reasoning_content
        in our message history, we need to strip any existing reasoning_content fields
        to avoid validation errors.

        This is necessary because:
        1. The API returns messages with reasoning_content when thinking is enabled
        2. We store messages without reasoning_content (it's internal to the model)
        3. When replaying, the API sees messages that should have thinking but don't
        4. This causes: "thinking is enabled but reasoning_content is missing"
        """
        if not self._is_thinking_api:
            return messages

        cleaned = []
        for msg in messages:
            msg_copy = dict(msg)

            # Remove reasoning_content if present (we don't preserve it)
            msg_copy.pop("reasoning_content", None)

            # For assistant messages with tool_calls, ensure content is present
            # Some APIs expect content to be present even if empty
            if msg_copy.get("role") == "assistant" and msg_copy.get("tool_calls") and msg_copy.get("content") is None:
                msg_copy["content"] = ""

            cleaned.append(msg_copy)

        return cleaned

    def _sanitize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sanitize messages for strict OpenAI-compatible APIs (Zhipu GLM, OpenRouter, etc.).

        Many OpenAI-compatible APIs are stricter than OpenAI itself about message schema.
        This method ensures all messages conform to the strictest common denominator:

        1. Role normalization — 'developer' role converted to 'system' (GLM only accepts
           system/user/assistant/tool)
        2. Content is always a string (never None/null) — GLM rejects null content
        3. Non-standard fields are removed (only role, content, tool_calls, tool_call_id,
           name allowed)
        4. Tool response messages use standard 'name' field (not 'function_name')
        5. tool_calls entries have valid structure with required 'type' field
        6. Empty messages are dropped to prevent "content cannot be empty" errors
        """
        # Standard fields per role (OpenAI Chat Completions API spec)
        _standard_fields = {
            "system": {"role", "content", "name"},
            "user": {"role", "content", "name"},
            "assistant": {"role", "content", "tool_calls", "name", "refusal"},
            "tool": {"role", "content", "tool_call_id", "name"},
        }

        sanitized = []
        for msg in messages:
            msg_copy = dict(msg)
            # Deep-copy tool_calls to avoid mutating originals
            if "tool_calls" in msg_copy and isinstance(msg_copy["tool_calls"], list):
                msg_copy["tool_calls"] = [
                    {**tc, "function": dict(tc["function"])}
                    if isinstance(tc, dict) and "function" in tc
                    else dict(tc)
                    if isinstance(tc, dict)
                    else tc
                    for tc in msg_copy["tool_calls"]
                ]
            role = msg_copy.get("role", "user")

            # 1. Normalize roles for strict APIs
            # GLM and similar only accept: system, user, assistant, tool
            if role == "developer":
                msg_copy["role"] = "system"
                role = "system"

            # 2. Ensure content is always a string (never None)
            content = msg_copy.get("content")
            if content is None:
                msg_copy["content"] = ""

            # 3. Convert non-standard 'function_name' to standard 'name' for tool messages
            if role == "tool" and "function_name" in msg_copy:
                if "name" not in msg_copy:
                    msg_copy["name"] = msg_copy["function_name"]
                del msg_copy["function_name"]

            # 4. Remove non-standard fields that strict APIs reject
            allowed = _standard_fields.get(role, {"role", "content"})
            # Keep internal fields prefixed with '_' (like _finish_reason) — stripped by SDK
            extra_keys = {k for k in msg_copy if k not in allowed and not k.startswith("_")}
            for key in extra_keys:
                del msg_copy[key]

            # 5a. Ensure required fields for tool messages (GLM strict schema)
            # After field removal, tool messages MUST have name and tool_call_id
            if role == "tool":
                if not msg_copy.get("name"):
                    msg_copy["name"] = "unknown_tool"
                else:
                    msg_copy["name"] = str(msg_copy["name"])
                if not msg_copy.get("tool_call_id"):
                    msg_copy["tool_call_id"] = f"call_{uuid.uuid4().hex[:8]}"
                else:
                    msg_copy["tool_call_id"] = str(msg_copy["tool_call_id"])

            # 5b. Validate tool_calls structure if present
            if msg_copy.get("tool_calls"):
                valid_calls = []
                for tc in msg_copy["tool_calls"]:
                    if isinstance(tc, dict) and tc.get("function"):
                        # Ensure all required fields exist (GLM rejects empty type)
                        tc.setdefault("id", f"call_{uuid.uuid4().hex[:8]}")
                        tc.setdefault("type", "function")
                        func = tc["function"]
                        func.setdefault("name", "unknown")
                        if func.get("arguments") is None:
                            func["arguments"] = "{}"
                        elif not isinstance(func["arguments"], str):
                            func["arguments"] = json.dumps(func["arguments"])
                        valid_calls.append(tc)
                if valid_calls:
                    msg_copy["tool_calls"] = valid_calls
                else:
                    # Remove tool_calls entirely if empty (some APIs reject null/empty)
                    msg_copy.pop("tool_calls", None)

            sanitized.append(msg_copy)

        return sanitized

    @staticmethod
    def _tool_calls_to_text(tool_calls: list[dict[str, Any]]) -> str:
        """Convert tool_calls to a text description for context preservation.

        When orphaned assistant messages with tool_calls must be cleaned up,
        this preserves the context of what was attempted rather than discarding
        the entire message.
        """
        parts = []
        for tc in tool_calls:
            func = tc.get("function", {})
            name = func.get("name", "unknown")
            args_str = func.get("arguments", "{}")
            # Truncate large arguments for readability
            if len(args_str) > 200:
                args_str = args_str[:200] + "..."
            parts.append(f"[Attempted to call {name} with {args_str}]")
        return "\n".join(parts)

    def _convert_orphaned_assistant(self, msg: dict[str, Any]) -> dict[str, Any]:
        """Convert an orphaned assistant message with tool_calls into a text-only message.

        Preserves the content and a text description of the attempted tool calls
        so the LLM retains context about what was tried.
        """
        tool_calls = msg.get("tool_calls", [])
        original_content = msg.get("content") or ""
        tool_text = self._tool_calls_to_text(tool_calls)

        combined = f"{original_content}\n{tool_text}".strip() if original_content else tool_text

        converted = dict(msg)
        converted.pop("tool_calls", None)
        converted["content"] = combined
        return converted

    def _validate_and_fix_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Validate message sequence and fix tool_call/tool_response ordering issues.

        Ensures every assistant message with tool_calls is followed by the
        corresponding tool responses before any other message type.

        Orphaned assistant messages (with tool_calls but no matching tool responses)
        are converted to text-only messages preserving context about what was attempted,
        rather than being removed entirely.
        """
        if not messages:
            return messages

        # First, strip reasoning_content for thinking APIs
        messages = self._strip_reasoning_content(messages)

        # Sanitize all messages for strict API compatibility
        messages = self._sanitize_messages(messages)

        fixed_messages = []
        pending_tool_ids = set()

        for _i, msg in enumerate(messages):
            role = msg.get("role", "")

            # Check if this is an assistant message with tool_calls
            if role == "assistant" and msg.get("tool_calls"):
                # If we have pending tool_ids from a previous assistant message,
                # that means we never got responses — convert to text to preserve context
                if pending_tool_ids:
                    logger.warning(
                        f"Converting orphaned assistant message with unfulfilled tool_calls: {pending_tool_ids}"
                    )
                    # Find and convert the last assistant message with tool_calls
                    for j in range(len(fixed_messages) - 1, -1, -1):
                        if fixed_messages[j].get("role") == "assistant" and fixed_messages[j].get("tool_calls"):
                            fixed_messages[j] = self._convert_orphaned_assistant(fixed_messages[j])
                            break
                    pending_tool_ids = set()

                # Track the new tool_call_ids
                pending_tool_ids = {tc.get("id") for tc in msg.get("tool_calls", []) if tc.get("id")}
                fixed_messages.append(msg)

            elif role == "tool":
                tool_call_id = msg.get("tool_call_id")
                if tool_call_id in pending_tool_ids:
                    pending_tool_ids.discard(tool_call_id)
                    fixed_messages.append(msg)
                elif not pending_tool_ids:
                    # Orphaned tool response - skip it
                    logger.warning(f"Removing orphaned tool response with id: {tool_call_id}")
                else:
                    # Drop mismatched tool responses while a specific sequence is pending.
                    # Keeping them can create orphan tool messages and break strict APIs.
                    logger.warning(
                        "Dropping mismatched tool response with id %s while pending ids are %s",
                        tool_call_id,
                        sorted(pending_tool_ids),
                    )

            else:
                # Regular message (user/system/assistant without tool_calls)
                if pending_tool_ids:
                    # Incomplete tool sequence — convert assistant to text instead of removing
                    logger.warning("Incomplete tool sequence detected, converting assistant message to text")
                    for j in range(len(fixed_messages) - 1, -1, -1):
                        if fixed_messages[j].get("role") == "assistant" and fixed_messages[j].get("tool_calls"):
                            fixed_messages[j] = self._convert_orphaned_assistant(fixed_messages[j])
                            break
                    # Also remove any orphaned tool responses after the converted assistant
                    pending_tool_ids = set()

                fixed_messages.append(msg)

        # Handle trailing incomplete tool sequence
        if pending_tool_ids:
            logger.warning("Trailing incomplete tool sequence, converting last assistant message to text")
            for j in range(len(fixed_messages) - 1, -1, -1):
                if fixed_messages[j].get("role") == "assistant" and fixed_messages[j].get("tool_calls"):
                    fixed_messages[j] = self._convert_orphaned_assistant(fixed_messages[j])
                    break

        if len(fixed_messages) != len(messages):
            logger.info(f"Fixed message sequence: {len(messages)} -> {len(fixed_messages)} messages")

        return fixed_messages

    async def ask(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        tool_choice: str | None = None,
        enable_caching: bool = True,
    ) -> dict[str, Any]:
        """Send chat request to OpenAI API with retry mechanism and caching support.

        For MLX models (local server), tools are converted to text-based format
        since MLX doesn't support OpenAI's native tool calling API.
        """
        # Validate and fix message sequence before sending
        messages = self._validate_and_fix_messages(messages)

        # MLX mode: convert tools to text-based format
        original_tools = tools
        if self._is_mlx_mode and tools:
            logger.info(f"MLX mode: Converting {len(tools)} tools to text-based format")
            messages = self._convert_messages_for_mlx(messages)
            messages = self._inject_tools_into_messages(messages, tools)
            tools = None  # Don't pass tools parameter to MLX

        # Apply cache optimization for message structure
        if enable_caching and self._cache_manager:
            messages = self._cache_manager.prepare_messages_for_caching(messages)

        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries + 1):  # every try
            response = None
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))  # back off
                    logger.info(f"Retrying API request (attempt {attempt + 1}/{max_retries + 1}) after {delay}s delay")
                    await asyncio.sleep(delay)

                # GPT-5 nano/mini and o1/o3 models have different parameter requirements
                is_new_model = self._model_name.startswith(("gpt-5", "o1", "o3"))

                # Build parameters based on model type
                params = {
                    "model": self._model_name,
                    "messages": messages,
                }

                if is_new_model:
                    # GPT-5+ models use max_completion_tokens and don't support custom temperature
                    params["max_completion_tokens"] = self._max_tokens
                else:
                    # Older models use max_tokens and support temperature
                    params["max_tokens"] = self._max_tokens
                    params["temperature"] = self._temperature

                # For thinking APIs (Kimi, etc.), explicitly disable extended thinking
                # to avoid reasoning_content errors when replaying messages
                if self._is_thinking_api:
                    params["extra_body"] = {"thinking": {"type": "disabled"}}

                if tools:
                    # OpenAI API mode with native tool support
                    logger.debug(f"Sending request with tools, model: {self._model_name}, attempt: {attempt + 1}")
                    # Some providers (DeepSeek, etc.) don't support response_format with tools
                    # Only pass response_format for official OpenAI endpoints
                    use_response_format = response_format if self._supports_response_format_with_tools() else None
                    response = await self.client.chat.completions.create(
                        **params,
                        tools=tools,
                        response_format=use_response_format,
                        tool_choice=tool_choice,
                        parallel_tool_calls=self._supports_parallel_tool_calls(),
                    )
                else:
                    # MLX mode or no tools
                    logger.debug(
                        f"Sending request without native tools, model: {self._model_name}, MLX mode: {self._is_mlx_mode}, attempt: {attempt + 1}"
                    )
                    response = await self.client.chat.completions.create(
                        **params,
                        response_format=response_format if not self._is_mlx_mode else None,
                    )

                logger.debug(f"Response from API: {response.model_dump()}")

                if not response or not response.choices:
                    error_msg = f"API returned invalid response (no choices) on attempt {attempt + 1}"
                    logger.error(error_msg)
                    if attempt == max_retries:
                        raise ValueError(f"Failed after {max_retries + 1} attempts: {error_msg}")
                    continue

                # Track usage if context is set
                await self._record_usage(response)

                result = response.choices[0].message.model_dump()

                # Check finish_reason for truncation detection
                finish_reason = response.choices[0].finish_reason
                if finish_reason == "length":
                    logger.warning(f"LLM response truncated (finish_reason=length, max_tokens={self._max_tokens})")
                    result["_finish_reason"] = "length"
                elif finish_reason not in ("stop", "end_turn", "tool_calls"):
                    logger.debug(f"LLM finish_reason: {finish_reason}")

                # MLX mode: parse tool calls from text response
                if self._is_mlx_mode and original_tools:
                    content = result.get("content", "")
                    parsed_tool_call = self._parse_tool_call_from_text(content)
                    if parsed_tool_call:
                        logger.info("MLX mode: Parsed tool call from text response")
                        return parsed_tool_call

                return result

            except RateLimitError as e:
                retry_after = None
                if hasattr(e, "response") and e.response is not None:
                    retry_after_header = e.response.headers.get("Retry-After") or e.response.headers.get("retry-after")
                    if retry_after_header:
                        with contextlib.suppress(ValueError, TypeError):
                            retry_after = float(retry_after_header)
                if retry_after is None:
                    retry_after = min(base_delay * (2**attempt), 60.0)
                logger.warning(
                    f"OpenAI rate limit hit on attempt {attempt + 1}/{max_retries + 1}, "
                    f"retrying after {retry_after:.1f}s"
                )
                if attempt == max_retries:
                    raise
                await asyncio.sleep(retry_after)
                continue

            except Exception as e:
                error_msg = str(e).lower()

                # Check for MLX-specific content type error
                if "only 'text' content type is supported" in error_msg:
                    logger.warning("MLX content type error detected, enabling MLX mode for retry")
                    self._is_mlx_mode = True
                    if original_tools:
                        messages = self._convert_messages_for_mlx(messages)
                        messages = self._inject_tools_into_messages(messages, original_tools)
                        tools = None
                    continue

                # Check for token limit errors and raise specific exception
                if any(
                    term in error_msg
                    for term in [
                        "context_length_exceeded",
                        "maximum context length",
                        "too many tokens",
                        "max_tokens",
                        "context window",
                    ]
                ):
                    logger.warning(f"Token limit exceeded: {e}")
                    raise TokenLimitExceededError(str(e)) from e

                # Detect message validation errors from strict APIs (Zhipu GLM error 1214, etc.)
                # These indicate message schema issues that won't resolve on retry
                if any(
                    term in error_msg
                    for term in [
                        "'1214'",  # Zhipu GLM invalid parameter error code
                        "invalid messages",
                        "message format",
                        "invalid_request_error",
                        "incorrect role",  # Zhipu GLM role validation
                        "cannot be empty",  # Zhipu GLM empty content
                        "parameter is illegal",  # Zhipu GLM translated error
                    ]
                ):
                    logger.error(
                        f"API message validation error (likely strict schema): {e!s}. "
                        f"Messages were sanitized but API still rejected them."
                    )
                    # Don't retry — message schema errors won't fix themselves
                    raise

                error_log = f"Error calling API on attempt {attempt + 1}: {e!s}"
                logger.error(error_log)
                if attempt == max_retries:
                    raise e
                continue
        # This should never be reached - all paths should either return or raise
        raise ValueError(f"LLM request failed after {max_retries + 1} attempts with no response")

    @staticmethod
    def _extract_json_from_text(text: str) -> str | None:
        """Extract outermost JSON object from text using balanced-brace matching.

        Useful when the LLM returns JSON embedded in prose or thinking content.

        Args:
            text: Text that may contain a JSON object

        Returns:
            Extracted JSON string, or None if no valid JSON found
        """
        # Find the first '{' that could start a JSON object
        start = text.find("{")
        if start == -1:
            return None

        depth = 0
        in_string = False
        escape_next = False

        for i in range(start, len(text)):
            ch = text[i]

            if escape_next:
                escape_next = False
                continue

            if ch == "\\":
                if in_string:
                    escape_next = True
                continue

            if ch == '"' and not escape_next:
                in_string = not in_string
                continue

            if in_string:
                continue

            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start : i + 1]
                    # Validate it's actually parseable JSON
                    try:
                        json.loads(candidate)
                        return candidate
                    except json.JSONDecodeError:
                        # Try next opening brace
                        next_start = text.find("{", start + 1)
                        if next_start == -1:
                            return None
                        start = next_start
                        depth = 0
                        # Reset and continue from new start
                        continue

        return None

    def get_cache_metrics(self) -> dict[str, Any]:
        """Get prompt caching performance metrics"""
        if self._cache_manager:
            return self._cache_manager.get_metrics()
        return {}

    async def ask_structured(
        self,
        messages: list[dict[str, str]],
        response_model: type[T],
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        enable_caching: bool = True,
    ) -> T:
        """Send chat request with structured output validation.

        Uses OpenAI's native JSON schema support for type-safe responses.
        Falls back to json_object mode + Pydantic validation for compatibility.

        Args:
            messages: List of messages
            response_model: Pydantic model class for response validation
            tools: Optional tools (usually None for structured output)
            tool_choice: Optional tool choice
            enable_caching: Whether to use prompt caching

        Returns:
            Validated Pydantic model instance
        """
        # Validate and fix message sequence
        messages = self._validate_and_fix_messages(messages)

        # Apply cache optimization
        if enable_caching and self._cache_manager:
            messages = self._cache_manager.prepare_messages_for_caching(messages)

        # Build JSON schema from Pydantic model
        schema = response_model.model_json_schema()

        # Detect if model supports native structured outputs (GPT-4o+, GPT-5+)
        supports_strict_schema = self._supports_structured_output()

        max_retries = 3
        base_delay = 1.0
        # Flag to control thinking API behavior across retries.
        # Starts True for thinking APIs; set to False if empty response
        # indicates the model needs thinking enabled to produce output.
        disable_thinking = self._is_thinking_api

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.info(f"Retrying structured request (attempt {attempt + 1}/{max_retries + 1})")
                    await asyncio.sleep(delay)

                is_new_model = self._model_name.startswith(("gpt-5", "o1", "o3"))
                params = {
                    "model": self._model_name,
                    "messages": messages,
                }

                if is_new_model:
                    params["max_completion_tokens"] = self._max_tokens
                else:
                    params["max_tokens"] = self._max_tokens
                    params["temperature"] = self._temperature

                # For thinking APIs (Kimi, etc.), disable extended thinking unless
                # a previous empty response indicated thinking is needed for output
                if disable_thinking:
                    params["extra_body"] = {"thinking": {"type": "disabled"}}

                if supports_strict_schema:
                    # Use native structured output with strict schema
                    params["response_format"] = {
                        "type": "json_schema",
                        "json_schema": {"name": response_model.__name__, "strict": True, "schema": schema},
                    }
                elif self._supports_json_object_format():
                    # Use json_object if provider supports it
                    params["response_format"] = {"type": "json_object"}
                    logger.debug("Using json_object response format")
                else:
                    # Provider doesn't support json_object - use prompt-based JSON
                    logger.info(
                        f"Provider doesn't support json_object format, using prompt-based JSON for {self._model_name}"
                    )
                    json_instruction = (
                        "\n\nCRITICAL: You must respond with valid JSON matching this schema:\n"
                        f"{json.dumps(schema, indent=2)}\n\n"
                        "Respond with ONLY the JSON object, no other text or explanation."
                    )
                    # Add instruction to system message or create one
                    if params["messages"] and params["messages"][0]["role"] == "system":
                        params["messages"][0]["content"] += json_instruction
                    else:
                        params["messages"].insert(0, {"role": "system", "content": json_instruction})

                if tools:
                    params["tools"] = tools
                    params["tool_choice"] = tool_choice
                    params["parallel_tool_calls"] = False

                response = await self.client.chat.completions.create(**params)

                # Record usage for structured requests
                await self._record_usage(response)

                if not response or not response.choices:
                    if attempt == max_retries:
                        raise ValueError("API returned invalid response")
                    continue

                message = response.choices[0].message
                content = message.content

                # For reasoning models (Kimi Code, o1, etc.), check reasoning_content if content is empty
                if not content and hasattr(message, "reasoning_content") and message.reasoning_content:
                    logger.info("Using reasoning_content as fallback for empty content field")
                    content = message.reasoning_content

                # Check for truncation before parsing
                finish_reason = response.choices[0].finish_reason
                if finish_reason == "length":
                    logger.warning("Structured output truncated (finish_reason=length), retrying")
                    if attempt == max_retries:
                        raise ValueError("Structured output truncated after all retries")
                    continue

                if not content:
                    # For thinking APIs: empty content with thinking disabled means
                    # the model's primary output mechanism was suppressed. Retry with
                    # thinking enabled and extract JSON from reasoning output.
                    if disable_thinking:
                        logger.warning(
                            "Thinking API returned empty content with thinking disabled — "
                            "retrying with thinking enabled"
                        )
                        disable_thinking = False
                        continue
                    if attempt == max_retries:
                        raise ValueError("Empty response content")
                    continue

                # Parse and validate with Pydantic
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    # Try balanced-brace extraction for JSON embedded in prose/thinking
                    extracted = self._extract_json_from_text(content)
                    if extracted:
                        logger.info("Extracted JSON from prose via balanced-brace matching")
                        parsed = json.loads(extracted)
                    else:
                        raise
                return response_model.model_validate(parsed)

            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error on attempt {attempt + 1}: {e}")
                if attempt == max_retries:
                    raise ValueError(f"Failed to parse JSON response: {e}") from e
            except RateLimitError as e:
                retry_after = None
                if hasattr(e, "response") and e.response is not None:
                    retry_after_header = e.response.headers.get("Retry-After") or e.response.headers.get("retry-after")
                    if retry_after_header:
                        with contextlib.suppress(ValueError, TypeError):
                            retry_after = float(retry_after_header)
                if retry_after is None:
                    retry_after = min(base_delay * (2**attempt), 60.0)
                logger.warning(
                    f"OpenAI rate limit hit on structured request attempt {attempt + 1}/{max_retries + 1}, "
                    f"retrying after {retry_after:.1f}s"
                )
                if attempt == max_retries:
                    raise
                await asyncio.sleep(retry_after)
            except Exception as e:
                error_msg = str(e).lower()
                if any(
                    term in error_msg
                    for term in [
                        "context_length_exceeded",
                        "maximum context length",
                        "too many tokens",
                        "max_tokens",
                        "context window",
                    ]
                ):
                    raise TokenLimitExceededError(str(e)) from e
                # Message validation errors won't fix on retry
                if any(
                    term in error_msg
                    for term in [
                        "'1214'",
                        "invalid messages",
                        "message format",
                        "invalid_request_error",
                        "incorrect role",
                        "cannot be empty",
                        "parameter is illegal",
                    ]
                ):
                    raise
                if attempt == max_retries:
                    raise
                logger.warning(f"Structured request failed on attempt {attempt + 1}: {e}")

        raise ValueError("Failed to get structured response after all retries")

    def _supports_structured_output(self) -> bool:
        """Check if the model supports native structured output with strict schemas."""
        # GPT-4o and later models support structured outputs
        # MLX and local models typically don't
        if self._is_mlx_mode:
            return False
        supported_prefixes = (
            "gpt-4o",
            "gpt-4-turbo",
            "gpt-5",
            "o1",
            "o3",  # Reasoning models
        )
        return self._model_name.startswith(supported_prefixes)

    def _supports_response_format_with_tools(self) -> bool:
        """Check if the provider supports response_format parameter with tools.

        Many OpenAI-compatible providers (DeepSeek, local servers, etc.) don't support
        response_format when tools are being used.

        Returns:
            True if response_format can be used with tools, False otherwise
        """
        # Only official OpenAI API supports response_format with tools
        if not self._api_base:
            return False

        # Check if using official OpenAI API
        base = self._api_base.lower()
        return "api.openai.com" in base or "openai.azure.com" in base

    def _supports_parallel_tool_calls(self) -> bool:
        """Check if the provider supports parallel tool calls."""
        if not self._api_base:
            return False
        base = self._api_base.lower()
        return "api.openai.com" in base or "openai.azure.com" in base

    def _supports_json_object_format(self) -> bool:
        """Check if provider supports json_object response format.

        Many OpenAI-compatible providers don't support json_object format:
        - DeepInfra with NVIDIA models
        - Most models on OpenRouter (except OpenAI/Anthropic/Google)
        - Local inference servers

        Returns:
            True if json_object format is supported, False otherwise
        """
        if not self._api_base:
            return True  # Default OpenAI supports it

        base = self._api_base.lower()

        # Official OpenAI API supports json_object
        if "api.openai.com" in base or "openai.azure.com" in base:
            return True

        # DeepInfra has limited json_object support
        # NVIDIA models on DeepInfra don't support it
        model_lower = self._model_name.lower()
        if "deepinfra" in base and ("nvidia" in model_lower or "nemotron" in model_lower):
            logger.debug(f"DeepInfra NVIDIA model {self._model_name} doesn't support json_object format")
            return False

        # Many OpenRouter providers don't support json_object
        if "openrouter" in base:
            # Only specific model families support it
            supported_prefixes = ("openai/", "anthropic/", "google/")
            if not self._model_name.startswith(supported_prefixes):
                logger.debug(f"OpenRouter model {self._model_name} doesn't support json_object format")
                return False

        # Conservative default for unknown providers
        return False

    async def ask_stream(
        self,
        messages: list[dict[str, str]],
        tools: list[dict[str, Any]] | None = None,
        response_format: dict[str, Any] | None = None,
        tool_choice: str | None = None,
        enable_caching: bool = True,
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from OpenAI API.

        Yields content chunks as they arrive for better perceived latency.

        Args:
            messages: List of messages
            tools: Optional tools for function calling
            response_format: Optional response format
            tool_choice: Optional tool choice
            enable_caching: Whether to use prompt caching

        Yields:
            Content chunks as strings
        """
        self._last_stream_metadata = None

        # Validate and fix message sequence
        messages = self._validate_and_fix_messages(messages)

        # MLX mode doesn't support streaming well, fall back to regular ask
        if self._is_mlx_mode:
            result = await self.ask(messages, tools, response_format, tool_choice, enable_caching)
            content = result.get("content", "")
            finish_reason = result.get("_finish_reason")
            self._last_stream_metadata = {
                "finish_reason": finish_reason or "stop",
                "truncated": finish_reason == "length",
                "provider": "openai",
            }
            if content:
                yield content
            return

        # Apply cache optimization
        if enable_caching and self._cache_manager:
            messages = self._cache_manager.prepare_messages_for_caching(messages)

        is_new_model = self._model_name.startswith(("gpt-5", "o1", "o3"))
        params = {
            "model": self._model_name,
            "messages": messages,
            "stream": True,
        }
        if self._supports_stream_usage:
            params["stream_options"] = {"include_usage": True}

        if is_new_model:
            params["max_completion_tokens"] = self._max_tokens
        else:
            params["max_tokens"] = self._max_tokens
            params["temperature"] = self._temperature

        # For thinking APIs (Kimi, etc.), explicitly disable extended thinking
        if self._is_thinking_api:
            params["extra_body"] = {"thinking": {"type": "disabled"}}

        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice
            params["parallel_tool_calls"] = False

        if response_format and not tools:
            params["response_format"] = response_format

        completion_parts: list[str] = []
        usage_counts: dict[str, int] | None = None
        finish_reason: str | None = None

        try:
            stream = await self.client.chat.completions.create(**params)

            async for chunk in stream:
                if getattr(chunk, "usage", None):
                    usage = chunk.usage
                    prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
                    completion_tokens = getattr(usage, "completion_tokens", 0) or 0
                    prompt_details = getattr(usage, "prompt_tokens_details", None)
                    cached_tokens = (getattr(prompt_details, "cached_tokens", 0) or 0) if prompt_details else 0
                    usage_counts = {
                        "prompt_tokens": prompt_tokens,
                        "completion_tokens": completion_tokens,
                        "cached_tokens": cached_tokens,
                    }
                if chunk.choices:
                    delta = chunk.choices[0].delta
                    if chunk.choices[0].finish_reason:
                        finish_reason = chunk.choices[0].finish_reason
                    if delta.content:
                        completion_parts.append(delta.content)
                        yield delta.content
                    if delta.tool_calls:
                        logger.warning(
                            "ask_stream received tool_call chunks — tool calls are not "
                            "supported in streaming mode. Use ask() for tool-calling requests."
                        )

            if usage_counts:
                await self._record_usage_counts(
                    prompt_tokens=usage_counts["prompt_tokens"],
                    completion_tokens=usage_counts["completion_tokens"],
                    cached_tokens=usage_counts["cached_tokens"],
                )
            else:
                await self._record_stream_usage(
                    messages,
                    "".join(completion_parts),
                    tools=tools,
                )

            normalized_finish_reason = finish_reason or "stop"
            self._last_stream_metadata = {
                "finish_reason": normalized_finish_reason,
                "truncated": normalized_finish_reason == "length",
                "provider": "openai",
            }
            if normalized_finish_reason == "length":
                logger.warning("OpenAI streaming response truncated (finish_reason=length)")

        except RateLimitError as e:
            self._last_stream_metadata = {
                "finish_reason": "error",
                "truncated": False,
                "provider": "openai",
                "error": "rate_limit",
            }
            retry_after = None
            if hasattr(e, "response") and e.response is not None:
                retry_after_header = e.response.headers.get("Retry-After") or e.response.headers.get("retry-after")
                if retry_after_header:
                    with contextlib.suppress(ValueError, TypeError):
                        retry_after = float(retry_after_header)
            if retry_after is None:
                retry_after = min(4.0, 60.0)  # Single retry for streaming
            logger.warning(f"OpenAI rate limit hit during streaming, retrying after {retry_after:.1f}s")
            await asyncio.sleep(retry_after)
            # Re-raise to let caller retry the entire stream
            raise
        except Exception as e:
            self._last_stream_metadata = {
                "finish_reason": "error",
                "truncated": False,
                "provider": "openai",
                "error": type(e).__name__,
            }
            error_msg = str(e).lower()
            if any(
                term in error_msg
                for term in [
                    "context_length_exceeded",
                    "maximum context length",
                    "too many tokens",
                    "max_tokens",
                    "context window",
                ]
            ):
                raise TokenLimitExceededError(str(e)) from e
            raise
