import pytest

from app.domain.services.flows.graph_checkpoint_manager import GraphCheckpointManager


@pytest.mark.asyncio
async def test_graph_checkpoint_manager_saves_in_memory():
    manager = GraphCheckpointManager()

    assert manager.get_latest("session-1") is None

    saved = await manager.save_checkpoint(
        session_id="session-1",
        node_name="planning",
        iteration=1,
        state={"foo": "bar"},
        execution={"status": "completed"},
    )

    assert saved is not None
    latest = manager.get_latest("session-1")
    assert latest is not None
    assert latest.node_name == "planning"
    assert latest.iteration == 1
