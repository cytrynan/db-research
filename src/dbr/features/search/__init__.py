"""① 探し物（F3）の入口。方式を切り替えて上位 k 件を返す."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal, get_args

from dbr.features.search.fts import fts_search
from dbr.features.search.fuse import rrf
from dbr.features.search.vector import NoEmbeddings, vector_search
from dbr.shared.db import connect
from dbr.shared.embed import Embedder

Mode = Literal["embed", "fts", "hybrid", "hybrid_ctx"]
MODES: tuple[str, ...] = get_args(Mode)
CANDIDATES = 100  # 各系の一次取得件数


@dataclass(frozen=True)
class Hit:
    chunk_id: int
    bundle: str
    rel_path: str
    heading_path: str
    body: str
    score: float
    source: str  # 'fts' | 'embed' | 'both'

    @property
    def doc_key(self) -> str:
        return f"{self.bundle}/{self.rel_path}"


def _hit(row: dict[str, Any], source: str, score: float | None = None) -> Hit:
    return Hit(
        chunk_id=int(str(row["chunk_id"])),
        bundle=str(row["bundle"]),
        rel_path=str(row["rel_path"]),
        heading_path=str(row["heading_path"]),
        body=str(row["body"]),
        score=float(score if score is not None else row["score"]),
        source=source,
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


def search(
    question: str,
    *,
    mode: Mode,
    dsn: str,
    k: int = 20,
    embedder: Embedder | None = None,
    ef_search: int = 40,
    bundles: list[str] | None = None,
) -> list[Hit]:
    if mode not in MODES:
        raise ValueError(f"mode は {MODES} のいずれか")
    conn = connect(dsn)
    with conn:
        if mode == "fts":
            rows = fts_search(conn, question, limit=k, bundles=bundles)
            return [_hit(r, "fts") for r in rows]
        if embedder is None:
            raise ValueError("embed / hybrid には embedder が必要")
        variant = "ctx" if mode == "hybrid_ctx" else "plain"
        # 各系の一次取得は k 以上（bench が文書 20 件を確保するため多めに要求してくる）
        candidates = max(CANDIDATES, k)
        vrows = vector_search(
            conn,
            question,
            embedder=embedder,
            variant=variant,
            limit=k if mode == "embed" else candidates,
            ef_search=ef_search,
            bundles=bundles,
        )
        if mode == "embed":
            return [_hit(r, "embed") for r in vrows]
        frows = fts_search(conn, question, limit=candidates, bundles=bundles)
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
        ]
    )
    hits = [
        _hit(by_id[cid], "both" if len(src[cid]) == 2 else next(iter(src[cid])), score)
        for cid, score in fused
    ]
    return hits[:k]


__all__ = [
    "CANDIDATES",
    "MODES",
    "Hit",
    "Mode",
    "NoEmbeddings",
    "dedupe_by_document",
    "search",
]
