"""Workspace contract middleware — session-scoped path resolution.

Replaces hardcoded ``/home/ubuntu/task_state.md`` references by computing
a per-session workspace tree and storing it on the RuntimeContext.
"""

from __future__ import annotations

from pydantic import BaseModel, computed_field

from app.domain.services.runtime.middleware import RuntimeContext, RuntimeMiddleware


class WorkspaceContract(BaseModel):
    """Immutable description of all session-scoped filesystem paths.

    Computed fields derive the two most-used file paths so callers never
    have to construct them by hand.
    """

    session_id: str
    workspace: str
    uploads: str
    outputs: str

    @computed_field  # type: ignore[prop-decorator]
    @property
    def task_state_path(self) -> str:
        """Absolute path to the session-scoped task_state.md file."""
        return f"{self.workspace}/task_state.md"

    @computed_field  # type: ignore[prop-decorator]
    @property
    def scratchpad_path(self) -> str:
        """Absolute path to the session-scoped scratchpad.md file."""
        return f"{self.workspace}/scratchpad.md"

    def to_prompt_block(self) -> str:
        """Return an XML block listing all workspace paths for prompt injection."""
        return (
            "<workspace_paths>\n"
            f"  <workspace>{self.workspace}</workspace>\n"
            f"  <uploads>{self.uploads}</uploads>\n"
            f"  <outputs>{self.outputs}</outputs>\n"
            f"  <task_state>{self.task_state_path}</task_state>\n"
            f"  <scratchpad>{self.scratchpad_path}</scratchpad>\n"
            "</workspace_paths>"
        )


class WorkspaceMiddleware(RuntimeMiddleware):
    """Runtime middleware that computes session-scoped workspace paths.

    Populates ``ctx.workspace`` with five path keys and stores a
    :class:`WorkspaceContract` under ``ctx.metadata["workspace_contract"]``
    so downstream code can access strongly-typed path properties.
    """

    def __init__(self, base_dir: str = "/home/ubuntu") -> None:
        self._base_dir = base_dir

    async def before_run(self, ctx: RuntimeContext) -> RuntimeContext:
        root = f"{self._base_dir}/{ctx.session_id}"

        contract = WorkspaceContract(
            session_id=ctx.session_id,
            workspace=root,
            uploads=f"{root}/uploads",
            outputs=f"{root}/outputs",
        )

        ctx.workspace["workspace"] = contract.workspace
        ctx.workspace["uploads"] = contract.uploads
        ctx.workspace["outputs"] = contract.outputs
        ctx.workspace["task_state"] = contract.task_state_path
        ctx.workspace["scratchpad"] = contract.scratchpad_path

        ctx.metadata["workspace_contract"] = contract

        return ctx
