"""`dbr summarize`: 抽出型の要約階層（bundle → document → section）を作る（冪等）.

LLM は使わない。section＝最初の段落、document＝description＋見出し＋メタ、
bundle＝件数＋各文書の 1 行。source_hash で元テキストの陳腐化を検知できる。
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dbr.features.ingest.frontmatter import JST
from dbr.shared.db import connect

FENCE = re.compile(r"^\s*(```|~~~)")


def _today() -> str:
    """要約を作った日（JST）。「期限切れ」はこの日を基準に数える（日付を直書きしない）."""
    return datetime.now(JST).date().isoformat()


BULLET = re.compile(r"^\s*([-*+]|\d+\.)\s+")


@dataclass
class SummarizeReport:
    bundle: str
    sections: int = 0
    documents: int = 0
    bundles: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _h(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# --- source_hash の材料。run_summarize と stale_summaries の両方がこれを使う
# （別実装にしない＝片方だけ変えると陳腐化検知が壊れる）
def top_headings(chunks: Sequence[Mapping[str, Any]]) -> list[str]:
    """断片の heading_path の上 2 段を出現順・重複なしで返す（要約とハッシュの材料）."""
    out: list[str] = []
    for c in chunks:
        top2 = " > ".join(str(c["heading_path"]).split(" > ")[:2])
        if top2 and top2 not in out:
            out.append(top2)
    return out


def doc_source_hash(fm: dict[str, Any], headings: Sequence[str]) -> str:
    return _h(
        json.dumps(fm, ensure_ascii=False, sort_keys=True, default=str)
        + "\n".join(headings)
    )


def bundle_line(rel_path: str, desc: str) -> str:
    return f"- {rel_path}: {desc or '(description なし)'}"


def bundle_source_hash(bundle_lines: Sequence[str]) -> str:
    return _h("\n".join(bundle_lines))


@dataclass(frozen=True)
class StaleSummary:
    bundle: str
    level: str  # 'bundle' | 'document'
    target_key: str
    reason: str  # 'changed'（元テキストが変わった）| 'missing'（要約が無い）


def _compare(
    out: list[StaleSummary],
    stored: Mapping[tuple[str, str], str],
    bundle: str,
    level: str,
    key: str,
    expected: str,
) -> None:
    got = stored.get((level, key))
    if got is None:
        out.append(StaleSummary(bundle, level, key, "missing"))
    elif got != expected:
        out.append(StaleSummary(bundle, level, key, "changed"))


def stale_summaries(
    dsn: str,
    bundles: Sequence[str],
    levels: Sequence[str] = ("bundle", "document"),
) -> list[StaleSummary]:
    """source_hash を要約時と同じ関数で再計算し、違う／無い要約を返す.

    本文は返さない（level と target_key だけ）。

    section レベルは対象外（overview が使わない・断片数ぶんの再計算になる）。
    受入検証（2026-09-29）で「source_hash は保存しているだけ」と指摘された分の回収。
    """
    out: list[StaleSummary] = []
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        for bundle in bundles:
            cur.execute(
                "SELECT id, rel_path, fm FROM document "
                "WHERE bundle = %(b)s ORDER BY rel_path",
                {"b": bundle},
            )
            docs = cur.fetchall()
            cur.execute(
                "SELECT level, target_key, source_hash FROM summary "
                "WHERE (level = 'bundle' AND target_key = %(b)s) "
                "OR (level = 'document' AND target_key = ANY(%(ids)s::text[]))",
                {"b": bundle, "ids": [str(d["id"]) for d in docs]},
            )
            stored = {
                (str(r["level"]), str(r["target_key"])): str(r["source_hash"])
                for r in cur.fetchall()
            }
            bundle_lines: list[str] = []
            for d in docs:
                doc_id = str(d["id"])
                fm = d["fm"] if isinstance(d["fm"], dict) else {}
                bundle_lines.append(
                    bundle_line(str(d["rel_path"]), str(fm.get("description") or ""))
                )
                if "document" in levels:
                    cur.execute(
                        "SELECT heading_path FROM chunk "
                        "WHERE document_id = %(d)s ORDER BY ordinal",
                        {"d": int(doc_id)},
                    )
                    expected = doc_source_hash(fm, top_headings(cur.fetchall()))
                    _compare(out, stored, bundle, "document", doc_id, expected)
            if "bundle" in levels:
                _compare(
                    out,
                    stored,
                    bundle,
                    "bundle",
                    bundle,
                    bundle_source_hash(bundle_lines),
                )
    return out


def first_paragraph(body: str, limit: int = 200) -> str:
    """コードフェンスを飛ばし、最初の空行区切りの段落を limit 字まで返す."""
    in_fence = False
    para: list[str] = []
    for line in body.split("\n"):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if not line.strip():
            if para:
                break
            continue
        para.append(BULLET.sub("", line).strip())
    text = " ".join(para)
    text = re.sub(r"[*_`]+", "", text)
    return text[:limit]


def _tokens(text: str) -> int:
    return max(1, len(text) // 2)


def run_summarize(bundle: str, dsn: str) -> SummarizeReport:
    report = SummarizeReport(bundle=bundle)
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT id, rel_path, fm, type, status, verified_at, stale_after "
            "FROM document WHERE bundle = %(b)s ORDER BY rel_path",
            {"b": bundle},
        )
        docs = cur.fetchall()
        doc_ids = [int(str(d["id"])) for d in docs]
        cur.execute(
            "DELETE FROM summary WHERE (level = 'bundle' AND target_key = %(b)s) "
            "OR (level = 'document' AND target_key = ANY(%(ids)s::text[])) "
            "OR (level = 'section' AND target_key IN "
            "   (SELECT id::text FROM chunk "
            "    WHERE document_id = ANY(%(idn)s::bigint[])))",
            {"b": bundle, "ids": [str(i) for i in doc_ids], "idn": doc_ids},
        )
        # summary は FK を持たないので、消えた文書・断片の要約（孤児）はここで掃除する
        cur.execute(
            "DELETE FROM summary WHERE (level = 'document' "
            "  AND target_key NOT IN (SELECT id::text FROM document)) "
            "OR (level = 'section' AND target_key NOT IN (SELECT id::text FROM chunk))"
        )
        rows: list[tuple[str, str, str, str, int]] = []
        bundle_lines: list[str] = []
        unverified = stale = 0
        by_type: dict[str, int] = {}
        for d in docs:
            doc_id = int(str(d["id"]))
            fm = d["fm"] if isinstance(d["fm"], dict) else {}
            desc = str(fm.get("description") or "")
            cur.execute(
                "SELECT id, heading_path, body FROM chunk "
                "WHERE document_id = %(d)s ORDER BY ordinal",
                {"d": doc_id},
            )
            chunks = cur.fetchall()
            headings = top_headings(chunks)
            for c in chunks:
                hp = str(c["heading_path"])
                sec = first_paragraph(str(c["body"])) or hp or "(空)"
                rows.append(
                    ("section", str(c["id"]), sec, _h(str(c["body"])), _tokens(sec))
                )
                report.sections += 1
            meta = (
                f"種別: {d['type'] or '-'} / 状態: {d['status']} / "
                f"確認: {'済' if d['verified_at'] else '未'} / "
                f"期限: {d['stale_after'] or '-'}"
            )
            doc_text = (
                f"{d['rel_path']}: {desc or '(description なし)'}\n"
                f"見出し: {', '.join(headings) or '-'}\n{meta}"
            )
            rows.append(
                (
                    "document",
                    str(doc_id),
                    doc_text,
                    doc_source_hash(fm, headings),
                    _tokens(doc_text),
                )
            )
            report.documents += 1
            bundle_lines.append(bundle_line(str(d["rel_path"]), desc))
            if d["verified_at"] is None and d["status"] != "deprecated":
                unverified += 1
            if d["stale_after"] is not None and str(d["stale_after"]) < _today():
                stale += 1
            by_type[str(d["type"] or "-")] = by_type.get(str(d["type"] or "-"), 0) + 1
        types = ", ".join(f"{k} {v}" for k, v in sorted(by_type.items()))
        head = (
            f"{bundle}: 文書 {len(docs)} / 種別: {types or '-'} / "
            f"未確認 {unverified} / 期限切れ（{_today()} 時点） {stale}"
        )
        bundle_text = head + "\n" + "\n".join(bundle_lines)
        rows.append(
            (
                "bundle",
                bundle,
                bundle_text,
                bundle_source_hash(bundle_lines),
                _tokens(bundle_text),
            )
        )
        report.bundles = 1
        cur.executemany(
            "INSERT INTO summary (level, target_key, text, source_hash, tokens) "
            "VALUES (%s, %s, %s, %s, %s)",
            rows,
        )
    return report
