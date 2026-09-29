"""① 探し物（F3）の入口。方式を切り替えて上位 k 件を返す."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Any, Literal, get_args

from dbr.features.search.fts import fts_search
from dbr.features.search.fuse import DEFAULT_K, rrf
from dbr.features.search.vector import NoEmbeddings, vector_search
from dbr.shared.db import connect
from dbr.shared.embed import Embedder
from dbr.shared.rerank import Reranker

Mode = Literal[
    "embed",
    "embed_ctx",
    "fts",
    "hybrid",
    "hybrid_ctx",
    "hybrid_ctx_rerank",
    "embed_ctx_rerank",
]
# embed_ctx: 文脈付き埋め込みだけ（融合なし）。sweep で w_fts=0 が最良だったので追加
# embed_ctx_rerank: 文脈付き埋め込みの候補だけを並べ直す（全文検索を混ぜない。
#   hybrid_ctx_rerank は fts 由来の候補ノイズで Q02/Q06 を落とした＝v5）
MODES: tuple[str, ...] = get_args(Mode)
Agg = Literal["max", "rrf_all", "rrf_top3"]
AGGS: tuple[str, ...] = get_args(Agg)
CANDIDATES = 100  # 各系の一次取得件数（既定）
RERANK_TOP = 150  # hybrid_ctx_rerank: 並べ直しに渡す融合上位の件数
# embed_ctx_rerank: 並べ直す埋め込み候補の件数。v8 tune（集約 rrf_top3）では 20〜50 が
# recall@5 1.00 で、20 が MRR 最良（0.803）。max 集約では 10/15 が Q08 を窓に入れず、
# 30 以上で Q06 を落とした。N=10 なので暫定（D-14）
RERANK_TOP_EMBED = 20
# 断片→文書の集約（rrf_*）に使う断片数。集約は下位断片の和を足すので、少ない断片で
# 計算すると順位が変わる（受入検証 R4(a)・2026-09-29）。bench と ask で同じ値を使う
AGG_CHUNKS = 500


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    bundle: str
    rel_path: str
    heading_path: str
    body: str
    score: float
    source: str  # 'fts' | 'embed' | 'both' | 'rerank'
    context: str | None = None

    @property
    def doc_key(self) -> str:
        return f"{self.bundle}/{self.rel_path}"


def _hit(row: dict[str, Any], source: str, score: float | None = None) -> Hit:
    ctx = row.get("context")
    return Hit(
        chunk_id=int(str(row["chunk_id"])),
        bundle=str(row["bundle"]),
        rel_path=str(row["rel_path"]),
        heading_path=str(row["heading_path"]),
        body=str(row["body"]),
        score=float(score if score is not None else row["score"]),
        source=source,
        context=str(ctx) if ctx is not None else None,
    )


def aggregate_by_document(hits: list[Hit], method: str = "max") -> list[Hit]:
    """断片の順位列を文書の順位列にする（順位ベース・モード非依存・決定的）.

    - max: 最良断片の順位（dedupe_by_document と同値）
    - rrf_all: 文書スコア = Σ_{その文書の全断片} 1/(60 + 断片順位)
    - rrf_top3: 同じ和を文書ごとの上位 3 断片まで
    返す Hit は代表＝最良断片。score は max なら断片スコアのまま、rrf 系は文書スコア。
    同点は最良断片の順位が小さい方が先（安定）。
    """
    if method not in AGGS:
        raise ValueError(f"agg は {AGGS} のいずれか")
    if method == "max":
        return dedupe_by_document(hits)
    limit = 3 if method == "rrf_top3" else None
    best: dict[str, Hit] = {}
    best_rank: dict[str, int] = {}
    score: dict[str, float] = {}
    count: dict[str, int] = {}
    for rank, h in enumerate(hits, start=1):
        key = h.doc_key
        if key not in best:
            best[key] = h
            best_rank[key] = rank
        n = count.get(key, 0)
        if limit is None or n < limit:
            score[key] = score.get(key, 0.0) + 1.0 / (DEFAULT_K + rank)
            count[key] = n + 1
    order = sorted(best, key=lambda d: (-score[d], best_rank[d]))
    return [replace(best[d], score=score[d]) for d in order]


def dedupe_by_document(hits: list[Hit]) -> list[Hit]:
    """同じ文書の最良チャンクだけ残す（文書単位の順位を測るため）＝aggregate の max."""
    seen: set[str] = set()
    out: list[Hit] = []
    for h in hits:
        if h.doc_key in seen:
            continue
        seen.add(h.doc_key)
        out.append(h)
    return out


def _fuse(
    frows: list[dict[str, Any]],
    vrows: list[dict[str, Any]],
    weights: tuple[float, float] | None,
) -> list[Hit]:
    by_id: dict[int, dict[str, Any]] = {}
    src: dict[int, set[str]] = {}
    for r in frows:
        cid = int(str(r["chunk_id"]))
        by_id[cid] = r
        src.setdefault(cid, set()).add("fts")
    for r in vrows:
        cid = int(str(r["chunk_id"]))
        by_id.setdefault(cid, r)
        src.setdefault(cid, set()).add("embed")
    fused = rrf(
        [
            [int(str(r["chunk_id"])) for r in frows],
            [int(str(r["chunk_id"])) for r in vrows],
        ],
        weights=weights,
    )
    return [
        _hit(by_id[cid], "both" if len(src[cid]) == 2 else next(iter(src[cid])), score)
        for cid, score in fused
    ]


def _rerank(question: str, hits: list[Hit], reranker: Reranker, top: int) -> list[Hit]:
    head = hits[:top]
    texts = [f"{h.context}\n{h.body}" if h.context else h.body for h in head]
    scores = reranker.score(question, texts)
    # スコア降順・同点は chunk_id 昇順（決定性）
    order = sorted(
        zip(head, scores, strict=True), key=lambda hs: (-hs[1], hs[0].chunk_id)
    )
    reranked = [
        Hit(
            h.chunk_id,
            h.bundle,
            h.rel_path,
            h.heading_path,
            h.body,
            float(s),
            "rerank",
            h.context,
        )
        for h, s in order
    ]
    # 並べ直しの対象外（top 以降）は融合順のまま後ろに残す。k > top でも k 件返せる
    return reranked + hits[top:]


def search(
    question: str,
    *,
    mode: Mode,
    dsn: str,
    k: int = 20,
    embedder: Embedder | None = None,
    ef_search: int = 40,
    bundles: list[str] | None = None,
    candidates: int | None = None,
    weights: tuple[float, float] | None = None,
    reranker: Reranker | None = None,
    rerank_top: int | None = None,
    force_index: bool = False,
) -> list[Hit]:
    """方式ごとに検索する.

    - candidates: hybrid 系の各系一次取得件数（既定 max(100, k)）
    - weights: RRF の (fts, embed) 重み。既定は等重み
    - reranker / rerank_top: 並べ直し器と対象件数。rerank_top 省略時はモード別既定
      （hybrid_ctx_rerank=RERANK_TOP=150、embed_ctx_rerank=RERANK_TOP_EMBED=20）
    - force_index: ベクトル検索で HNSW 索引を強制（ef_search 実験用）
    """
    if mode not in MODES:
        raise ValueError(f"mode は {MODES} のいずれか")
    n_cand = candidates if candidates is not None else max(CANDIDATES, k)
    if rerank_top is None:
        rerank_top = RERANK_TOP_EMBED if mode == "embed_ctx_rerank" else RERANK_TOP
    if rerank_top <= 0:
        raise ValueError("rerank_top は正の整数")
    conn = connect(dsn)
    with conn:
        if mode == "fts":
            rows = fts_search(conn, question, limit=k, bundles=bundles)
            return [_hit(r, "fts") for r in rows]
        if embedder is None:
            raise ValueError("embed / hybrid には embedder が必要")
        variant = "plain" if mode in ("embed", "hybrid") else "ctx"
        if mode in ("embed", "embed_ctx"):
            limit = k
        elif mode == "embed_ctx_rerank":
            limit = max(rerank_top, k)  # 並べ直す候補は埋め込みだけから取る
        else:
            limit = n_cand
        vrows = vector_search(
            conn,
            question,
            embedder=embedder,
            variant=variant,
            limit=limit,
            ef_search=ef_search,
            bundles=bundles,
            force_index=force_index,
        )
        if mode in ("embed", "embed_ctx"):
            return [_hit(r, "embed") for r in vrows]
        if mode == "embed_ctx_rerank":
            if reranker is None:
                raise ValueError("embed_ctx_rerank には reranker が必要")
            embed_hits = [_hit(r, "embed") for r in vrows]
            return _rerank(question, embed_hits, reranker, rerank_top)[:k]
        frows = fts_search(conn, question, limit=n_cand, bundles=bundles)
    fused = _fuse(frows, vrows, weights)
    if mode == "hybrid_ctx_rerank":
        if reranker is None:
            raise ValueError("hybrid_ctx_rerank には reranker が必要")
        return _rerank(question, fused, reranker, rerank_top)[:k]
    return fused[:k]


__all__ = [
    "AGGS",
    "AGG_CHUNKS",
    "CANDIDATES",
    "MODES",
    "RERANK_TOP",
    "RERANK_TOP_EMBED",
    "Hit",
    "Mode",
    "NoEmbeddings",
    "aggregate_by_document",
    "dedupe_by_document",
    "search",
]
