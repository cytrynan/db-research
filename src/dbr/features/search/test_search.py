"""検索のユニット（DB 不要）: RRF の手計算一致・dedupe."""

import math

import pytest

from dbr.features.search import AGGS, Hit, aggregate_by_document, dedupe_by_document
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


class _RecordingReranker:
    """並べ直し器が受け取った文字列を記録するダミー（入力の形を直接観測する）."""

    name = "recording"

    def __init__(self) -> None:
        self.seen: list[list[str]] = []

    def score(self, query: str, passages: list[str]) -> list[float]:
        self.seen.append(passages)
        return [float(len(p)) for p in passages]  # 長い方を上に


def _h(cid: int, doc: str, score: float) -> Hit:
    return Hit(cid, "references", doc, "h", "b", score, "embed")


def test_aggregate_max_equals_dedupe_and_rrf_prefers_many_good_chunks() -> None:
    # A は順位 1 の断片だけ、B は順位 2,3,4 の 3 断片
    hits = [
        _h(1, "a.md", 0.9),
        _h(2, "b.md", 0.8),
        _h(3, "b.md", 0.7),
        _h(4, "b.md", 0.6),
    ]
    assert aggregate_by_document(hits, "max") == dedupe_by_document(hits)
    assert [x.rel_path for x in aggregate_by_document(hits, "max")] == ["a.md", "b.md"]
    # 手計算: A = 1/61 = 0.01639、B = 1/62 + 1/63 + 1/64 = 0.04763 → B が先
    all_ = aggregate_by_document(hits, "rrf_all")
    assert [x.rel_path for x in all_] == ["b.md", "a.md"]
    assert math.isclose(all_[0].score, 1 / 62 + 1 / 63 + 1 / 64)
    assert math.isclose(all_[1].score, 1 / 61)
    assert all_[0].chunk_id == 2  # 代表は最良断片
    top3 = aggregate_by_document(hits, "rrf_top3")
    assert [x.score for x in top3] == [x.score for x in all_]  # B は 3 断片なので同値


def test_aggregate_top3_caps_and_ties_break_by_best_rank() -> None:
    hits = [_h(1, "a.md", 1.0)] + [
        _h(i, "b.md", 1.0) for i in range(2, 7)
    ]  # B は 5 断片
    all_ = aggregate_by_document(hits, "rrf_all")
    top3 = aggregate_by_document(hits, "rrf_top3")
    b_all = next(x for x in all_ if x.rel_path == "b.md").score
    b_top3 = next(x for x in top3 if x.rel_path == "b.md").score
    assert math.isclose(b_all, sum(1 / (60 + r) for r in range(2, 7)))
    assert math.isclose(b_top3, sum(1 / (60 + r) for r in range(2, 5)))
    assert b_all > b_top3  # rrf_all だけ 5,6 位の分が増える
    # 本当の同点: p=順位(3,45)・q=順位(10,30) はどちらも 8/315
    # → 最良断片の順位が小さい p が先
    tie: list[Hit] = []
    for rank in range(1, 46):
        doc = {3: "p.md", 45: "p.md", 10: "q.md", 30: "q.md"}.get(rank, f"f{rank}.md")
        tie.append(_h(rank, doc, 1.0))
    agg = aggregate_by_document(tie, "rrf_all")
    sp = next(x for x in agg if x.rel_path == "p.md")
    sq = next(x for x in agg if x.rel_path == "q.md")
    assert math.isclose(sp.score, sq.score) and math.isclose(sp.score, 8 / 315)
    assert agg.index(sp) < agg.index(sq)
    assert aggregate_by_document([], "rrf_top3") == []
    with pytest.raises(ValueError):
        aggregate_by_document(tie, "mean")
    assert AGGS == ("max", "rrf_all", "rrf_top3")


def test_rerank_input_is_context_plus_body_and_tail_is_kept() -> None:
    from dbr.features.search import _rerank

    hits = [
        Hit(1, "dev", "a.md", "", "b1", 0.9, "both", "c1"),
        Hit(2, "dev", "b.md", "", "body-long-2", 0.8, "fts", None),
        Hit(3, "dev", "c.md", "", "b3", 0.7, "embed", "c3"),
    ]
    rr = _RecordingReranker()
    out = _rerank("q", hits, rr, top=2)
    assert rr.seen == [
        ["c1\nb1", "body-long-2"]
    ]  # context + "\\n" + body / 無ければ body
    assert [h.chunk_id for h in out] == [2, 1, 3]  # 上位 2 件を並べ直し、3 は末尾に残る
    assert [h.source for h in out] == ["rerank", "rerank", "embed"]


def test_weighted_rrf_matches_hand_calculation() -> None:
    # 列A 重み 0.5 / 列B 重み 1.0
    fused = dict(rrf([["x", "y"], ["y", "z"]], k=60, weights=[0.5, 1.0]))
    assert math.isclose(fused["y"], 0.5 / 62 + 1.0 / 61)
    assert math.isclose(fused["x"], 0.5 / 61)
    assert math.isclose(fused["z"], 1.0 / 62)


def test_weighted_rrf_default_equals_unweighted() -> None:
    a = rrf([["x", "y"], ["y", "z"]])
    b = rrf([["x", "y"], ["y", "z"]], weights=[1.0, 1.0])
    assert a == b


def test_weight_zero_drops_single_side_documents() -> None:
    fused = dict(rrf([["only-fts", "y"], ["y"]], weights=[0.0, 1.0]))
    assert "only-fts" not in fused and "y" in fused


def test_weighted_rrf_rejects_bad_weights() -> None:
    with pytest.raises(ValueError):
        rrf([["a"], ["b"]], weights=[1.0])
    with pytest.raises(ValueError):
        rrf([["a"], ["b"]], weights=[1.0, -1.0])
