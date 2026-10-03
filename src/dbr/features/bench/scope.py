"""bundle 絞り込み bench: ① の順位と ④ の証拠に scope（none / filter / boost×w）が効くかを測る.

find は mode=embed_ctx・agg=rrf_top3（D-14）に固定し、全 bundle の検索は 1 回だけ行って
boost は後処理で当てる（filter だけ推定 bundle で検索し直す）。overview も同じく質問ごとに
全 bundle 1 回＋filter 1 回。
overview は上位 5 文書のうち期待文書（questions.md の期待欄のパス）が何件入るかと bundle 内訳。
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from dbr.features.bench.metrics import mrr, rank_of, recall_at
from dbr.features.bench.questions import Question
from dbr.features.bench.report import git_sha
from dbr.features.scope import boost_by_bundle, guess_bundles
from dbr.features.search import AGG_CHUNKS, Hit, aggregate_by_document, search
from dbr.shared.embed import Embedder
from dbr.shared.text import dict_version

CELLS: tuple[tuple[str, float], ...] = (
    ("none", 0.0),
    ("filter", 0.0),
    ("boost", 0.5),
    ("boost", 1.0),
    ("boost", 2.0),
)
DOC_K = 20
EVIDENCE_K = 5


def _docs_for_cells(
    question: str, *, dsn: str, embedder: Embedder
) -> tuple[dict[tuple[str, float], list[Hit]], Any]:
    guess = guess_bundles(question)
    base = aggregate_by_document(
        search(question, mode="embed_ctx", dsn=dsn, k=AGG_CHUNKS, embedder=embedder),
        "rrf_top3",
    )
    out: dict[tuple[str, float], list[Hit]] = {}
    for scope, w in CELLS:
        if scope == "none" or not guess.bundles:
            out[(scope, w)] = base
        elif scope == "filter":
            out[(scope, w)] = aggregate_by_document(
                search(
                    question,
                    mode="embed_ctx",
                    dsn=dsn,
                    k=AGG_CHUNKS,
                    embedder=embedder,
                    bundles=guess.bundles,
                ),
                "rrf_top3",
            )
        else:
            out[(scope, w)] = boost_by_bundle(base, guess.bundles, w)
    return out, guess


def run_scope(
    questions: list[Question], *, dsn: str, embedder: Embedder, repo: Path | None = None
) -> dict[str, Any]:
    finds = [q for q in questions if q.kind == "find" and q.expected]
    ovs = [q for q in questions if q.kind == "overview"]
    find_ranks: dict[tuple[str, float], dict[str, int | None]] = {c: {} for c in CELLS}
    guesses: dict[str, dict[str, Any]] = {}
    for q in finds:
        docs, g = _docs_for_cells(q.text, dsn=dsn, embedder=embedder)
        guesses[q.id] = {"bundles": g.bundles, "reason": g.reason}
        for c, ds in docs.items():
            find_ranks[c][q.id] = rank_of(q.expected, [d.doc_key for d in ds[:DOC_K]])
    # overview も検索は質問ごとに 1 回（全 bundle）＋ filter 1 回。セルは同じ結果への後処理
    # （受入検証 R4: セルのループの内側で毎回検索していた。結果は決定的なので数値は同じ）
    ov_docs: dict[str, dict[tuple[str, float], list[Hit]]] = {}
    for q in ovs:
        ov_docs[q.id], g = _docs_for_cells(q.text, dsn=dsn, embedder=embedder)
        guesses[q.id] = {"bundles": g.bundles, "reason": g.reason}
    ov_cells: list[dict[str, Any]] = []
    for scope, w in CELLS:
        per: list[dict[str, Any]] = []
        for q in ovs:
            top = [d.doc_key for d in ov_docs[q.id][(scope, w)][:EVIDENCE_K]]
            per.append(
                {
                    "id": q.id,
                    "expected_in_top5": len(set(top) & set(q.expected)),
                    "expected_total": len(q.expected),
                    "bundles_in_top5": dict(Counter(k.split("/")[0] for k in top)),
                    "top5": top,
                }
            )
        ov_cells.append({"scope": scope, "w": w, "per_question": per})
    find_cells = [
        {
            "scope": scope,
            "w": w,
            "recall@5": recall_at(list(find_ranks[(scope, w)].values()), 5),
            "recall@20": recall_at(list(find_ranks[(scope, w)].values()), 20),
            "mrr": mrr(list(find_ranks[(scope, w)].values())),
            "ranks": find_ranks[(scope, w)],
        }
        for scope, w in CELLS
    ]
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "kind": "scope",
        "git_sha": git_sha(repo or Path.cwd()),
        "model": embedder.name,
        "sudachi_dict": dict_version(),
        "mode": "embed_ctx",
        "agg": "rrf_top3",
        "chunks": AGG_CHUNKS,
        "find_question_count": len(finds),
        "overview_question_count": len(ovs),
        "guesses": guesses,
        "find": find_cells,
        "overview": ov_cells,
    }


def scope_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"scope: {result['date']} / git {result['git_sha']} / model {result['model']} / "
        f"find N={result['find_question_count']} / overview N={result['overview_question_count']}",
        "",
        "| scope / w | recall@5 | recall@20 | MRR | 質問別順位 |",
        "|---|---|---|---|---|",
    ]
    for c in result["find"]:
        ranks = ", ".join(str(c["ranks"][q] or "-") for q in sorted(c["ranks"]))
        label = c["scope"] + (f" / {c['w']}" if c["scope"] == "boost" else "")
        lines.append(
            f"| {label} | {c['recall@5']:.2f} | {c['recall@20']:.2f} | {c['mrr']:.3f} | {ranks} |"
        )
    lines += [
        "",
        "| scope / w | 問 | 期待文書の数（上位 5） | bundle 内訳 |",
        "|---|---|---|---|",
    ]
    for c in result["overview"]:
        label = c["scope"] + (f" / {c['w']}" if c["scope"] == "boost" else "")
        for p in c["per_question"]:
            lines.append(
                f"| {label} | {p['id']} | {p['expected_in_top5']}/{p['expected_total']} | "
                f"{p['bundles_in_top5']} |"
            )
    lines += [
        "",
        "推定 bundle: "
        + "; ".join(f"{q}={v['bundles']}" for q, v in result["guesses"].items()),
    ]
    return "\n".join(lines)
