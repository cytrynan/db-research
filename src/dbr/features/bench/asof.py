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
    """上位 k 件に「ファイル一致 ∧ 日付一致」の事実があるか.

    期待のファイルか日付が空なら**不正解**（正解が定義されていない問いは通さない）。
    以前は空側を「何でも一致」にしていたので、期待欄の書き漏れがそのまま正解に
    数えられた（受入検証 D5・2026-09-29）。
    """
    if not expected_docs or not dates:
        return False
    return any(
        h.doc_key in expected_docs and h.valid_from.date().isoformat() in dates
        for h in hits
    )


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
                "n_candidate_chunks": len(a.chunks),
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
