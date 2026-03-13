"""Capability manifest domain model.

Per-session snapshot of active capabilities, middleware configuration, model
properties, and sandbox state.  Stored on RuntimeContext.metadata so any
downstream middleware or prompt builder can read it without re-computing.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ModelCapabilities(BaseModel):
    """Properties of the language model assigned to this session."""

    name: str
    supports_vision: bool = False
    supports_thinking: bool = False
    max_tokens: int = 4096


class SandboxState(BaseModel):
    """Current state of the Docker sandbox for this session."""

    active: bool = False
    sandbox_id: str | None = None


class CapabilityManifest(BaseModel):
    """Per-session manifest of active capabilities and runtime configuration.

    Built once during ``before_run`` by :class:`CapabilityMiddleware` and
    stored under ``ctx.metadata["capability_manifest"]`` for downstream use.
    """

    session_id: str
    active_skills: list[str] = Field(default_factory=list)
    mcp_servers: list[str] = Field(default_factory=list)
    tool_categories: set[str] = Field(default_factory=set)
    model: ModelCapabilities = Field(default_factory=lambda: ModelCapabilities(name="default"))
    sandbox: SandboxState = Field(default_factory=SandboxState)
    max_concurrent_delegates: int = 3

    def to_prompt_block(self) -> str:
        """Return an XML block summarising the manifest for prompt injection.

        Only non-empty / non-default fields are included so the block stays
        concise when the session has minimal capabilities configured.
        """
        lines: list[str] = ["<capability_manifest>"]

        lines.append(f"  <session_id>{self.session_id}</session_id>")

        if self.active_skills:
            skills_str = ", ".join(self.active_skills)
            lines.append(f"  <active_skills>{skills_str}</active_skills>")

        if self.mcp_servers:
            servers_str = ", ".join(self.mcp_servers)
            lines.append(f"  <mcp_servers>{servers_str}</mcp_servers>")

        if self.tool_categories:
            cats_str = ", ".join(sorted(self.tool_categories))
            lines.append(f"  <tool_categories>{cats_str}</tool_categories>")

        lines.append(f'  <model name="{self.model.name}"')
        lines.append(f'         supports_vision="{str(self.model.supports_vision).lower()}"')
        lines.append(f'         supports_thinking="{str(self.model.supports_thinking).lower()}"')
        lines.append(f'         max_tokens="{self.model.max_tokens}" />')

        lines.append(
            f'  <sandbox active="{str(self.sandbox.active).lower()}"'
            + (f' sandbox_id="{self.sandbox.sandbox_id}"' if self.sandbox.sandbox_id else "")
            + " />"
        )

        lines.append(f"  <max_concurrent_delegates>{self.max_concurrent_delegates}</max_concurrent_delegates>")

        lines.append("</capability_manifest>")
        return "\n".join(lines)
