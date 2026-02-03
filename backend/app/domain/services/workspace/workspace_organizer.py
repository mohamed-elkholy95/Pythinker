"""Workspace organization and deliverable tracking."""

import logging

from app.domain.external.sandbox import Sandbox
from app.domain.services.workspace.workspace_templates import WorkspaceTemplate

logger = logging.getLogger(__name__)


class WorkspaceOrganizer:
    """Organizes workspace structure and tracks deliverables."""

    def __init__(self, sandbox: Sandbox, workspace_root: str = "/workspace"):
        self._sandbox = sandbox
        self._workspace_root = workspace_root
        self._deliverables: list[str] = []

    async def initialize_workspace(self, session_id: str, template: WorkspaceTemplate) -> dict[str, str]:
        """Initialize workspace structure from template.

        Args:
            session_id: Session ID for sandbox operations
            template: Workspace template to use

        Returns:
            Dict mapping folder names to their purposes
        """
        logger.info(f"Initializing workspace with template: {template.name}")

        # Create folders
        for folder_name, purpose in template.folders.items():
            folder_path = f"{self._workspace_root}/{folder_name}"

            # Create directory using exec_command
            await self._sandbox.exec_command(
                session_id=session_id, exec_dir="/workspace", command=f"mkdir -p {folder_path}"
            )

            logger.debug(f"Created folder: {folder_path} ({purpose})")

        # Create README using file_write
        readme_path = f"{self._workspace_root}/README.md"
        await self._sandbox.file_write(file=readme_path, content=template.readme_content)

        logger.info(f"Workspace initialized: {len(template.folders)} folders created")
        return template.folders

    def add_deliverable(self, file_path: str):
        """Track a file as a deliverable"""
        if file_path not in self._deliverables:
            self._deliverables.append(file_path)
            logger.info(f"Added deliverable: {file_path}")

    def get_deliverables(self) -> list[str]:
        """Get list of tracked deliverables"""
        return self._deliverables.copy()

    async def generate_manifest(self, session_id: str) -> str:
        """Generate deliverables manifest.

        Args:
            session_id: Session ID for sandbox operations

        Returns:
            Path to manifest file
        """
        manifest_path = f"{self._workspace_root}/deliverables/MANIFEST.md"

        manifest_content = "# Deliverables Manifest\n\n"
        manifest_content += f"Total deliverables: {len(self._deliverables)}\n\n"

        for i, deliverable in enumerate(self._deliverables, 1):
            manifest_content += f"{i}. `{deliverable}`\n"

        # Write manifest using file_write
        await self._sandbox.file_write(file=manifest_path, content=manifest_content)

        logger.info(f"Generated manifest: {manifest_path}")
        return manifest_path
