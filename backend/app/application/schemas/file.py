from pydantic import BaseModel


class FileViewResponse(BaseModel):
    """Application DTO for file content responses."""

    content: str
    file: str
