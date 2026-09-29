"""① 探し物 tune: 並べ直し候補数（rerank_top）× 文書集約（agg）の格子を測る.

検索は (mode, rerank_top) ごとに 1 回だけ行い、集約 3 種は同じ断片列に後処理で当てる
（集約は順位だけを見るので、検索結果を共有できる）。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dbr.features.bench.metrics import mrr, rank_of, recall_at
from dbr.features.bench.questions import Question
from dbr.features.bench.report import git_sha
from dbr.features.search import AGG_CHUNKS, AGGS, Mode, aggregate_by_document, search
from dbr.shared.embed import Embedder
from dbr.shared.rerank import Reranker
from dbr.shared.text import dict_version

RERANK_TOPS: tuple[int, ...] = (20, 50, 100, 150)
DOC_K = 20
CHUNK_K = AGG_CHUNKS


def configs(rerank_tops: tuple[int, ...]) -> list[tuple[Mode, int | None]]:
    """embed_ctx（並べ直しなし・1 セル）＋ embed_ctx_rerank × rerank_top."""
    out: list[tuple[Mode, int | None]] = [("embed_ctx", None)]
    out.extend(("embed_ctx_rerank", t) for t in rerank_tops)
    return out


def run_tune(
    questions: list[Question],
    *,
    dsn: str,
    embedder: Embedder,
    reranker: Reranker,
    rerank_tops: tuple[int, ...] = RERANK_TOPS,
    aggs: tuple[str, ...] = AGGS,
    ef_search: int = 40,
    repo: Path | None = None,
) -> dict[str, Any]:
    finds = [q for q in questions if q.kind == "find" and q.expected]
    cells: list[dict[str, Any]] = []
    for mode, top in configs(rerank_tops):
        ranks: dict[str, dict[str, int | None]] = {a: {} for a in aggs}
        for q in finds:
            hits = search(
                q.text,
                mode=mode,
                dsn=dsn,
                k=CHUNK_K,
                embedder=embedder,
                ef_search=ef_search,
                reranker=reranker if top is not None else None,
                rerank_top=top,
            )
            for a in aggs:
                docs = [h.doc_key for h in aggregate_by_document(hits, a)[:DOC_K]]
                ranks[a][q.id] = rank_of(q.expected, docs)
        for a in aggs:
            rl = list(ranks[a].values())
            cells.append(
                {
                    "mode": mode,
                    "rerank_top": top,
                    "agg": a,
                    "recall@5": recall_at(rl, 5),
                    "recall@20": recall_at(rl, 20),
                    "mrr": mrr(rl),
                    "ranks": ranks[a],
                }
            )
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "kind": "tune",
        "git_sha": git_sha(repo or Path.cwd()),
        "model": embedder.name,
        "reranker": reranker.name,
        "sudachi_dict": dict_version(),
        "ef_search": ef_search,
        "question_count": len(finds),
        "rerank_tops": list(rerank_tops),
        "aggs": list(aggs),
        "cells": cells,
    }


def tune_markdown(result: dict[str, Any]) -> str:
    aggs = list(result["aggs"])
    lines = [
        f"tune: {result['date']} / git {result['git_sha']} / model {result['model']} / "
        f"reranker {result['reranker']} / N={result['question_count']}",
        "",
        "| mode / rerank_top | " + " | ".join(f"{a}（r@5 / MRR）" for a in aggs) + " |",
        "|---|" + "---|" * len(aggs),
    ]
    by = {(c["mode"], c["rerank_top"], c["agg"]): c for c in result["cells"]}
    keys = sorted(
        {(c["mode"], c["rerank_top"]) for c in result["cells"]},
        key=lambda mt: (mt[0], -1 if mt[1] is None else int(mt[1])),  # 数値順
    )
    for mode, top in keys:
        row = f"{mode}" + (f" / {top}" if top is not None else "")
        cells = []
        for a in aggs:
            c = by[(mode, top, a)]
            cells.append(f"{c['recall@5']:.2f} / {c['mrr']:.3f}")
        lines.append(f"| {row} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
