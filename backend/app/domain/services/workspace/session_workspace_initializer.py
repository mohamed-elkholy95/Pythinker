"""Session workspace initialization helper.

Provides integration point for workspace template selection and initialization
when a new task is started.
"""

import logging

from app.domain.external.sandbox import Sandbox
from app.domain.models.session import Session
from app.domain.repositories.session_repository import SessionRepository
from app.domain.services.workspace import WorkspaceOrganizer, WorkspaceSelector

logger = logging.getLogger(__name__)


class SessionWorkspaceInitializer:
    """Initializes workspace for sessions based on task description.

    Usage:
        initializer = SessionWorkspaceInitializer(session_repository)
        await initializer.initialize_workspace_if_needed(session, sandbox, task_description)
    """

    def __init__(self, session_repository: SessionRepository):
        self._session_repository = session_repository
        self._selector = WorkspaceSelector()

    async def initialize_workspace_if_needed(
        self,
        session: Session,
        sandbox: Sandbox,
        task_description: str
    ) -> dict[str, str] | None:
        """Initialize workspace for session if not already initialized.

        Args:
            session: Session to initialize workspace for
            sandbox: Sandbox instance for workspace operations
            task_description: User's task description for template selection

        Returns:
            Dict mapping folder names to purposes, or None if already initialized
        """
        # Skip if workspace already initialized
        if session.workspace_structure:
            logger.debug(f"Workspace already initialized for session {session.id}")
            return None

        # Skip for discuss mode (no workspace needed)
        if session.mode == "discuss":
            logger.debug(f"Skipping workspace init for discuss mode session {session.id}")
            return None

        try:
            # Select appropriate template
            template = self._selector.select_template(task_description)
            logger.info(f"Selected workspace template '{template.name}' for session {session.id}")

            # Initialize workspace structure
            organizer = WorkspaceOrganizer(sandbox)
            workspace_structure = await organizer.initialize_workspace(session.id, template)

            # Store in session
            session.workspace_structure = workspace_structure
            await self._session_repository.update_by_id(
                session.id,
                {"workspace_structure": workspace_structure}
            )

            logger.info(
                f"Initialized {len(workspace_structure)} workspace folders "
                f"for session {session.id}"
            )

            return workspace_structure

        except Exception as e:
            logger.error(f"Failed to initialize workspace for session {session.id}: {e}")
            # Non-critical - continue without workspace
            return None

    async def mark_deliverable(
        self,
        session_id: str,
        file_path: str
    ) -> None:
        """Mark a file as a deliverable for tracking.

        Args:
            session_id: Session ID
            file_path: Path to deliverable file
        """
        try:
            # This could be extended to track deliverables in session model
            logger.info(f"Deliverable created in session {session_id}: {file_path}")
        except Exception as e:
            logger.warning(f"Failed to mark deliverable: {e}")


# Singleton instance
_initializer: SessionWorkspaceInitializer | None = None


def get_session_workspace_initializer(
    session_repository: SessionRepository
) -> SessionWorkspaceInitializer:
    """Get or create session workspace initializer.

    Args:
        session_repository: Session repository for updates

    Returns:
        SessionWorkspaceInitializer instance
    """
    global _initializer
    if _initializer is None:
        _initializer = SessionWorkspaceInitializer(session_repository)
    return _initializer
