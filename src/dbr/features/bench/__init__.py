"""測定ハーネス（F7）。find 質問を方式ごとに流し、文書単位の順位から指標を出す."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

from dbr.features.bench.metrics import mrr, rank_of, recall_at
from dbr.features.bench.questions import Question, load_questions
from dbr.features.bench.report import git_sha, save_json, to_markdown
from dbr.features.search import Mode, dedupe_by_document, search
from dbr.shared.embed import Embedder
from dbr.shared.text import dict_version

DOC_K = 20  # 文書単位で上位 20 まで見る（recall@20）
# 断片を文書に畳むと件数が減るので、断片は文書 20 件を確実に確保できる数を取る。
# 100 だと上位 100 断片に 20 文書が含まれず 11〜20 位の文書が消えることがある
# （2026-09-29 受入検証で指摘・現データの hybrid Q09 は 16 文書しか残らなかった）
CHUNK_K = 500


def run_find(
    questions: list[Question],
    modes: list[Mode],
    *,
    dsn: str,
    embedder: Embedder | None,
    ef_search: int = 40,
    repo: Path | None = None,
    log: Callable[[str], None] = print,
) -> dict[str, Any]:
    finds = [q for q in questions if q.kind == "find" and q.expected]
    # 正解パスが無い find 行は測れない。黙って母数から外さず、記録に残す
    skipped = [q.id for q in questions if q.kind == "find" and not q.expected]
    for qid in skipped:
        log(
            f"WARN: {qid} は正解パス（バッククォート内の bundle/rel_path.md）が無く除外"
        )
    result: dict[str, Any] = {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "kind": "find",
        "git_sha": git_sha(repo or Path.cwd()),
        "model": embedder.name if embedder else None,
        "sudachi_dict": dict_version(),
        "ef_search": ef_search,
        "question_count": len(finds),
        "skipped": skipped,
        "modes": {},
    }
    for mode in modes:
        per: list[dict[str, Any]] = []
        for q in finds:
            hits = dedupe_by_document(
                search(
                    q.text,
                    mode=mode,
                    dsn=dsn,
                    k=CHUNK_K,
                    embedder=embedder,
                    ef_search=ef_search,
                )
            )[:DOC_K]
            keys = [h.doc_key for h in hits]
            per.append(
                {
                    "id": q.id,
                    "rank": rank_of(q.expected, keys),
                    "expected": list(q.expected),
                    "top5": keys[:5],  # 本文は出さない（パスだけ）
                }
            )
        ranks = [p["rank"] for p in per]
        result["modes"][mode] = {
            "recall@5": recall_at(ranks, 5),
            "recall@20": recall_at(ranks, 20),
            "mrr": mrr(ranks),
            "per_question": per,
        }
    return result


__all__ = ["DOC_K", "load_questions", "run_find", "save_json", "to_markdown"]
