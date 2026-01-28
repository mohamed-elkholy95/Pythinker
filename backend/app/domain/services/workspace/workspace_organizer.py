"""Workspace organization and deliverable tracking."""
from typing import Dict, List, Optional
from pathlib import Path
import logging
from app.domain.services.workspace.workspace_templates import WorkspaceTemplate
from app.domain.external.sandbox import Sandbox

logger = logging.getLogger(__name__)


class WorkspaceOrganizer:
    """Organizes workspace structure and tracks deliverables."""

    def __init__(self, sandbox: Sandbox, workspace_root: str = "/workspace"):
        self._sandbox = sandbox
        self._workspace_root = workspace_root
        self._deliverables: List[str] = []

    async def initialize_workspace(
        self,
        template: WorkspaceTemplate
    ) -> Dict[str, str]:
        """Initialize workspace structure from template.

        Returns:
            Dict mapping folder names to their purposes
        """
        logger.info(f"Initializing workspace with template: {template.name}")

        # Create folders
        for folder_name, purpose in template.folders.items():
            folder_path = f"{self._workspace_root}/{folder_name}"

            # Create directory
            await self._sandbox.execute_code(
                language="python",
                code=f"""
import os
os.makedirs("{folder_path}", exist_ok=True)
"""
            )

            logger.debug(f"Created folder: {folder_path} ({purpose})")

        # Create README
        readme_path = f"{self._workspace_root}/README.md"
        await self._sandbox.execute_code(
            language="python",
            code=f"""
with open("{readme_path}", "w") as f:
    f.write('''{template.readme_content}''')
"""
        )

        logger.info(f"Workspace initialized: {len(template.folders)} folders created")
        return template.folders

    def add_deliverable(self, file_path: str):
        """Track a file as a deliverable"""
        if file_path not in self._deliverables:
            self._deliverables.append(file_path)
            logger.info(f"Added deliverable: {file_path}")

    def get_deliverables(self) -> List[str]:
        """Get list of tracked deliverables"""
        return self._deliverables.copy()

    async def generate_manifest(self) -> str:
        """Generate deliverables manifest.

        Returns:
            Path to manifest file
        """
        manifest_path = f"{self._workspace_root}/deliverables/MANIFEST.md"

        manifest_content = "# Deliverables Manifest\n\n"
        manifest_content += f"Total deliverables: {len(self._deliverables)}\n\n"

        for i, deliverable in enumerate(self._deliverables, 1):
            manifest_content += f"{i}. `{deliverable}`\n"

        # Write manifest
        await self._sandbox.execute_code(
            language="python",
            code=f"""
with open("{manifest_path}", "w") as f:
    f.write('''{manifest_content}''')
"""
        )

        logger.info(f"Generated manifest: {manifest_path}")
        return manifest_path
