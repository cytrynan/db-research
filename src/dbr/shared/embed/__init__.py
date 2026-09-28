"""埋め込みの入口。実装はローカルモデルだけ（D-13）。外部 API 実装は存在しない."""

from __future__ import annotations

from typing import Protocol

DEFAULT_MODEL = "intfloat/multilingual-e5-small"
FAKE_MODEL = "fake"
DIMS = 384  # migrations/0007 の vector(384) と一致させる


class EmbedderUnavailable(Exception):
    """モデルが読み込めない（未取得・依存不足・次元不一致）."""


class Embedder(Protocol):
    name: str
    dims: int

    def embed_passages(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def get_embedder(name: str = DEFAULT_MODEL) -> Embedder:
    """名前から実装を返す。`fake` は決定的ダミー（テスト・DB 側の検証用）."""
    if name == FAKE_MODEL:
        from dbr.shared.embed.fake import FakeEmbedder

        return FakeEmbedder()
    from dbr.shared.embed.local import LocalE5

    emb = LocalE5(name)
    if emb.dims != DIMS:
        raise EmbedderUnavailable(
            f"{name} は {emb.dims} 次元。スキーマは vector({DIMS}) なので使えません"
        )
    return emb


__all__ = [
    "DEFAULT_MODEL",
    "DIMS",
    "FAKE_MODEL",
    "Embedder",
    "EmbedderUnavailable",
    "get_embedder",
]
