"""Schema-first hook configuration models."""

from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter


class BaseHook(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: str


class BashHook(BaseHook):
    type: Literal["bash"] = "bash"
    command: str


class PromptHook(BaseHook):
    type: Literal["prompt"] = "prompt"
    prompt: str


class AgentHook(BaseHook):
    type: Literal["agent"] = "agent"
    agent: str
    prompt: str | None = None


class HttpHook(BaseHook):
    type: Literal["http"] = "http"
    url: str
    method: Literal["GET", "POST", "PUT", "PATCH", "DELETE"] = "POST"
    headers: dict[str, str] = Field(default_factory=dict)
    body: dict[str, Any] | None = None
    timeout_seconds: float = 30.0


HookConfig = Annotated[BashHook | PromptHook | AgentHook | HttpHook, Field(discriminator="type")]


def validate_hook_configs(hook_configs: list[Any] | None) -> list[HookConfig]:
    """Validate hook configs eagerly at startup."""
    adapter = TypeAdapter(list[HookConfig])
    return adapter.validate_python(hook_configs or [])
