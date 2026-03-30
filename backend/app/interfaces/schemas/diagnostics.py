"""Diagnostics API schemas."""

from pydantic import BaseModel, Field


class ContainerLogsPreviewResponse(BaseModel):
    """Recent container stdout/stderr lines for local troubleshooting."""

    enabled: bool = Field(description="Whether the server allows log preview (feature flag).")
    backend: list[str] = Field(
        default_factory=list, description="Last lines from a container whose name matches 'backend'."
    )
    sandbox: list[str] = Field(
        default_factory=list, description="Last lines from a container whose name matches 'sandbox'."
    )
    message: str | None = Field(default=None, description="Optional hint when disabled or Docker unavailable.")
