"""Self-hosted reranker — REMOVED.

SelfHostedReranker (CrossEncoder) has been replaced by JinaReranker
(API-based, zero ML deps). See:
  backend/app/infrastructure/external/search/jina_reranker.py

This module is kept only for backward-compatible import paths.
"""

from __future__ import annotations

from typing import Any


class _NoopReranker:
    def is_available(self) -> bool:
        return False

    def rerank(
        self,
        query: str,
        candidates: list[tuple[str, dict[str, Any]]],
        top_k: int = 10,
    ) -> list[tuple[str, dict[str, Any], float]]:
        return [(text, meta, 0.5) for text, meta in candidates[:top_k]]


_reranker = _NoopReranker()


def get_reranker() -> _NoopReranker:
    return _reranker
