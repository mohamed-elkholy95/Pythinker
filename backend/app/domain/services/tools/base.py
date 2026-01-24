from typing import Dict, Any, List, Callable, Optional
import inspect
import logging
from app.domain.models.tool_result import ToolResult

logger = logging.getLogger(__name__)

# Default observation limits per tool category (in characters)
DEFAULT_MAX_OBSERVE = 8000
TOOL_OBSERVATION_LIMITS = {
    "browser": 10000,   # Browser content can be verbose
    "shell": 5000,      # Command output usually shorter
    "file": 8000,       # File content moderate
    "search": 8000,     # Search results moderate
    "mcp": 6000,        # MCP resources varied
    "message": 2000,    # Messages should be concise
}


def _truncate_output(content: str, max_length: int, preserve_end: bool = True) -> str:
    """Truncate content intelligently, preserving structure.

    Args:
        content: Content to truncate
        max_length: Maximum length
        preserve_end: Whether to preserve some content from the end

    Returns:
        Truncated content with indicator
    """
    if len(content) <= max_length:
        return content

    if preserve_end:
        # Reserve 20% for the end portion
        end_reserve = int(max_length * 0.2)
        start_length = max_length - end_reserve - 50  # 50 for truncation message

        # Find natural break points
        start_content = content[:start_length]
        last_newline = start_content.rfind('\n')
        if last_newline > start_length * 0.8:
            start_content = start_content[:last_newline]

        end_content = content[-end_reserve:]
        first_newline = end_content.find('\n')
        if first_newline > 0 and first_newline < end_reserve * 0.2:
            end_content = end_content[first_newline + 1:]

        truncated_chars = len(content) - len(start_content) - len(end_content)
        return f"{start_content}\n\n... [{truncated_chars:,} characters truncated] ...\n\n{end_content}"
    else:
        # Simple truncation from end
        truncated = content[:max_length]
        last_newline = truncated.rfind('\n')
        if last_newline > max_length * 0.8:
            truncated = truncated[:last_newline]

        truncated_chars = len(content) - len(truncated)
        return f"{truncated}\n\n... [{truncated_chars:,} characters truncated]"


def tool(
    name: str, 
    description: str,
    parameters: Dict[str, Dict[str, Any]],
    required: List[str]
) -> Callable:
    """Tool registration decorator
    
    Args:
        name: Tool name
        description: Tool description
        parameters: Tool parameter definitions
        required: List of required parameters
        
    Returns:
        Decorator function
    """
    def decorator(func):
        # Create tool schema directly using provided parameters, without automatic extraction
        schema = {
            "type": "function",
            "function": {
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object", 
                    "properties": parameters,
                    "required": required
                }
            }
        }
        
        # Store tool information
        func._function_name = name
        func._tool_description = description
        func._tool_schema = schema
        
        return func
    
    return decorator

class BaseTool:
    """Base tool class, providing common tool calling methods with observation limiting"""

    name: str = ""
    max_observe: Optional[int] = None  # Per-tool observation limit (None = use category default)

    def __init__(self, max_observe: Optional[int] = None):
        """Initialize base tool class

        Args:
            max_observe: Optional custom observation limit for this tool instance
        """
        self._tools_cache = None
        if max_observe is not None:
            self.max_observe = max_observe
        elif self.name and self.name in TOOL_OBSERVATION_LIMITS:
            self.max_observe = TOOL_OBSERVATION_LIMITS[self.name]
        else:
            # Try to find category match
            for category, limit in TOOL_OBSERVATION_LIMITS.items():
                if category in self.name.lower():
                    self.max_observe = limit
                    break
            else:
                self.max_observe = DEFAULT_MAX_OBSERVE
    
    def get_tools(self) -> List[Dict[str, Any]]:
        """Get all registered tools
        
        Returns:
            List of tools
        """
        if self._tools_cache is not None:
            return self._tools_cache
        
        tools = []
        for _, method in inspect.getmembers(self, inspect.ismethod):
            if hasattr(method, '_tool_schema'):
                tools.append(method._tool_schema)
        
        self._tools_cache = tools
        return tools
    
    def has_function(self, function_name: str) -> bool:
        """Check if specified function exists
        
        Args:
            function_name: Function name
            
        Returns:
            Whether the tool exists
        """
        for _, method in inspect.getmembers(self, inspect.ismethod):
            if hasattr(method, '_function_name') and method._function_name == function_name:
                return True
        return False
    
    def _filter_parameters(self, method: Callable, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Filter parameters to match method signature
        
        Args:
            method: Target method
            kwargs: Input parameters
            
        Returns:
            Filtered parameters that match the method signature
        """
        # Get method signature
        sig = inspect.signature(method)
        
        # Filter kwargs to only include parameters that the method accepts
        filtered_kwargs = {}
        for param_name, param_value in kwargs.items():
            if param_name in sig.parameters:
                filtered_kwargs[param_name] = param_value
        
        return filtered_kwargs
    
    async def invoke_function(self, function_name: str, **kwargs) -> ToolResult:
        """Invoke specified tool with observation limiting

        Args:
            function_name: Function name
            **kwargs: Parameters

        Returns:
            Invocation result with potentially truncated output

        Raises:
            ValueError: Raised when tool doesn't exist
        """
        for _, method in inspect.getmembers(self, inspect.ismethod):
            if hasattr(method, '_function_name') and method._function_name == function_name:
                # Filter parameters to match method signature
                filtered_kwargs = self._filter_parameters(method, kwargs)
                result = await method(**filtered_kwargs)

                # Apply observation limiting to result message
                if self.max_observe and result.message:
                    original_length = len(result.message)
                    if original_length > self.max_observe:
                        result.message = _truncate_output(
                            result.message,
                            self.max_observe,
                            preserve_end=True
                        )
                        logger.debug(
                            f"Truncated {function_name} output from {original_length:,} "
                            f"to {len(result.message):,} chars (limit: {self.max_observe:,})"
                        )

                return result

        raise ValueError(f"Tool '{function_name}' not found")

    def set_max_observe(self, limit: Optional[int]) -> None:
        """Set custom observation limit for this tool instance.

        Args:
            limit: New observation limit, or None to disable limiting
        """
        self.max_observe = limit

    def get_observation_stats(self, result: ToolResult) -> Dict[str, Any]:
        """Get statistics about observation limiting for a result.

        Args:
            result: Tool result to analyze

        Returns:
            Dict with truncation stats
        """
        message_length = len(result.message) if result.message else 0
        return {
            "message_length": message_length,
            "max_observe": self.max_observe,
            "would_truncate": self.max_observe and message_length > self.max_observe,
            "truncation_amount": max(0, message_length - (self.max_observe or message_length))
        } 