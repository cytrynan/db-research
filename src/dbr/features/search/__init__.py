"""① 探し物（F3）の入口。方式を切り替えて上位 k 件を返す."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, get_args

from dbr.features.search.fts import fts_search
from dbr.features.search.fuse import rrf
from dbr.features.search.vector import NoEmbeddings, vector_search
from dbr.shared.db import connect
from dbr.shared.embed import Embedder
from dbr.shared.rerank import Reranker

Mode = Literal[
    "embed", "embed_ctx", "fts", "hybrid", "hybrid_ctx", "hybrid_ctx_rerank"
]  # fmt: skip
# embed_ctx: 文脈付き埋め込みだけ（融合なし）。sweep で w_fts=0 が最良だったので追加
MODES: tuple[str, ...] = get_args(Mode)
CANDIDATES = 100  # 各系の一次取得件数（既定）
RERANK_TOP = 150  # 並べ直しに渡す融合上位の件数


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


def dedupe_by_document(hits: list[Hit]) -> list[Hit]:
    """同じ文書の最良チャンクだけ残す（文書単位の順位を測るため）."""
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
    return [
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
    rerank_top: int = RERANK_TOP,
    force_index: bool = False,
) -> list[Hit]:
    """方式ごとに検索する.

    - candidates: hybrid 系の各系一次取得件数（既定 max(100, k)）
    - weights: RRF の (fts, embed) 重み。既定は等重み
    - reranker / rerank_top: hybrid_ctx_rerank で使う並べ直し器と対象件数
    - force_index: ベクトル検索で HNSW 索引を強制（ef_search 実験用）
    """
    if mode not in MODES:
        raise ValueError(f"mode は {MODES} のいずれか")
    n_cand = candidates if candidates is not None else max(CANDIDATES, k)
    conn = connect(dsn)
    with conn:
        if mode == "fts":
            rows = fts_search(conn, question, limit=k, bundles=bundles)
            return [_hit(r, "fts") for r in rows]
        if embedder is None:
            raise ValueError("embed / hybrid には embedder が必要")
        variant = "plain" if mode in ("embed", "hybrid") else "ctx"
        embed_only = mode in ("embed", "embed_ctx")
        vrows = vector_search(
            conn,
            question,
            embedder=embedder,
            variant=variant,
            limit=k if embed_only else n_cand,
            ef_search=ef_search,
            bundles=bundles,
            force_index=force_index,
        )
        if embed_only:
            return [_hit(r, "embed") for r in vrows]
        frows = fts_search(conn, question, limit=n_cand, bundles=bundles)
    fused = _fuse(frows, vrows, weights)
    if mode == "hybrid_ctx_rerank":
        if reranker is None:
            raise ValueError("hybrid_ctx_rerank には reranker が必要")
        return _rerank(question, fused, reranker, rerank_top)[:k]
    return fused[:k]


__all__ = [
    "CANDIDATES",
    "MODES",
    "RERANK_TOP",
    "Hit",
    "Mode",
    "NoEmbeddings",
    "dedupe_by_document",
    "search",
]
