"""④ 全体 bench: 自動採点はしない。回答を Markdown に書き出し、K が 5 段階で採点する."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from dbr.features.bench.questions import Question
from dbr.features.bench.report import git_sha
from dbr.features.overview import OverviewAnswer, answer, narrate
from dbr.shared.embed import Embedder
from dbr.shared.llm import LLM


def render_answer(a: OverviewAnswer) -> str:
    # bundle 要約は先頭行（件数・内訳）だけ。文書一覧（数十行）は根拠 id で辿れる
    parts = [
        f"【{b['bundle']}】{b['text'].split(chr(10))[0]}（全文は summary#{b['id']}）"
        for b in a.bundle_summaries
    ]
    if a.doc_summaries:
        parts.append(
            "【質問に近い文書】\n"
            + "\n".join(f"- {d['text']}" for d in a.doc_summaries)
        )
    if a.warnings:
        parts.append("WARN: " + " / ".join(a.warnings))
    return "\n\n".join(parts) or "（要約なし）"


def run_overview(
    questions: list[Question],
    *,
    dsn: str,
    embedder: Embedder | None,
    answers_path: Path,
    repo: Path | None = None,
    llm: LLM | None = None,
) -> dict[str, Any]:
    """抽出型の回答（llm があれば同じ証拠からの LLM 回答も）を K 採点用に書く.

    LLM は 2 回生成して一致（reproducible）を記録する。JSON に本文は入れない。
    """
    ovs = [q for q in questions if q.kind == "overview"]
    per: list[dict[str, Any]] = []
    method = "抽出型（bundle 要約＋上位文書の document 要約）"
    if llm is not None:
        method += f" ＋ LLM 回答（{llm.name}・同じ証拠・貪欲デコード）"
    md = [
        "---",
        "type: Bench Answers",
        "description: ④ 全体 の回答（抽出型要約）。K が 5 段階で採点する欄つき。"
        "自動採点はしない",
        "generated: { by: process:dbr-bench, at: "
        f"{datetime.now().astimezone().isoformat(timespec='seconds')} }}",
        "status: draft",
        "---",
        "",
        "# overview の回答（K 採点用）",
        "",
        f"生成: {datetime.now().strftime('%Y-%m-%d')} / "
        f"git {git_sha(repo or Path.cwd())} / 方式: {method}",
        "",
        "| # | 質問 | 抽出型の回答 | LLM 回答 | 根拠外の言及 | K 採点 抽出型 (1-5) "
        "| K 採点 LLM (1-5) | メモ |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for q in ovs:
        a = answer(q.text, dsn=dsn, embedder=embedder)
        text = render_answer(a)
        row: dict[str, Any] = {
            "id": q.id,
            "bundles": a.bundles,
            "n_bundle_summaries": len(a.bundle_summaries),
            "n_doc_summaries": len(a.doc_summaries),
            "evidence_ids": a.evidence_ids,
            "warnings": a.warnings,
        }
        llm_cell, unsup_cell = "—", "—"
        if llm is not None:
            n1 = narrate(q.text, a, llm)
            n2 = narrate(q.text, a, llm)
            row["llm"] = {
                "model": llm.name,
                "seconds": [n1.seconds, n2.seconds],
                "chars": len(n1.text),
                "unsupported": n1.unsupported,
                "reproducible": n1.text == n2.text,
            }
            llm_cell = n1.text
            unsup_cell = ", ".join(n1.unsupported) or "なし"
            if not row["llm"]["reproducible"]:
                unsup_cell += "（2 回目と不一致）"
        per.append(row)
        cell = text.replace("|", "\\|").replace("\n", "<br>")
        lcell = llm_cell.replace("|", "\\|").replace("\n", "<br>")
        md.append(f"| {q.id} | {q.text} | {cell} | {lcell} | {unsup_cell} |  |  |  |")
    answers_path.parent.mkdir(parents=True, exist_ok=True)
    answers_path.write_text("\n".join(md) + "\n", encoding="utf-8")
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "kind": "overview",
        "git_sha": git_sha(repo or Path.cwd()),
        "model": embedder.name if embedder else None,
        "llm_model": llm.name if llm else None,
        "question_count": len(ovs),
        "answers_file": str(answers_path),
        "per_question": per,
    }


def overview_markdown(result: dict[str, Any]) -> str:
    lines = [
        f"overview: {result['date']} / git {result['git_sha']} / "
        f"N={result['question_count']} / 回答: {result['answers_file']}（K が採点）",
        "",
        "| # | 対象 bundle | bundle 要約 | 文書要約 | 根拠 id 数 "
        "| LLM 秒 | 根拠外 | 2 回一致 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for p in result["per_question"]:
        llm = p.get("llm")
        extra = (
            f"{llm['seconds'][0]} | {len(llm['unsupported'])} | {llm['reproducible']}"
            if llm
            else "— | — | —"
        )
        lines.append(
            f"| {p['id']} | {', '.join(p['bundles'])} | {p['n_bundle_summaries']} | "
            f"{p['n_doc_summaries']} | {len(p['evidence_ids'])} | {extra} |"
        )
    return "\n".join(lines)
