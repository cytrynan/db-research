"""並べ直し（reranking）の入口。実装はローカル cross-encoder だけ（外部 API は無い）."""

from __future__ import annotations

from typing import Protocol

DEFAULT_RERANKER = "cross-encoder/mmarco-mMiniLMv2-L12-H384-v1"
FAKE_RERANKER = "fake"


class RerankerUnavailable(Exception):
    """モデルが読み込めない（未取得・依存不足）."""


class Reranker(Protocol):
    name: str

    def score(self, query: str, passages: list[str]) -> list[float]: ...


def get_reranker(name: str = DEFAULT_RERANKER) -> Reranker:
    if name == FAKE_RERANKER:
        from dbr.shared.rerank.fake import FakeReranker

        return FakeReranker()
    from dbr.shared.rerank.local import LocalCrossEncoder

    return LocalCrossEncoder(name)


__all__ = [
    "DEFAULT_RERANKER",
    "FAKE_RERANKER",
    "Reranker",
    "RerankerUnavailable",
    "get_reranker",
]
