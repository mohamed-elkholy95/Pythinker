from typing import List, Dict, Any, Optional
from openai import AsyncOpenAI
from app.domain.external.llm import LLM
from app.core.config import get_settings
from app.domain.services.agents.error_handler import TokenLimitExceeded
import logging
import asyncio
import time


logger = logging.getLogger(__name__)

class OpenAILLM(LLM):
    def __init__(self):
        settings = get_settings()
        self.client = AsyncOpenAI(
            api_key=settings.api_key,
            base_url=settings.api_base
        )
        
        self._model_name = settings.model_name
        self._temperature = settings.temperature
        self._max_tokens = settings.max_tokens
        logger.info(f"Initialized OpenAI LLM with model: {self._model_name}")
    
    @property
    def model_name(self) -> str:
        return self._model_name
    
    @property
    def temperature(self) -> float:
        return self._temperature
    
    @property
    def max_tokens(self) -> int:
        return self._max_tokens
    
    def _validate_and_fix_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Validate message sequence and fix tool_call/tool_response ordering issues.

        Ensures every assistant message with tool_calls is followed by the
        corresponding tool responses before any other message type.
        """
        if not messages:
            return messages

        fixed_messages = []
        pending_tool_ids = set()

        for i, msg in enumerate(messages):
            role = msg.get("role", "")

            # Check if this is an assistant message with tool_calls
            if role == "assistant" and msg.get("tool_calls"):
                # If we have pending tool_ids from a previous assistant message,
                # that means we never got responses - skip the orphaned message
                if pending_tool_ids:
                    logger.warning(f"Removing orphaned assistant message with unfulfilled tool_calls: {pending_tool_ids}")
                    pending_tool_ids = set()

                # Track the new tool_call_ids
                pending_tool_ids = {
                    tc.get("id") for tc in msg.get("tool_calls", []) if tc.get("id")
                }
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
                    logger.warning(f"Incomplete tool sequence detected, removing last assistant message")
                    # Find and remove the last assistant message with tool_calls
                    for j in range(len(fixed_messages) - 1, -1, -1):
                        if fixed_messages[j].get("role") == "assistant" and fixed_messages[j].get("tool_calls"):
                            fixed_messages.pop(j)
                            break
                    pending_tool_ids = set()

                fixed_messages.append(msg)

        # Handle trailing incomplete tool sequence
        if pending_tool_ids:
            logger.warning(f"Trailing incomplete tool sequence, removing last assistant message")
            for j in range(len(fixed_messages) - 1, -1, -1):
                if fixed_messages[j].get("role") == "assistant" and fixed_messages[j].get("tool_calls"):
                    fixed_messages.pop(j)
                    break

        if len(fixed_messages) != len(messages):
            logger.info(f"Fixed message sequence: {len(messages)} -> {len(fixed_messages)} messages")

        return fixed_messages

    async def ask(self, messages: List[Dict[str, str]],
                tools: Optional[List[Dict[str, Any]]] = None,
                response_format: Optional[Dict[str, Any]] = None,
                tool_choice: Optional[str] = None) -> Dict[str, Any]:
        """Send chat request to OpenAI API with retry mechanism"""
        # Validate and fix message sequence before sending
        messages = self._validate_and_fix_messages(messages)

        max_retries = 3
        base_delay = 1.0

        for attempt in range(max_retries + 1):  # every try
            response = None
            try:
                if attempt > 0:
                    delay = base_delay * (2 ** (attempt - 1))  # back off
                    logger.info(f"Retrying OpenAI API request (attempt {attempt + 1}/{max_retries + 1}) after {delay}s delay")
                    await asyncio.sleep(delay)

                # GPT-5 nano/mini and o1/o3 models have different parameter requirements
                is_new_model = self._model_name.startswith(('gpt-5', 'o1', 'o3'))

                # Build parameters based on model type
                params = {
                    'model': self._model_name,
                    'messages': messages,
                }

                if is_new_model:
                    # GPT-5+ models use max_completion_tokens and don't support custom temperature
                    params['max_completion_tokens'] = self._max_tokens
                else:
                    # Older models use max_tokens and support temperature
                    params['max_tokens'] = self._max_tokens
                    params['temperature'] = self._temperature

                if tools:
                    logger.debug(f"Sending request to OpenAI with tools, model: {self._model_name}, attempt: {attempt + 1}")
                    response = await self.client.chat.completions.create(
                        **params,
                        tools=tools,
                        response_format=response_format,
                        tool_choice=tool_choice,
                        parallel_tool_calls=False,
                    )
                else:
                    logger.debug(f"Sending request to OpenAI without tools, model: {self._model_name}, attempt: {attempt + 1}")
                    response = await self.client.chat.completions.create(
                        **params,
                        response_format=response_format,
                    )

                logger.debug(f"Response from OpenAI: {response.model_dump()}")

                
                if not response or not response.choices:
                    error_msg = f"OpenAI API returned invalid response (no choices) on attempt {attempt + 1}"
                    logger.error(error_msg)
                    if attempt == max_retries:
                        raise ValueError(f"Failed after {max_retries + 1} attempts: {error_msg}")
                    continue

                return response.choices[0].message.model_dump()

            except Exception as e:
                error_msg = str(e).lower()
                # Check for token limit errors and raise specific exception
                if any(term in error_msg for term in [
                    'context_length_exceeded',
                    'maximum context length',
                    'too many tokens',
                    'max_tokens',
                    'context window'
                ]):
                    logger.warning(f"Token limit exceeded: {e}")
                    raise TokenLimitExceeded(str(e))

                error_log = f"Error calling OpenAI API on attempt {attempt + 1}: {str(e)}"
                logger.error(error_log)
                if attempt == max_retries:
                    raise e
                continue

