from pydantic import BaseModel, Field


class Message(BaseModel):
    title: str | None = None
    message: str = ""
    attachments: list[str] = []
    skills: list[str] = Field(default_factory=list, description="Skill IDs enabled for this message")
    deep_research: bool = Field(default=False, description="Enable deep research mode (parallel wide_research)")
