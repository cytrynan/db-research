"""HNSW の ef_search 実験。索引を強制し、厳密結果との一致率とレイテンシを測る.

- 質問ベクトルは 1 回だけ計算し、DB 側だけの時間を測る（埋め込み時間を含めない）
- 各測定は REPEATS 回の中央値、質問間も中央値（外れ値に強い）
"""

from __future__ import annotations

import statistics
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from dbr.features.bench.questions import Question
from dbr.features.bench.report import git_sha
from dbr.features.search.vector import (
    explain_vector_search,
    vector_literal,
    vector_search_vec,
)
from dbr.shared.db import connect
from dbr.shared.embed import Embedder

EFS: tuple[int, ...] = (40, 100, 250)
REPEATS = 3


def _ids(rows: list[dict[str, Any]]) -> list[int]:
    return [int(str(r["chunk_id"])) for r in rows]


def overlap_at_k(approx: list[int], exact: list[int], k: int) -> float:
    """上位 k の集合一致率（厳密結果を正とした recall@k）."""
    if k <= 0:
        raise ValueError("k は正")
    a, e = set(approx[:k]), set(exact[:k])
    return len(a & e) / k


def _timed(fn: Any) -> tuple[Any, float]:
    t0 = time.perf_counter()
    out = fn()
    return out, (time.perf_counter() - t0) * 1000.0


def run_hnsw(
    questions: list[Question],
    *,
    dsn: str,
    embedder: Embedder,
    variant: str = "plain",
    k: int = 20,
    efs: tuple[int, ...] = EFS,
    repeats: int = REPEATS,
    repo: Path | None = None,
) -> dict[str, Any]:
    finds = [q for q in questions if q.kind == "find"]
    qvecs = {q.id: vector_literal(embedder.embed_query(q.text)) for q in finds}
    conn = connect(dsn)
    result: dict[str, Any] = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "kind": "hnsw",
        "git_sha": git_sha(repo or Path.cwd()),
        "model": embedder.name,
        "variant": variant,
        "k": k,
        "repeats": repeats,
        "question_count": len(finds),
    }
    with conn:
        exact: dict[str, list[int]] = {}
        exact_lat: list[float] = []
        for q in finds:
            lats = []
            for _ in range(repeats):
                rows, ms = _timed(
                    lambda qid=q.id: vector_search_vec(
                        conn,
                        qvecs[qid],
                        variant=variant,
                        model=embedder.name,
                        limit=k,
                        force_index=False,
                    )
                )
                lats.append(ms)
            exact[q.id] = _ids(rows)
            exact_lat.append(statistics.median(lats))
        result["exact"] = {"latency_ms_median": statistics.median(exact_lat)}

        per_ef: list[dict[str, Any]] = []
        for ef in efs:
            recalls: list[float] = []
            lat_medians: list[float] = []
            for q in finds:
                lats = []
                for _ in range(repeats):
                    rows, ms = _timed(
                        lambda qid=q.id, e=ef: vector_search_vec(
                            conn,
                            qvecs[qid],
                            variant=variant,
                            model=embedder.name,
                            limit=k,
                            ef_search=e,
                            force_index=True,
                        )
                    )
                    lats.append(ms)
                recalls.append(overlap_at_k(_ids(rows), exact[q.id], k))
                lat_medians.append(statistics.median(lats))
            per_ef.append(
                {
                    "ef_search": ef,
                    f"recall@{k}_vs_exact": statistics.fmean(recalls),
                    "latency_ms_median": statistics.median(lat_medians),
                }
            )
        result["ef"] = per_ef
        first = qvecs[finds[0].id] if finds else None
        if first is not None:
            result["explain_default"] = explain_vector_search(
                conn, first, variant=variant, model=embedder.name, limit=k
            )
            result["explain_forced"] = explain_vector_search(
                conn,
                first,
                variant=variant,
                model=embedder.name,
                limit=k,
                force_index=True,
            )
            result["index_used_when_forced"] = "Index Scan" in result["explain_forced"]
    return result


def hnsw_markdown(result: dict[str, Any]) -> str:
    k = result["k"]
    lines = [
        f"hnsw: {result['date']} / git {result['git_sha']} / {result['model']} / "
        f"variant={result['variant']} / k={k} / repeats={result['repeats']} / "
        f"N={result['question_count']}",
        "厳密（Seq Scan）の中央値レイテンシ: "
        f"{result['exact']['latency_ms_median']:.1f} ms",
        f"強制時に索引が使われたか: {result.get('index_used_when_forced')}",
        "",
        f"| ef_search | recall@{k}（厳密比） | 中央値レイテンシ ms |",
        "|---|---|---|",
    ]
    for e in result["ef"]:
        lines.append(
            f"| {e['ef_search']} | {e[f'recall@{k}_vs_exact']:.3f} | "
            f"{e['latency_ms_median']:.1f} |"
        )
    return "\n".join(lines)
