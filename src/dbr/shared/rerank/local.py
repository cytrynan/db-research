"""ローカル cross-encoder（sentence-transformers.CrossEncoder・CPU）."""

from __future__ import annotations

from typing import Any

from dbr.shared.rerank import RerankerUnavailable


class LocalCrossEncoder:
    def __init__(self, name: str, *, device: str = "cpu", batch_size: int = 32) -> None:
        self.name = name
        self.batch_size = batch_size
        try:
            from sentence_transformers import CrossEncoder
        except ImportError as exc:  # pragma: no cover - 環境依存
            raise RerankerUnavailable(f"sentence-transformers 未導入: {exc}") from exc
        try:
            self._model: Any = CrossEncoder(name, device=device)
        except Exception as exc:
            raise RerankerUnavailable(f"{name} を読み込めません: {exc}") from exc

    def score(self, query: str, passages: list[str]) -> list[float]:
        if not passages:
            return []
        pairs = [(query, p) for p in passages]
        out = self._model.predict(
            pairs, batch_size=self.batch_size, show_progress_bar=False
        )
        return [float(x) for x in out]
