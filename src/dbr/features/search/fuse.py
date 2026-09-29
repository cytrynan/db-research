"""RRF（Reciprocal Rank Fusion）。尺度の違う順位列を正規化なしで統合する純粋関数.

score(doc) = Σ_i w_i / (k + rank_i(doc))
（rank は 1 始まり。片側に無い文書はその項を持たない。w は列ごとの重み・既定 1.0）
"""

from __future__ import annotations

from collections.abc import Hashable, Sequence

DEFAULT_K = 60


def rrf[K: Hashable](
    rankings: Sequence[Sequence[K]],
    *,
    k: int = DEFAULT_K,
    weights: Sequence[float] | None = None,
) -> list[tuple[K, float]]:
    """複数の順位列（各列は上位から並んだキーの列）を統合し、スコア降順で返す.

    weights 省略時は等重み（従来と同値）。重み 0 の列だけに出る文書は含めない。
    """
    if k <= 0:
        raise ValueError("k は正の整数")
    ws = [1.0] * len(rankings) if weights is None else list(weights)
    if len(ws) != len(rankings):
        raise ValueError("weights の長さは rankings と同じ")
    if any(w < 0 for w in ws):
        raise ValueError("weights は非負")
    scores: dict[K, float] = {}
    for w, ranking in zip(ws, rankings, strict=True):
        if w == 0:
            continue
        for rank, key in enumerate(ranking, start=1):
            scores[key] = scores.get(key, 0.0) + w / (k + rank)
    # 同点は先に現れた順（安定ソート）
    return sorted(scores.items(), key=lambda kv: -kv[1])
