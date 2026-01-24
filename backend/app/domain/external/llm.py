from typing import List, Dict, Any, Optional, Protocol, AsyncGenerator, Type, TypeVar
from pydantic import BaseModel

T = TypeVar('T', bound=BaseModel)


class LLM(Protocol):
    """AI service gateway interface for interacting with AI services"""

    async def ask(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        tool_choice: Optional[str] = None
    ) -> Dict[str, Any]:
        """Send chat request to AI service

        Args:
            messages: List of messages, including conversation history
            tools: Optional list of tools for function calling
            response_format: Optional response format configuration
            tool_choice: Optional tool choice configuration
        Returns:
            Response message from AI service
        """
        ...

    async def ask_structured(
        self,
        messages: List[Dict[str, str]],
        response_model: Type[T],
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[str] = None,
        enable_caching: bool = True
    ) -> T:
        """Send chat request with structured output validation.

        Uses native JSON schema support for type-safe responses.

        Args:
            messages: List of messages
            response_model: Pydantic model class for response validation
            tools: Optional tools (usually None for structured output)
            tool_choice: Optional tool choice
            enable_caching: Whether to use prompt caching

        Returns:
            Validated Pydantic model instance
        """
        ...

    async def ask_stream(
        self,
        messages: List[Dict[str, str]],
        tools: Optional[List[Dict[str, Any]]] = None,
        response_format: Optional[Dict[str, Any]] = None,
        tool_choice: Optional[str] = None,
        enable_caching: bool = True
    ) -> AsyncGenerator[str, None]:
        """Stream chat response.

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
        ...

    @property
    def model_name(self) -> str:
        """Get the model name"""
        ...

    @property
    def temperature(self) -> float:
        """Get the temperature"""
        ...

    @property
    def max_tokens(self) -> int:
        """Get the max tokens"""
        ...