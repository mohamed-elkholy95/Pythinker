from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from enum import Enum

from app.domain.models.event import BaseEvent


class FlowStatus(str, Enum):
    """Canonical flow lifecycle states."""

    IDLE = "idle"  # Created but not yet started
    PLANNING = "planning"  # Generating or refining a plan
    EXECUTING = "executing"  # Running plan steps
    VERIFYING = "verifying"  # Checking step/plan results
    REFLECTING = "reflecting"  # Self-evaluating quality
    SUMMARIZING = "summarizing"  # Building final response
    COMPLETED = "completed"  # Finished successfully
    FAILED = "failed"  # Terminated with error


class BaseFlow(ABC):
    """Abstract base for all execution flows (FlowEngine interface).

    Every flow must implement:
      - run() → yields events as the flow progresses
      - is_done() → whether the flow has finished
      - get_status() → current lifecycle status
    """

    @abstractmethod
    def run(self) -> AsyncGenerator[BaseEvent, None]:
        pass

    @abstractmethod
    def is_done(self) -> bool:
        pass

    def get_status(self) -> FlowStatus:
        """Current lifecycle status. Override for finer-grained reporting."""
        return FlowStatus.COMPLETED if self.is_done() else FlowStatus.IDLE
