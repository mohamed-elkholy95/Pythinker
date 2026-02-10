from pydantic import BaseModel


class ConsoleRecord(BaseModel):
    """Application DTO for shell console lines."""

    ps1: str
    command: str
    output: str


class ShellViewResponse(BaseModel):
    """Application DTO for shell session output."""

    output: str
    session_id: str
    console: list[ConsoleRecord] | None = None
