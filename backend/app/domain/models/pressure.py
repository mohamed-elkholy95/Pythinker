"""Canonical PressureLevel enum for token/memory pressure management."""

from enum import Enum


class PressureLevel(str, Enum):
    """Token/memory pressure levels for proactive management.

    Used by both TokenManager and MemoryManager for consistent
    pressure detection and response.
    """

    NORMAL = "normal"  # < 75% - operating normally
    WARNING = "warning"  # 75-85% - consider summarizing
    CRITICAL = "critical"  # 85-95% - begin proactive trimming
    OVERFLOW = "overflow"  # > 95% - force immediate action
