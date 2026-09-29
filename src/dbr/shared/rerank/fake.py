"""決定的なダミー並べ直し。配線のテスト用（意味は見ない）.

スコア＝質問の文字集合と本文の文字集合の共通数。同じ入力には同じ値。
"""

from __future__ import annotations

from dbr.shared.rerank import FAKE_RERANKER


class FakeReranker:
    name = FAKE_RERANKER

    def score(self, query: str, passages: list[str]) -> list[float]:
        q = {ch for ch in query if not ch.isspace()}
        return [float(len(q & set(p))) for p in passages]
