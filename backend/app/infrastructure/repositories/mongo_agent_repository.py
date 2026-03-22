import asyncio
import contextlib
import logging
from datetime import UTC, datetime

from pymongo.errors import ConnectionFailure, OperationFailure

from app.domain.exceptions.base import AgentNotFoundException
from app.domain.models.agent import Agent
from app.domain.models.memory import Memory
from app.domain.repositories.agent_repository import AgentRepository
from app.infrastructure.models.documents import AgentDocument

logger = logging.getLogger(__name__)


class WriteCoalescer:
    """Coalesces rapid writes into single DB operations for better performance"""

    def __init__(self, delay_ms: int = 100):
        self._pending: dict[str, tuple[str, Memory]] = {}  # key -> (agent_id, name, memory)
        self._delay = delay_ms / 1000
        self._task: asyncio.Task | None = None
        self._lock = asyncio.Lock()

    async def schedule_write(self, agent_id: str, name: str, memory: Memory) -> None:
        """Schedule a write, coalescing with any pending writes for the same key"""
        key = f"{agent_id}:{name}"

        async with self._lock:
            self._pending[key] = (agent_id, name, memory)

            # Start flush task if not already running
            if not self._task or self._task.done():
                self._task = asyncio.create_task(self._flush_after_delay())

    async def _flush_after_delay(self) -> None:
        """Wait for delay then flush all pending writes"""
        await asyncio.sleep(self._delay)
        await self._flush_pending()

    async def _flush_pending(self) -> int:
        """Flush all pending writes immediately. Returns count flushed."""
        async with self._lock:
            if not self._pending:
                return 0

            batch = self._pending.copy()
            self._pending.clear()

        # Execute all writes
        for key, (agent_id, name, memory) in batch.items():
            try:
                # model_dump() excludes MemoryConfig (exclude=True) which is a
                # plain dataclass that beanie's BSON encoder cannot serialize.
                memory_dict = memory.model_dump() if hasattr(memory, "model_dump") else memory
                await AgentDocument.find_one(AgentDocument.agent_id == agent_id).update(
                    {"$set": {f"memories.{name}": memory_dict, "updated_at": datetime.now(UTC)}}
                )
            except (ConnectionFailure, OperationFailure) as e:
                logger.warning("Coalesced write failed for %s: %s", key, e)
        return len(batch)

    async def shutdown(self) -> None:
        """Flush pending writes and cancel the background task."""
        if self._task and not self._task.done():
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        flushed = await self._flush_pending()
        logger.info("WriteCoalescer shut down — %d pending writes flushed", flushed)


# Global write coalescer instance
_write_coalescer: WriteCoalescer | None = None


def get_write_coalescer() -> WriteCoalescer:
    """Get or create the global write coalescer"""
    global _write_coalescer
    if _write_coalescer is None:
        from app.core.config import get_settings

        _write_coalescer = WriteCoalescer(delay_ms=get_settings().write_coalescer_delay_ms)
    return _write_coalescer


async def shutdown_write_coalescer() -> None:
    """Shutdown the global write coalescer, flushing pending writes."""
    global _write_coalescer
    if _write_coalescer is not None:
        await _write_coalescer.shutdown()
        _write_coalescer = None


class MongoAgentRepository(AgentRepository):
    """MongoDB implementation of AgentRepository with write coalescing"""

    def __init__(self, use_coalescing: bool = True):
        """Initialize repository with optional write coalescing.

        Args:
            use_coalescing: If True, coalesce rapid memory writes (default: True)
        """
        self._use_coalescing = use_coalescing

    async def save(self, agent: Agent) -> None:
        """Save or update an agent"""
        mongo_agent = await AgentDocument.find_one(AgentDocument.agent_id == agent.id)

        if not mongo_agent:
            mongo_agent = AgentDocument.from_domain(agent)
            await mongo_agent.save()
            return

        # Update fields from agent domain model
        mongo_agent.update_from_domain(agent)
        await mongo_agent.save()

    async def find_by_id(self, agent_id: str) -> Agent | None:
        """Find an agent by its ID"""
        mongo_agent = await AgentDocument.find_one(AgentDocument.agent_id == agent_id)
        return mongo_agent.to_domain() if mongo_agent else None

    async def add_memory(self, agent_id: str, name: str, memory: Memory) -> None:
        """Add or update a memory for an agent"""
        memory_dict = memory.model_dump() if hasattr(memory, "model_dump") else memory
        result = await AgentDocument.find_one(AgentDocument.agent_id == agent_id).update(
            {"$set": {f"memories.{name}": memory_dict, "updated_at": datetime.now(UTC)}}
        )
        if not result:
            raise AgentNotFoundException(agent_id)

    async def get_memory(self, agent_id: str, name: str) -> Memory:
        """Get memory by name from agent, create if not exists"""
        mongo_agent = await AgentDocument.find_one(AgentDocument.agent_id == agent_id)
        if not mongo_agent:
            raise AgentNotFoundException(agent_id)
        return mongo_agent.memories.get(name, Memory(messages=[]))

    async def save_memory(self, agent_id: str, name: str, memory: Memory) -> None:
        """Update the messages of a memory with optional write coalescing"""
        if self._use_coalescing:
            # Use coalesced write for better performance during rapid updates
            await get_write_coalescer().schedule_write(agent_id, name, memory)
        else:
            # Direct write
            memory_dict = memory.model_dump() if hasattr(memory, "model_dump") else memory
            result = await AgentDocument.find_one(AgentDocument.agent_id == agent_id).update(
                {"$set": {f"memories.{name}": memory_dict, "updated_at": datetime.now(UTC)}}
            )
            if not result:
                raise AgentNotFoundException(agent_id)
