import logging
import os

from app.core.config import get_settings
from app.domain.models.mcp_config import MCPConfig
from app.domain.repositories.mcp_repository import MCPRepository

logger = logging.getLogger(__name__)


class FileMCPRepository(MCPRepository):
    """Repository for MCP config stored in a file"""

    async def get_mcp_config(self) -> MCPConfig:
        """Get the MCP config from the file"""
        file_path = get_settings().mcp_config_path
        if not os.path.exists(file_path):
            return MCPConfig(mcp_servers={})
        try:
            with open(file_path) as file:  # noqa: ASYNC230
                return MCPConfig.model_validate_json(file.read())
        except (OSError, ValueError) as e:
            logger.exception("Error reading MCP config file: %s", e)

        return MCPConfig(mcp_servers={})
