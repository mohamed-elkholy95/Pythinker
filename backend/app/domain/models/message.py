from pydantic import BaseModel, Field


class Message(BaseModel):
    title: str | None = None
    message: str = ""
    attachments: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list, description="Skill IDs enabled for this message")
    deep_research: bool = Field(default=False, description="Enable deep research mode (parallel wide_research)")
    thinking_mode: str | None = Field(default=None, description="Model tier override: 'auto', 'fast', 'deep_think'")
    # Follow-up context from suggestion clicks
    follow_up_selected_suggestion: str | None = Field(default=None, description="The suggestion text that was clicked")
    follow_up_anchor_event_id: str | None = Field(default=None, description="Event ID to anchor context to")
    follow_up_source: str | None = Field(default=None, description="Source of follow-up (e.g., 'suggestion_click')")
