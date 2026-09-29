"""RRF の重み（fts 側）× 候補数のグリッド掃引（hybrid_ctx）."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dbr.features.bench.metrics import mrr, rank_of, recall_at
from dbr.features.bench.questions import Question
from dbr.features.bench.report import git_sha
from dbr.features.search import Mode, dedupe_by_document, search
from dbr.shared.embed import Embedder
from dbr.shared.text import dict_version

WEIGHTS: tuple[float, ...] = (0.0, 0.25, 0.5, 1.0)
CANDIDATES: tuple[int, ...] = (20, 100, 500)
DOC_K = 20
CHUNK_K = 500


def grid(
    weights: tuple[float, ...] = WEIGHTS, cands: tuple[int, ...] = CANDIDATES
) -> list[tuple[float, int]]:
    return [(w, c) for w in weights for c in cands]


def run_sweep(
    questions: list[Question],
    *,
    dsn: str,
    embedder: Embedder,
    mode: Mode = "hybrid_ctx",
    ef_search: int = 40,
    weights: tuple[float, ...] = WEIGHTS,
    cands: tuple[int, ...] = CANDIDATES,
    repo: Path | None = None,
) -> dict[str, Any]:
    finds = [q for q in questions if q.kind == "find" and q.expected]
    cells: list[dict[str, Any]] = []
    for w, c in grid(weights, cands):
        ranks: dict[str, int | None] = {}
        for q in finds:
            hits = dedupe_by_document(
                search(
                    q.text,
                    mode=mode,
                    dsn=dsn,
                    k=CHUNK_K,
                    embedder=embedder,
                    ef_search=ef_search,
                    candidates=c,
                    weights=(w, 1.0),
                )
            )[:DOC_K]
            ranks[q.id] = rank_of(q.expected, [h.doc_key for h in hits])
        rs = list(ranks.values())
        cells.append(
            {
                "w_fts": w,
                "candidates": c,
                "recall@5": recall_at(rs, 5),
                "recall@20": recall_at(rs, 20),
                "mrr": mrr(rs),
                "ranks": ranks,
            }
        )
    best = max(cells, key=lambda x: (x["mrr"], x["recall@5"], x["recall@20"]))
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "kind": "sweep",
        "git_sha": git_sha(repo or Path.cwd()),
        "model": embedder.name,
        "sudachi_dict": dict_version(),
        "mode": mode,
        "w_embed": 1.0,
        "question_count": len(finds),
        "cells": cells,
        "best": {"w_fts": best["w_fts"], "candidates": best["candidates"]},
    }


def sweep_markdown(result: dict[str, Any]) -> str:
    cells: list[dict[str, Any]] = result["cells"]
    ws = sorted({c["w_fts"] for c in cells})
    cs = sorted({c["candidates"] for c in cells})
    lines = [
        f"sweep: {result['date']} / git {result['git_sha']} / {result['mode']} / "
        f"w_embed=1.0 / N={result['question_count']}"
        "（セル＝recall@5 / recall@20 / MRR）",
        "",
        "| w_fts \\ candidates | " + " | ".join(str(c) for c in cs) + " |",
        "|---|" + "---|" * len(cs),
    ]
    by = {(c["w_fts"], c["candidates"]): c for c in cells}
    for w in ws:
        row = [
            f"{by[(w, c)]['recall@5']:.2f} / {by[(w, c)]['recall@20']:.2f} / "
            f"{by[(w, c)]['mrr']:.3f}"
            for c in cs
        ]
        lines.append(f"| {w} | " + " | ".join(row) + " |")
    b = result["best"]
    lines.append(
        f"\n最良（MRR→recall@5→recall@20）: w_fts={b['w_fts']}, "
        f"candidates={b['candidates']}"
    )
    return "\n".join(lines)
