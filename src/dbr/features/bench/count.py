"""② 数える bench: 質問→ビューで答え、3 回同値（stable）と正解ビュー一致を記録.

受入検証（2026-09-29）で「stable だけでは選んだビューの正しさを測らない」と
指摘され、期待欄の `v_xxx` との照合（view_ok）を足した。期待が無い問いは
view_ok=None（正解扱いにしない）。
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dbr.features.bench.questions import Question
from dbr.features.bench.report import git_sha
from dbr.features.count import UnknownAggregate, ask_view, guess_view


def run_count(
    questions: list[Question], *, dsn: str, repeats: int = 3, repo: Path | None = None
) -> dict[str, Any]:
    counts = [q for q in questions if q.kind == "count"]
    per: list[dict[str, Any]] = []
    for q in counts:
        view = guess_view(q.text)
        if view is None:
            per.append(
                {"id": q.id, "view": None, "stable": False, "error": "ビュー未決"}
            )
            continue
        try:
            runs = [ask_view(view, dsn) for _ in range(repeats)]
        except UnknownAggregate as exc:
            per.append({"id": q.id, "view": view, "stable": False, "error": str(exc)})
            continue
        stable = all(r == runs[0] for r in runs)
        expected_view = q.views[0] if q.views else None
        per.append(
            {
                "id": q.id,
                "view": view,
                "expected_view": expected_view,
                "view_ok": (view == expected_view) if expected_view else None,
                "stable": stable,
                "rows": runs[0],
            }
        )
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "kind": "count",
        "git_sha": git_sha(repo or Path.cwd()),
        "repeats": repeats,
        "question_count": len(counts),
        "all_stable": all(p["stable"] for p in per) if per else False,
        "all_views_ok": all(p.get("view_ok") is True for p in per) if per else False,
        "per_question": per,
    }


def count_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"count: {result['date']} / git {result['git_sha']} / "
        f"repeats={result['repeats']} / N={result['question_count']} / "
        f"all_stable={result['all_stable']} / all_views_ok={result['all_views_ok']}",
        "",
        "| # | ビュー | 正解ビュー | 一致 | 3回同値 | 行数 |",
        "|---|---|---|---|---|---|",
    ]
    for p in result["per_question"]:
        rows = p.get("rows")
        ok = p.get("view_ok")
        mark = "○" if ok else ("×" if ok is False else "?")
        lines.append(
            f"| {p['id']} | {p['view'] or '-'} | {p.get('expected_view') or '-'} | "
            f"{mark} | {p['stable']} | "
            f"{len(rows) if rows is not None else p.get('error', '-')} |"
        )
    return "\n".join(lines)
