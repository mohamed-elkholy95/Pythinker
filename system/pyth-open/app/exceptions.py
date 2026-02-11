class ToolError(Exception):
    """Raised when a tool encounters an error."""

    def __init__(self, message):
        self.message = message


class PythinkerError(Exception):
    """Base exception for all Pythinker errors"""


class TokenLimitExceeded(PythinkerError):
    """Exception raised when the token limit is exceeded"""
