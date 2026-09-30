"""④ 全体（F6）: 要約階層から答える。bundle 要約 ＋ 質問に近い上位文書の要約."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any

from dbr.features.ingest.handler import BUNDLES
from dbr.features.ingest.summarize import stale_summaries
from dbr.features.search import Hit, Mode, NoEmbeddings, aggregate_by_document, search
from dbr.shared.db import connect
from dbr.shared.embed import Embedder
from dbr.shared.llm import LLM

# 根拠外の言及の検出に使う。年月日は 1 つの数値として扱う。2 桁以上だけ見る
FILE_RE = re.compile(r"[A-Za-z0-9_./-]+\.md")
NUM_RE = re.compile(r"\d{4}-\d{2}-\d{2}|\d{2,}")
# プロンプト v2（2026-09-30）。v1「5 文以内」では 1.5B が 27〜89 字の薄い答え
# （ファイル名 0〜1 個）を返した。観点ごとにファイル名を挙げさせる形に変えた
SYSTEM_PROMPT = (
    "あなたは個人の記録（Markdown ファイル群）の要約係です。"
    "与えられた一覧だけを根拠に、日本語で 3〜5 文で答えてください。"
    "質問の観点（例: 手厚い／薄い、どこに反映）ごとに、該当するファイル名を"
    "一覧のとおりに 1 つ以上挙げてください。該当が無い観点は「一覧には見当たらない」と"
    "書いてください。一覧に無いファイル名・数値・事実は書かないでください。"
)


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
    # ① の既定（D-14）と同じ集約で上位文書を選ぶ
    return aggregate_by_document(
        search(question, mode=mode, dsn=dsn, k=50, embedder=embedder, bundles=bundles),
        "rrf_top3",
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
        changed = sum(1 for s in stale if s.reason == "changed")
        cmds = " / ".join(
            f"dbr summarize --bundle {b}" for b in sorted({s.bundle for s in stale})
        )
        out.warnings.append(
            f"要約が古い: 変更 {changed} 件・無い {len(stale) - changed} 件（{cmds}）"
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


@dataclass(frozen=True)
class Narrative:
    text: str
    unsupported: list[str]  # 回答にあって証拠に無いファイル名・数値
    seconds: float
    model: str


def evidence_text(a: OverviewAnswer) -> str:
    """LLM に渡す証拠。抽出型と同じ材料（bundle 要約の先頭行＋文書要約）.

    断片の本文は含めない。
    """
    parts = [
        f"【{b['bundle']}】{b['text'].split(chr(10))[0]}" for b in a.bundle_summaries
    ]
    parts.extend(f"- {d['doc']}: {d['text']}" for d in a.doc_summaries)
    return "\n".join(parts)


def unsupported_mentions(text: str, evidence: str) -> list[str]:
    """回答中のファイル名・数値のうち証拠に無いもの（ハルシネーションの下界。順序は出現順）."""
    ev_files = set(FILE_RE.findall(evidence))
    ev_nums = set(NUM_RE.findall(evidence))
    out: list[str] = []
    for f in FILE_RE.findall(text):
        base = f.rsplit("/", 1)[-1]
        if not any(e.endswith(base) for e in ev_files) and f not in out:
            out.append(f)
    for n in NUM_RE.findall(text):
        if n not in ev_nums and n not in out:
            out.append(n)
    return out


def narrate(
    question: str, a: OverviewAnswer, llm: LLM, *, max_new_tokens: int = 400
) -> Narrative:
    """証拠だけを渡して短い回答を書かせ、根拠外の言及と所要秒を付ける."""
    ev = evidence_text(a)
    user = f"質問: {question}\n\n一覧:\n{ev}\n\n回答:"
    t0 = time.perf_counter()
    text = llm.generate(SYSTEM_PROMPT, user, max_new_tokens=max_new_tokens)
    return Narrative(
        text=text,
        unsupported=unsupported_mentions(text, ev),
        seconds=round(time.perf_counter() - t0, 1),
        model=llm.name,
    )


__all__ = [
    "Narrative",
    "OverviewAnswer",
    "answer",
    "evidence_text",
    "narrate",
    "pick_bundles",
    "unsupported_mentions",
]
