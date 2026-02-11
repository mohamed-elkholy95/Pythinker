"""Canonical PressureLevel enum for token/memory pressure management."""

from enum import Enum


class PressureLevel(str, Enum):
    """Token/memory pressure levels for proactive management.

    Used by both TokenManager and MemoryManager for consistent
    pressure detection and response.

    Priority 4: Optimized thresholds for better context utilization.
    """

    NORMAL = "normal"  # < 60% - operating normally
    EARLY_WARNING = "early_warning"  # 60-70% - early notice for planning (new)
    WARNING = "warning"  # 70-80% - consider summarizing
    CRITICAL = "critical"  # 80-90% - begin proactive trimming
    OVERFLOW = "overflow"  # > 90% - force immediate action
