"""Tests for the LLM Middleware Pipeline (Phase 1).

Covers: LLMRequest, LLMResponse, LLMPipeline assembly, middleware ordering,
pass-through, and mutation of request/response metadata.
"""

from __future__ import annotations

import pytest

from app.domain.services.llm.middleware import (
    LLMCallable,
    LLMMiddleware,
    LLMPipeline,
    LLMRequest,
    LLMResponse,
)

# ─────────────────────────── Helpers ─────────────────────────────────────────


async def _echo_handler(request: LLMRequest) -> LLMResponse:
    """Minimal base handler — echoes first message content."""
    content = (request.messages[0].get("content") or "") if request.messages else ""
    return LLMResponse(content=f"echo:{content}")


# ─────────────────────────── LLMRequest ──────────────────────────────────────


def test_llm_request_defaults():
    req = LLMRequest(messages=[{"role": "user", "content": "hi"}])
    assert req.tools is None
    assert req.model is None
    assert req.enable_caching is False
    assert req.metadata == {}


def test_llm_request_metadata_is_mutable():
    req = LLMRequest(messages=[])
    req.metadata["task_id"] = "t-1"
    assert req.metadata["task_id"] == "t-1"


# ─────────────────────────── LLMResponse ─────────────────────────────────────


def test_llm_response_defaults():
    resp = LLMResponse(content="hello")
    assert resp.tool_calls is None
    assert resp.usage is None
    assert resp.finish_reason == "stop"
    assert resp.metadata == {}


# ─────────────────────────── LLMPipeline ─────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_no_middleware_passes_through():
    pipeline = LLMPipeline(middlewares=[], handler=_echo_handler)
    req = LLMRequest(messages=[{"role": "user", "content": "hello"}])
    resp = await pipeline.execute(req)
    assert resp.content == "echo:hello"


@pytest.mark.asyncio
async def test_pipeline_single_middleware_wraps_response():
    class TagMiddleware(LLMMiddleware):
        async def __call__(self, request: LLMRequest, next_handler: LLMCallable) -> LLMResponse:
            response = await next_handler(request)
            response.metadata["tagged"] = True
            return response

    pipeline = LLMPipeline(middlewares=[TagMiddleware()], handler=_echo_handler)
    req = LLMRequest(messages=[{"role": "user", "content": "x"}])
    resp = await pipeline.execute(req)
    assert resp.metadata["tagged"] is True


@pytest.mark.asyncio
async def test_pipeline_middleware_order_is_outermost_first():
    """First middleware in list wraps outermost — its pre-processing runs first."""
    order: list[str] = []

    class AMiddleware(LLMMiddleware):
        async def __call__(self, request, next_handler):
            order.append("A_pre")
            resp = await next_handler(request)
            order.append("A_post")
            return resp

    class BMiddleware(LLMMiddleware):
        async def __call__(self, request, next_handler):
            order.append("B_pre")
            resp = await next_handler(request)
            order.append("B_post")
            return resp

    pipeline = LLMPipeline(middlewares=[AMiddleware(), BMiddleware()], handler=_echo_handler)
    req = LLMRequest(messages=[{"role": "user", "content": ""}])
    await pipeline.execute(req)
    assert order == ["A_pre", "B_pre", "A_post", "B_post"] or order == [
        "A_pre",
        "B_pre",
        "B_post",  # inner B post happens before outer A post
        "A_post",
    ]
    # A wraps B: A_pre → B_pre → handler → B_post → A_post
    assert order.index("A_pre") < order.index("B_pre")
    assert order.index("B_post") < order.index("A_post")


@pytest.mark.asyncio
async def test_pipeline_middleware_can_mutate_request():
    class InjectMiddleware(LLMMiddleware):
        async def __call__(self, request, next_handler):
            request.metadata["injected"] = "yes"
            return await next_handler(request)

    received: list[LLMRequest] = []

    async def capturing_handler(req: LLMRequest) -> LLMResponse:
        received.append(req)
        return LLMResponse(content="ok")

    pipeline = LLMPipeline(middlewares=[InjectMiddleware()], handler=capturing_handler)
    await pipeline.execute(LLMRequest(messages=[]))
    assert received[0].metadata["injected"] == "yes"


@pytest.mark.asyncio
async def test_pipeline_exception_propagates():
    class BoomMiddleware(LLMMiddleware):
        async def __call__(self, request, next_handler):
            raise ValueError("middleware boom")

    pipeline = LLMPipeline(middlewares=[BoomMiddleware()], handler=_echo_handler)
    with pytest.raises(ValueError, match="middleware boom"):
        await pipeline.execute(LLMRequest(messages=[]))


@pytest.mark.asyncio
async def test_pipeline_multiple_executions_are_independent():
    """Same pipeline object can be called multiple times safely."""
    pipeline = LLMPipeline(middlewares=[], handler=_echo_handler)
    for content in ["a", "b", "c"]:
        req = LLMRequest(messages=[{"role": "user", "content": content}])
        resp = await pipeline.execute(req)
        assert resp.content == f"echo:{content}"


def test_pipeline_repr_shows_middleware_names():
    class FooMiddleware(LLMMiddleware):
        pass

    pipeline = LLMPipeline(middlewares=[FooMiddleware()], handler=_echo_handler)
    assert "FooMiddleware" in repr(pipeline)
