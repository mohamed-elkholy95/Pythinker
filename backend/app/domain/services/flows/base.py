from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator

from app.domain.models.event import BaseEvent


class BaseFlow(ABC):

    @abstractmethod
    def run(self) -> AsyncGenerator[BaseEvent, None]:
        pass

    @abstractmethod
    def is_done(self) -> bool:
        pass
