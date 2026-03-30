"""Redis stream queue — benign disconnect classification."""

from app.infrastructure.external.message_queue.redis_stream_queue import _is_benign_redis_xread_disconnect


def test_benign_connection_closed_by_server() -> None:
    assert _is_benign_redis_xread_disconnect("Connection closed by server.")


def test_not_benign_invalid_stream_id() -> None:
    assert not _is_benign_redis_xread_disconnect("Invalid stream ID specified as stream command argument")
