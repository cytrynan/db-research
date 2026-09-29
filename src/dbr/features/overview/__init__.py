"""④ 全体（F6）: 要約階層から答える。bundle 要約 ＋ 質問に近い上位文書の要約."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from dbr.features.ingest.handler import BUNDLES
from dbr.features.ingest.summarize import stale_summaries
from dbr.features.search import Hit, Mode, NoEmbeddings, dedupe_by_document, search
from dbr.shared.db import connect
from dbr.shared.embed import Embedder


@dataclass
class OverviewAnswer:
    bundles: list[str]
    bundle_summaries: list[dict[str, Any]] = field(
        default_factory=list
    )  # {id, bundle, text}
    doc_summaries: list[dict[str, Any]] = field(
        default_factory=list
    )  # {id, doc, text, score}
    evidence_ids: list[int] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def pick_bundles(question: str) -> list[str] | None:
    """質問文に bundle 名が**語として**出ていればその bundle に絞る（部分一致はしない）.

    `dev` は `devcontainer` の中にも現れるので、英数字の続きでない位置だけ拾う。
    """
    found = [
        b
        for b in sorted(BUNDLES)
        if re.search(rf"(?<![A-Za-z0-9_]){re.escape(b)}(?![A-Za-z0-9_])", question)
    ]
    return found or None


def _top_docs(
    question: str,
    mode: Mode,
    dsn: str,
    embedder: Embedder | None,
    bundles: list[str] | None,
    n: int,
) -> list[Hit]:
    return dedupe_by_document(
        search(question, mode=mode, dsn=dsn, k=50, embedder=embedder, bundles=bundles)
    )[:n]


def answer(
    question: str,
    *,
    dsn: str,
    embedder: Embedder | None = None,
    bundles: list[str] | None = None,
    top_docs: int = 5,
) -> OverviewAnswer:
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        if bundles is None:
            bundles = pick_bundles(question)
        if bundles is None:
            cur.execute(
                "SELECT target_key FROM summary WHERE level = 'bundle' ORDER BY 1"
            )
            bundles = [str(r["target_key"]) for r in cur.fetchall()]
        out = OverviewAnswer(bundles=bundles)
        cur.execute(
            "SELECT id, target_key, text FROM summary "
            "WHERE level = 'bundle' AND target_key = ANY(%(b)s::text[]) "
            "ORDER BY target_key",
            {"b": bundles},
        )
        for r in cur.fetchall():
            out.bundle_summaries.append(
                {
                    "id": int(str(r["id"])),
                    "bundle": str(r["target_key"]),
                    "text": str(r["text"]),
                }
            )
            out.evidence_ids.append(int(str(r["id"])))
        if not out.bundle_summaries:
            out.warnings.append("bundle 要約が無い（dbr summarize を実行する）")

    # 要約は元テキストの source_hash を持つ。変わっていたら黙って古い要約を出さず WARN
    stale = stale_summaries(dsn, bundles)
    if stale:
        targets = ", ".join(sorted({s.bundle for s in stale}))
        out.warnings.append(
            f"要約が古い: {len(stale)} 件（dbr summarize --bundle {targets}）"
        )

    mode: Mode = "embed_ctx" if embedder is not None else "fts"
    hits: list[Hit] = []
    use_fts = mode == "fts"
    if not use_fts:
        try:
            hits = _top_docs(question, mode, dsn, embedder, bundles, top_docs)
        except NoEmbeddings:
            hits = []
        if not hits:
            # NoEmbeddings は表全体が 0 件のときしか出ない。対象 bundle だけ埋め込みが
            # 無いときは空で返るので、黙って空にせず全文検索へ（受入検証 D4）
            out.warnings.append(
                "対象 bundle に文脈付き埋め込みが無いので全文検索で代替"
            )
            use_fts = True
    if use_fts:
        hits = _top_docs(question, "fts", dsn, None, bundles, top_docs)

    if hits:
        conn = connect(dsn)
        with conn, conn.cursor() as cur:
            for h in hits:
                cur.execute(
                    "SELECT s.id, s.text FROM summary s "
                    "JOIN document d ON d.id::text = s.target_key "
                    "WHERE s.level = 'document' AND d.bundle = %(b)s "
                    "  AND d.rel_path = %(r)s",
                    {"b": h.bundle, "r": h.rel_path},
                )
                row = cur.fetchone()
                if row is None:
                    out.warnings.append(f"document 要約が無い: {h.doc_key}")
                    continue
                out.doc_summaries.append(
                    {
                        "id": int(str(row["id"])),
                        "doc": h.doc_key,
                        "text": str(row["text"]),
                        "score": h.score,
                    }
                )
                out.evidence_ids.append(int(str(row["id"])))
    return out


__all__ = ["OverviewAnswer", "answer", "pick_bundles"]
