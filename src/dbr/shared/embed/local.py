"""ローカル埋め込み（sentence-transformers・CPU）。個人データを外へ出さない唯一の経路."""

from __future__ import annotations

from typing import Any

from dbr.shared.embed import EmbedderUnavailable


class LocalE5:
    """multilingual-e5 系。作法どおり文書は `passage: `、質問は `query: ` を前置."""

    def __init__(self, name: str, *, device: str = "cpu") -> None:
        self.name = name
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - 環境依存
            raise EmbedderUnavailable(f"sentence-transformers 未導入: {exc}") from exc
        try:
            self._model: Any = SentenceTransformer(name, device=device)
        except Exception as exc:  # モデル未取得（オフライン）など
            raise EmbedderUnavailable(f"{name} を読み込めません: {exc}") from exc
        # sentence-transformers 6.x で名前が変わった（旧名は FutureWarning）
        getter = getattr(self._model, "get_embedding_dimension", None)
        dims = getter() if getter else self._model.get_sentence_embedding_dimension()
        self.dims = int(dims) if dims else 0

    def _encode(self, texts: list[str]) -> list[list[float]]:
        vectors = self._model.encode(
            texts, batch_size=64, normalize_embeddings=True, show_progress_bar=False
        )
        return [[float(x) for x in v] for v in vectors]

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        return self._encode([f"passage: {t}" for t in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._encode([f"query: {text}"])[0]
