"""検索指標（純粋関数）。rank は 1 始まり、正解が出なければ None."""

from __future__ import annotations

from collections.abc import Sequence


def recall_at(ranks: Sequence[int | None], k: int) -> float:
    if not ranks:
        return 0.0
    hit = sum(1 for r in ranks if r is not None and r <= k)
    return hit / len(ranks)


def mrr(ranks: Sequence[int | None]) -> float:
    if not ranks:
        return 0.0
    return sum(1.0 / r for r in ranks if r is not None) / len(ranks)


def rank_of(expected: Sequence[str], doc_keys: Sequence[str]) -> int | None:
    """文書キー列（上位順）の中で、正解のどれかが最初に出る順位."""
    wanted = set(expected)
    for i, key in enumerate(doc_keys, start=1):
        if key in wanted:
            return i
    return None
