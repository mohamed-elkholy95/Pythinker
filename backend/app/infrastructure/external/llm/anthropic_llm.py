"""Anthropic Claude LLM Implementation

Provides integration with Anthropic's Claude models using the official SDK.
Supports Claude Opus 4, Sonnet 4, and other Claude models.
"""
from typing import List, Dict, Any, Optional, AsyncGenerator, Type, TypeVar
import logging
import asyncio
import json

from pydantic import BaseModel

from app.domain.external.llm import LLM
from app.core.config import get_settings
from app.infrastructure.external.llm.factory import LLMProviderRegistry
from app.domain.services.agents.usage_context import get_usage_context
from app.domain.services.agents.token_manager import TokenManager

T = TypeVar('T', bound=BaseModel)

logger = logging.getLogger(__name__)

# Check if anthropic is installed
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    logger.warning("anthropic package not installed. Run: pip install anthropic")


class TokenLimitExceeded(Exception):
    """Raised when the token limit is exceeded."""
    pass


@LLMProviderRegistry.register("anthropic")
class AnthropicLLM(LLM):
    """Anthropic Claude LLM implementation.

    Uses the official Anthropic Python SDK for Claude API access.
    Supports tool use, structured outputs, and streaming.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ):
        """Initialize Anthropic LLM.

        Args:
            api_key: Anthropic API key (defaults to settings)
            model_name: Model name (defaults to settings)
            temperature: Sampling temperature (defaults to settings)
            max_tokens: Maximum tokens in response (defaults to settings)
        """
        if not ANTHROPIC_AVAILABLE:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")

        settings = get_settings()

        self._api_key = api_key or settings.anthropic_api_key
        if not self._api_key:
            raise ValueError("Anthropic API key is required")

        self._model_name = model_name or getattr(settings, 'anthropic_model_name', 'claude-sonnet-4-20250514')
        self._temperature = temperature if temperature is not None else settings.temperature
        self._max_tokens = max_tokens if max_tokens is not None else settings.max_tokens

        self.client = anthropic.AsyncAnthropic(api_key=self._api_key)

        logger.info(f"Initialized Anthropic LLM with model: {self._model_name}")

    @property
    def model_name(self) -> str:
        return self._model_name

    @property
    def temperature(self) -> float:
        return self._temperature

    @property
    def max_tokens(self) -> int:
        return self._max_tokens

    async def _record_usage(self, response: Any) -> None:
        """Record usage from Anthropic response if usage context is set.

        Args:
            response: Anthropic API response containing usage info
        """
        ctx = get_usage_context()
        if not ctx:
            return

        try:
            # Extract usage from Anthropic response
            usage = getattr(response, 'usage', None)
            if not usage:
                return

            input_tokens = getattr(usage, 'input_tokens', 0)
            output_tokens = getattr(usage, 'output_tokens', 0)
            cache_read_tokens = getattr(usage, 'cache_read_input_tokens', 0)
            cache_creation_tokens = getattr(usage, 'cache_creation_input_tokens', 0)

            # Total cached tokens = read from cache + created for cache
            cached_tokens = cache_read_tokens + cache_creation_tokens

            # Lazy import to avoid circular dependency
            from app.application.services.usage_service import get_usage_service
            usage_service = get_usage_service()

            await usage_service.record_llm_usage(
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                model=ctx.model_override or self._model_name,
                prompt_tokens=input_tokens,
                completion_tokens=output_tokens,
                cached_tokens=cached_tokens,
            )
        except Exception as e:
            logger.warning(f"Failed to record usage: {e}")

    async def _record_stream_usage(
        self,
        messages: List[Dict[str, Any]],
        completion_text: str,
        tools: Optional[List[Dict[str, Any]]] = None,
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

            from app.application.services.usage_service import get_usage_service
            usage_service = get_usage_service()

            await usage_service.record_llm_usage(
                user_id=ctx.user_id,
                session_id=ctx.session_id,
                model=ctx.model_override or self._model_name,
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                cached_tokens=0,
            )
        except Exception as e:
            logger.warning(f"Failed to record streaming usage: {e}")

    def _convert_openai_tools_to_anthropic(
        self,
        tools: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Convert OpenAI tool format to Anthropic format.

        Args:
            tools: List of tools in OpenAI format

        Returns:
            List of tools in Anthropic format
        """
        anthropic_tools = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                anthropic_tools.append({
                    "name": func.get("name"),
                    "description": func.get("description", ""),
                    "input_schema": func.get("parameters", {"type": "object", "properties": {}})
                })
        return anthropic_tools

    def _convert_openai_messages_to_anthropic(
        self,
        messages: List[Dict[str, Any]]
    ) -> tuple[Optional[str], List[Dict[str, Any]]]:
        """Convert OpenAI message format to Anthropic format.

        Args:
            messages: List of messages in OpenAI format

        Returns:
            Tuple of (system_prompt, anthropic_messages)
        """
        system_prompt = None
        anthropic_messages = []

        for msg in messages:
            role = msg.get("role", "")
            content = msg.get("content", "")

            if role == "system":
                # Anthropic uses a separate system parameter
                system_prompt = content
                continue

            elif role == "assistant":
                # Handle assistant messages with tool calls
                if msg.get("tool_calls"):
                    tool_use_blocks = []
                    for tc in msg.get("tool_calls", []):
                        func = tc.get("function", {})
                        args = func.get("arguments", "{}")
                        if isinstance(args, str):
                            try:
                                args = json.loads(args)
                            except json.JSONDecodeError:
                                args = {}

                        tool_use_blocks.append({
                            "type": "tool_use",
                            "id": tc.get("id", ""),
                            "name": func.get("name", ""),
                            "input": args
                        })

                    # Include text content if present
                    if content:
                        anthropic_messages.append({
                            "role": "assistant",
                            "content": [{"type": "text", "text": content}] + tool_use_blocks
                        })
                    else:
                        anthropic_messages.append({
                            "role": "assistant",
                            "content": tool_use_blocks
                        })
                else:
                    anthropic_messages.append({
                        "role": "assistant",
                        "content": content or ""
                    })

            elif role == "tool":
                # Convert tool response to Anthropic format
                anthropic_messages.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id", ""),
                        "content": content
                    }]
                })

            elif role == "user":
                anthropic_messages.append({
                    "role": "user",
                    "content": content
                })

        return system_prompt, anthropic_messages

    def _convert_anthropic_response_to_openai(
        self,
        response: Any
    ) -> Dict[str, Any]:
        """Convert Anthropic response to OpenAI format.

        Args:
            response: Anthropic API response

        Returns:
            Response in OpenAI format
        """
        result = {
            "role": "assistant",
            "content": None,
            "tool_calls": None
        }

        text_content = []
        tool_calls = []

        for block in response.content:
            if block.type == "text":
                text_content.append(block.text)
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "type": "function",
                    "function": {
                        "name": block.name,
                        "arguments": json.dumps(block.input)
                    }
                })

        if text_content:
            result["content"] = "\n".join(text_content)

        if tool_calls:
            result["tool_calls"] = tool_calls

        return result

    def _prepare_system_with_caching(self, system_prompt: str, enable_caching: bool) -> Any:
        """Prepare system prompt with cache control for Anthropic.

        When caching is enabled, marks the system prompt for ephemeral caching
        which can reduce token costs by up to 90% on repeated requests.

        Args:
            system_prompt: The system prompt text
            enable_caching: Whether to enable prompt caching

        Returns:
            System prompt with cache control markers if caching enabled
        """
        if not enable_caching or not system_prompt:
            return system_prompt

        # Use Anthropic's cache control format for ephemeral caching
        # This marks the system prompt as cacheable for subsequent requests
        return [
            {
                "type": "text",
                "text": system_prompt,
                "cache_control": {"type": "ephemeral"}
            }
        ]

    async def ask(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        tool_choice: Optional[str] = None,
        enable_caching: bool = True
    ) -> Dict[str, Any]:
        """Send chat request to Anthropic API.

        Args:
            messages: List of messages in OpenAI format
            tools: Optional list of tools in OpenAI format
            response_format: Optional response format (limited support)
            tool_choice: Optional tool choice configuration
            enable_caching: Whether to enable prompt caching (up to 90% token savings)

        Returns:
            Response message in OpenAI format
        """
        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries + 1):
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))
                    logger.info(f"Retrying Anthropic request (attempt {attempt + 1}/{max_retries + 1})")
                    await asyncio.sleep(delay)

                # Convert messages to Anthropic format
                system_prompt, anthropic_messages = self._convert_openai_messages_to_anthropic(messages)

                # Build request parameters
                params = {
                    "model": self._model_name,
                    "max_tokens": self._max_tokens,
                    "messages": anthropic_messages,
                }

                # Anthropic uses temperature differently - 0 to 1
                if self._temperature is not None:
                    params["temperature"] = min(1.0, max(0.0, self._temperature))

                # Apply cache control to system prompt for token savings
                if system_prompt:
                    params["system"] = self._prepare_system_with_caching(system_prompt, enable_caching)

                if tools:
                    params["tools"] = self._convert_openai_tools_to_anthropic(tools)

                    # Handle tool_choice
                    if tool_choice == "required":
                        params["tool_choice"] = {"type": "any"}
                    elif tool_choice == "none":
                        params["tool_choice"] = {"type": "none"}
                    # "auto" is the default

                response = await self.client.messages.create(**params)

                # Track usage if context is set
                await self._record_usage(response)

                return self._convert_anthropic_response_to_openai(response)

            except anthropic.RateLimitError as e:
                logger.warning(f"Anthropic rate limit on attempt {attempt + 1}: {e}")
                if attempt == max_retries:
                    raise

            except anthropic.BadRequestError as e:
                error_msg = str(e).lower()
                if "token" in error_msg or "context" in error_msg:
                    raise TokenLimitExceeded(str(e))
                raise

            except Exception as e:
                logger.error(f"Anthropic API error on attempt {attempt + 1}: {e}")
                if attempt == max_retries:
                    raise

        raise RuntimeError("Failed to get response after all retries")

    async def ask_structured(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[T],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        enable_caching: bool = True
    ) -> T:
        """Send chat request with structured output validation.

        Uses Anthropic's tool use feature to enforce structured output.

        Args:
            messages: List of messages
            response_model: Pydantic model class for response validation
            tools: Optional additional tools
            tool_choice: Optional tool choice
            enable_caching: Whether to use prompt caching

        Returns:
            Validated Pydantic model instance
        """
        schema = response_model.model_json_schema()

        # Create a tool that returns the structured response
        structured_tool = {
            "type": "function",
            "function": {
                "name": "return_structured_response",
                "description": f"Return a response matching the {response_model.__name__} schema",
                "parameters": schema
            }
        }

        # Add instruction to use the tool
        enhanced_messages = list(messages)
        if enhanced_messages and enhanced_messages[-1].get("role") == "user":
            enhanced_messages[-1] = {
                **enhanced_messages[-1],
                "content": enhanced_messages[-1].get("content", "") +
                          f"\n\nPlease respond using the return_structured_response tool."
            }

        response = await self.ask(
            messages=enhanced_messages,
            tools=[structured_tool],
            tool_choice="required",
            enable_caching=enable_caching
        )

        # Extract structured response from tool call
        if response.get("tool_calls"):
            for tc in response["tool_calls"]:
                if tc["function"]["name"] == "return_structured_response":
                    args = tc["function"]["arguments"]
                    if isinstance(args, str):
                        args = json.loads(args)
                    return response_model.model_validate(args)

        raise ValueError("Model did not return structured response")

    async def ask_stream(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        tool_choice: Optional[str] = None,
        enable_caching: bool = True
    ) -> AsyncGenerator[str, None]:
        """Stream chat response from Anthropic API.

        Args:
            messages: List of messages
            tools: Optional tools for function calling
            response_format: Optional response format
            tool_choice: Optional tool choice
            enable_caching: Whether to use prompt caching

        Yields:
            Content chunks as strings
        """
        # Convert messages to Anthropic format
        system_prompt, anthropic_messages = self._convert_openai_messages_to_anthropic(messages)

        params = {
            "model": self._model_name,
            "max_tokens": self._max_tokens,
            "messages": anthropic_messages,
        }

        if self._temperature is not None:
            params["temperature"] = min(1.0, max(0.0, self._temperature))

        if system_prompt:
            params["system"] = system_prompt

        if tools:
            params["tools"] = self._convert_openai_tools_to_anthropic(tools)

        completion_parts: List[str] = []

        try:
            async with self.client.messages.stream(**params) as stream:
                async for text in stream.text_stream:
                    completion_parts.append(text)
                    yield text

            if completion_parts:
                await self._record_stream_usage(messages, "".join(completion_parts), tools=tools)
            else:
                await self._record_stream_usage(messages, "", tools=tools)

        except anthropic.BadRequestError as e:
            error_msg = str(e).lower()
            if "token" in error_msg or "context" in error_msg:
                raise TokenLimitExceeded(str(e))
            raise


# Test function
if __name__ == "__main__":
    import asyncio
    import os

    async def test():
        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            print("Set ANTHROPIC_API_KEY environment variable to test")
            return

        llm = AnthropicLLM(api_key=api_key)

        response = await llm.ask([
            {"role": "user", "content": "What is 2 + 2?"}
        ])

        print(f"Response: {response}")

    asyncio.run(test())
