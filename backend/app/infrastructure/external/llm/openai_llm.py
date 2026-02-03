import asyncio
import json
import logging
import re
import uuid
from collections.abc import AsyncGenerator
from typing import Any, TypeVar

from openai import AsyncOpenAI
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
        self.client = AsyncOpenAI(api_key=settings.api_key, base_url=settings.api_base)

        self._model_name = settings.model_name
        self._temperature = settings.temperature
        self._max_tokens = settings.max_tokens
        self._api_base = settings.api_base
        self._supports_stream_usage = self._detect_stream_usage_support()

        # Detect if using local MLX server (doesn't support native tool calling)
        self._is_mlx_mode = self._detect_mlx_mode()

        # Initialize prompt cache manager for KV-cache optimization
        self._cache_manager = get_prompt_cache_manager(self._model_name)

        logger.info(f"Initialized OpenAI LLM with model: {self._model_name}, MLX mode: {self._is_mlx_mode}")

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
            logger.warning(f"Failed to record usage: {e}")

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
            logger.warning(f"Failed to record usage counts: {e}")

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
        patterns = [
            r'```json\s*(\{.*?"tool_call".*?\})\s*```',  # Markdown code block
            r'```\s*(\{.*?"tool_call".*?\})\s*```',  # Generic code block
            r'(\{[^{}]*"tool_call"[^{}]*\{[^{}]*\}[^{}]*\})',  # Inline JSON
        ]

        for pattern in patterns:
            matches = re.findall(pattern, content, re.DOTALL | re.IGNORECASE)
            for match in matches:
                try:
                    data = json.loads(match)
                    if "tool_call" in data:
                        tc = data["tool_call"]
                        return {
                            "role": "assistant",
                            "content": None,
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
                except json.JSONDecodeError:
                    continue

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

    def _validate_and_fix_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Validate message sequence and fix tool_call/tool_response ordering issues.

        Ensures every assistant message with tool_calls is followed by the
        corresponding tool responses before any other message type.
        """
        if not messages:
            return messages

        fixed_messages = []
        pending_tool_ids = set()

        for _i, msg in enumerate(messages):
            role = msg.get("role", "")

            # Check if this is an assistant message with tool_calls
            if role == "assistant" and msg.get("tool_calls"):
                # If we have pending tool_ids from a previous assistant message,
                # that means we never got responses - skip the orphaned message
                if pending_tool_ids:
                    logger.warning(
                        f"Removing orphaned assistant message with unfulfilled tool_calls: {pending_tool_ids}"
                    )
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
                    # Tool response for unknown id - still add it if we're expecting responses
                    fixed_messages.append(msg)

            else:
                # Regular message (user/system/assistant without tool_calls)
                if pending_tool_ids:
                    # We have an incomplete tool sequence - remove the assistant message
                    logger.warning("Incomplete tool sequence detected, removing last assistant message")
                    # Find and remove the last assistant message with tool_calls
                    for j in range(len(fixed_messages) - 1, -1, -1):
                        if fixed_messages[j].get("role") == "assistant" and fixed_messages[j].get("tool_calls"):
                            fixed_messages.pop(j)
                            break
                    pending_tool_ids = set()

                fixed_messages.append(msg)

        # Handle trailing incomplete tool sequence
        if pending_tool_ids:
            logger.warning("Trailing incomplete tool sequence, removing last assistant message")
            for j in range(len(fixed_messages) - 1, -1, -1):
                if fixed_messages[j].get("role") == "assistant" and fixed_messages[j].get("tool_calls"):
                    fixed_messages.pop(j)
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

                # MLX mode: parse tool calls from text response
                if self._is_mlx_mode and original_tools:
                    content = result.get("content", "")
                    parsed_tool_call = self._parse_tool_call_from_text(content)
                    if parsed_tool_call:
                        logger.info("MLX mode: Parsed tool call from text response")
                        return parsed_tool_call

                return result

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

                error_log = f"Error calling API on attempt {attempt + 1}: {e!s}"
                logger.error(error_log)
                if attempt == max_retries:
                    raise e
                continue
        # This should never be reached - all paths should either return or raise
        raise ValueError(f"LLM request failed after {max_retries + 1} attempts with no response")

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
                    logger.info(f"Provider doesn't support json_object format, using prompt-based JSON for {self._model_name}")
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

                if not response or not response.choices:
                    if attempt == max_retries:
                        raise ValueError("API returned invalid response")
                    continue

                content = response.choices[0].message.content
                if not content:
                    if attempt == max_retries:
                        raise ValueError("Empty response content")
                    continue

                # Parse and validate with Pydantic
                parsed = json.loads(content)
                return response_model.model_validate(parsed)

            except json.JSONDecodeError as e:
                logger.warning(f"JSON decode error on attempt {attempt + 1}: {e}")
                if attempt == max_retries:
                    raise ValueError(f"Failed to parse JSON response: {e}") from e
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
        if "deepinfra" in base:
            if "nvidia" in self._model_name.lower() or "nemotron" in self._model_name.lower():
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
        # Validate and fix message sequence
        messages = self._validate_and_fix_messages(messages)

        # MLX mode doesn't support streaming well, fall back to regular ask
        if self._is_mlx_mode:
            result = await self.ask(messages, tools, response_format, tool_choice, enable_caching)
            content = result.get("content", "")
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

        if tools:
            params["tools"] = tools
            params["tool_choice"] = tool_choice
            params["parallel_tool_calls"] = False

        if response_format and not tools:
            params["response_format"] = response_format

        completion_parts: list[str] = []
        usage_counts: dict[str, int] | None = None

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
                if chunk.choices and chunk.choices[0].delta.content:
                    content = chunk.choices[0].delta.content
                    completion_parts.append(content)
                    yield content

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
            raise
