"""Feature Flags for Agent Enhancement Rollout

Provides feature flags for gradual rollout of agent enhancements.
All flags default to False for safe deployment.

Usage:
    from app.core.feature_flags import get_feature_flags
    from fastapi import Depends

    async def endpoint(flags: Annotated[FeatureFlags, Depends(get_feature_flags)]):
        if flags.response_recovery_policy:
            # Use recovery policy
            pass

Environment Variables:
    FEATURE_response_recovery_policy=true
    FEATURE_failure_snapshot=true
    FEATURE_tool_arg_canonicalization=true
    FEATURE_duplicate_query_suppression=true
    FEATURE_tool_definition_cache=true
"""

import logging
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class FeatureFlags(BaseSettings):
    """Feature flags for gradual rollout of agent enhancements.

    All flags default to False for safety. Enable via environment variables
    with FEATURE_ prefix.
    """

    # Workstream A: Response Recovery Policy
    response_recovery_policy: bool = False

    # Workstream B: Failure Snapshot
    failure_snapshot: bool = False

    # Workstream C: Tool Argument Canonicalization
    tool_arg_canonicalization: bool = False

    # Workstream D: Duplicate Query Suppression
    duplicate_query_suppression: bool = False

    # Workstream E: Tool Definition Cache
    tool_definition_cache: bool = False

    model_config = SettingsConfigDict(
        env_prefix="FEATURE_",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    def log_enabled_features(self) -> None:
        """Log which features are currently enabled."""
        enabled = [name for name, value in self.model_dump().items() if value is True]

        if enabled:
            logger.info(f"Enabled agent enhancement features: {', '.join(enabled)}")
        else:
            logger.info("All agent enhancement features are disabled (default)")


@lru_cache
def get_feature_flags() -> FeatureFlags:
    """Get cached feature flags instance (singleton pattern).

    Returns:
        FeatureFlags: Global feature flags configuration
    """
    flags = FeatureFlags()
    flags.log_enabled_features()
    return flags
