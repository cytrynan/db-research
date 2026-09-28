"""RRF（Reciprocal Rank Fusion）。尺度の違う順位列を正規化なしで統合する純粋関数.

score(doc) = Σ_i 1 / (k + rank_i(doc))
（rank は 1 始まり。片側に無い文書はその項を持たない）
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence

DEFAULT_K = 60


def rrf[K: Hashable](
    rankings: Sequence[Sequence[K]], *, k: int = DEFAULT_K
) -> list[tuple[K, float]]:
    """複数の順位列（各列は上位から並んだキーの列）を統合し、スコア降順で返す."""
    if k <= 0:
        raise ValueError("k は正の整数")
    scores: dict[K, float] = {}
    for ranking in rankings:
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + 1.0 / (k + rank)
    # 同点は先に現れた順（安定ソート）
    return sorted(scores.items(), key=lambda kv: -kv[1])
