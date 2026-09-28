"""検索のユニット（DB 不要）: RRF の手計算一致・dedupe."""

import math

import pytest

from dbr.features.search import Hit, dedupe_by_document
from dbr.features.search.fuse import rrf


def test_rrf_matches_hand_calculation() -> None:
    # 列A: x(1位), y(2位) / 列B: y(1位), z(2位) / k=60
    fused = dict(rrf([["x", "y"], ["y", "z"]], k=60))
    assert math.isclose(fused["y"], 1 / 62 + 1 / 61)
    assert math.isclose(fused["x"], 1 / 61)
    assert math.isclose(fused["z"], 1 / 62)
    order = [key for key, _ in rrf([["x", "y"], ["y", "z"]], k=60)]
    assert order == ["y", "x", "z"]  # 両方に出た y が最上位


def test_rrf_single_side_document_kept() -> None:
    fused = dict(rrf([["only-a"], []]))
    assert "only-a" in fused


def test_rrf_rejects_nonpositive_k() -> None:
    with pytest.raises(ValueError):
        rrf([["a"]], k=0)


def _hit(cid: int, rel: str, score: float) -> Hit:
    return Hit(cid, "dev", rel, "", "", score, "fts")


def test_dedupe_keeps_best_chunk_per_document() -> None:
    hits = [
        _hit(1, "a.md", 0.9),
        _hit(2, "a.md", 0.8),
        _hit(3, "b.md", 0.7),
        _hit(4, "a.md", 0.1),
    ]
    deduped = dedupe_by_document(hits)
    assert [h.chunk_id for h in deduped] == [1, 3]
