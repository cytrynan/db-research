"""③ 時点 bench: 正解＝「ファイル一致 ∧ 日付一致」の事実が上位 k 件にあるか."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dbr.features.asof import FactHit, answer_asof
from dbr.features.bench.questions import Question
from dbr.features.bench.report import git_sha
from dbr.shared.embed import Embedder

TOP_K = 3


def is_correct(
    hits: list[FactHit], expected_docs: tuple[str, ...], dates: tuple[str, ...]
) -> bool:
    for h in hits:
        d = h.valid_from.date().isoformat()
        if (not expected_docs or h.doc_key in expected_docs) and (
            not dates or d in dates
        ):
            return True
    return False


def run_asof(
    questions: list[Question],
    *,
    dsn: str,
    k: int = TOP_K,
    embedder: Embedder | None = None,
    repo: Path | None = None,
) -> dict[str, Any]:
    asofs = [q for q in questions if q.kind == "asof"]
    per: list[dict[str, Any]] = []
    for q in asofs:
        # ① 探し物で文書を絞ってから時間で絞る（answer_asof）。CLI の ask と同じ経路
        a = answer_asof(q.text, dsn=dsn, embedder=embedder, k=k)
        at, hits = a.at, a.hits
        per.append(
            {
                "id": q.id,
                "at": at.date().isoformat() if at else None,
                "candidate_docs": a.docs,
                "scope": a.scope,
                "fallback_to_history": a.fallback_to_history,
                "expected": list(q.expected),
                "expected_dates": list(q.dates),
                "hits": [
                    {
                        "doc": h.doc_key,
                        "date": h.valid_from.date().isoformat(),
                        "source": h.valid_source,
                    }
                    for h in hits
                ],
                "correct": is_correct(hits, q.expected, q.dates),
            }
        )
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "kind": "asof",
        "git_sha": git_sha(repo or Path.cwd()),
        "model": embedder.name if embedder else None,
        "k": k,
        "question_count": len(asofs),
        "correct": sum(1 for p in per if p["correct"]),
        "per_question": per,
    }


def asof_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"asof: {result['date']} / git {result['git_sha']} / k={result['k']} / "
        f"N={result['question_count']} / 正解 {result['correct']}",
        "",
        "| # | 時点 | 正解（ファイル・日付） | 上位の事実（日付 / ファイル） | 判定 |",
        "|---|---|---|---|---|",
    ]
    for p in result["per_question"]:
        exp = ", ".join(p["expected"]) + " / " + ", ".join(p["expected_dates"])
        hits = "<br>".join(f"{h['date']} {h['doc']}" for h in p["hits"]) or "-"
        lines.append(
            f"| {p['id']} | {p['at'] or '履歴'} | {exp} | {hits} | "
            f"{'○' if p['correct'] else '×'} |"
        )
    return "\n".join(lines)
