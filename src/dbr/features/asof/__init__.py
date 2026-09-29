"""③ 時点（F5）: 「YYYY-MM 時点はどうだったか」「いつ変わったか」に fact 表で答える."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from dbr.features.ingest.frontmatter import JST
from dbr.features.search import Mode, NoEmbeddings, dedupe_by_document, search
from dbr.features.search.fts import or_tsquery
from dbr.shared.db import connect
from dbr.shared.embed import Embedder

AT_RE = re.compile(r"(20\d{2})-(\d{2})(?:-(\d{2}))?")
# 「2026-08 より前」→ その期間の直前の瞬間（期間自体は含めない）。
# 「以前」「までに」は日本語では基準日を**含む**ので既定（期間の終わり）のまま
# （受入検証 D2・2026-09-29。以前は 4 語とも直前扱いにしていた）
BEFORE_RE = re.compile(r"[ 　]*(より以前|より前)")


@dataclass(frozen=True)
class FactHit:
    fact_id: int
    bundle: str
    rel_path: str
    subject: str
    value: str
    valid_from: datetime
    valid_to: datetime | None
    recorded_at: datetime
    valid_source: str
    score: float

    @property
    def doc_key(self) -> str:
        return f"{self.bundle}/{self.rel_path}"


def parse_at(text: str) -> datetime | None:
    """`YYYY-MM-DD` はその日の終わり、`YYYY-MM` は月末の終わり（JST）。無ければ None.

    日付の直後に「より前」が続くときは、その日（月）の**始まりの直前**を返す
    （「以前」「までに」は基準日を含むので終わりのまま）。質問文の中から拾う用途なので、
    `--at` のような値そのものの検査には parse_at_option を使う。
    """
    m = AT_RE.search(text)
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    before = BEFORE_RE.match(text, m.end()) is not None
    try:
        if before:
            d = int(m.group(3)) if m.group(3) else 1
            start = datetime(y, mo, d, tzinfo=JST)
            return start - timedelta(seconds=1)
        d = int(m.group(3)) if m.group(3) else calendar.monthrange(y, mo)[1]
        return datetime(y, mo, d, 23, 59, 59, tzinfo=JST)
    except ValueError:
        return None


def parse_at_option(value: str) -> datetime | None:
    """`--at` の値を検査する。`YYYY-MM-DD` / `YYYY-MM` に**全体一致**しなければ None.

    parse_at は質問文の中から日付を拾うので `2026-08-1` → 月末、`x2026-08-15y` も
    通してしまう（受入検証 D1）。オプション値は前後に余計な字があれば拒否する。
    """
    v = value.strip()
    if AT_RE.fullmatch(v) is None:
        return None
    return parse_at(v)


_SELECT = """
SELECT f.id AS fact_id, d.bundle, d.rel_path, f.subject, f.value,
       f.valid_from, f.valid_to, f.recorded_at, f.valid_source,
       ts_rank_cd(f.tsv, q) AS score
FROM fact f
JOIN document d ON d.id = f.document_id,
     to_tsquery('simple', %(q)s) q
WHERE f.tsv @@ q
  AND (%(bundles)s::text[] IS NULL OR d.bundle = ANY(%(bundles)s::text[]))
  AND (%(docs)s::text[] IS NULL
       OR (d.bundle || '/' || d.rel_path) = ANY(%(docs)s::text[]))
  AND (%(chunks)s::bigint[] IS NULL OR f.chunk_id = ANY(%(chunks)s::bigint[]))
"""
SQL_ASOF = (
    _SELECT
    + "  AND f.valid_from <= %(at)s AND (f.valid_to IS NULL OR %(at)s < f.valid_to)\n"
    + "ORDER BY score DESC, f.valid_from DESC, f.id\nLIMIT %(k)s\n"
)
SQL_HISTORY = _SELECT + "ORDER BY f.valid_from ASC, score DESC, f.id\nLIMIT %(k)s\n"
SQL_HISTORY_BY_SCORE = (
    _SELECT + "ORDER BY score DESC, f.valid_from ASC, f.id\nLIMIT %(k)s\n"
)


def _dt(v: object) -> datetime:
    """timestamptz はセッション TZ（UTC）で返るので JST に直す（.date() がずれる）."""
    assert isinstance(v, datetime)
    return v.astimezone(JST)


def _hit(r: dict[str, Any]) -> FactHit:
    return FactHit(
        fact_id=int(str(r["fact_id"])),
        bundle=str(r["bundle"]),
        rel_path=str(r["rel_path"]),
        subject=str(r["subject"]),
        value=str(r["value"]),
        valid_from=_dt(r["valid_from"]),
        valid_to=_dt(r["valid_to"]) if r["valid_to"] is not None else None,
        recorded_at=_dt(r["recorded_at"]),
        valid_source=str(r["valid_source"]),
        score=float(str(r["score"])),
    )


def as_of(
    question: str,
    at: datetime,
    *,
    dsn: str,
    bundles: list[str] | None = None,
    docs: list[str] | None = None,
    chunks: list[int] | None = None,
    k: int = 5,
) -> list[FactHit]:
    """時点 at に有効だった事実。docs（bundle/rel_path）や chunks（断片 id）で絞れる."""
    q = or_tsquery(question)
    if not q:
        return []
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute(
            SQL_ASOF,
            {
                "q": q,
                "bundles": bundles,
                "docs": docs,
                "chunks": chunks,
                "at": at,
                "k": k,
            },
        )
        return [_hit(dict(r)) for r in cur.fetchall()]


def history(
    question: str,
    *,
    dsn: str,
    bundles: list[str] | None = None,
    docs: list[str] | None = None,
    chunks: list[int] | None = None,
    k: int = 20,
    by: str = "date",
) -> list[FactHit]:
    """関連する事実の履歴。by='date' は古い順（既定）、by='score' は関連度順."""
    if by not in ("date", "score"):
        raise ValueError("by は 'date' か 'score'")
    q = or_tsquery(question)
    if not q:
        return []
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        sql = SQL_HISTORY if by == "date" else SQL_HISTORY_BY_SCORE
        cur.execute(
            sql, {"q": q, "bundles": bundles, "docs": docs, "chunks": chunks, "k": k}
        )
        return [_hit(dict(r)) for r in cur.fetchall()]


@dataclass
class Scopes:
    chunks: list[int]  # 質問に近い断片（上位 10）
    docs: list[str]  # 質問に近い文書（上位 5）


def candidate_scopes(
    question: str,
    *,
    dsn: str,
    embedder: Embedder | None,
    n_chunks: int = 10,
    n_docs: int = 5,
) -> Scopes:
    """① 探し物で質問に近い断片・文書を先に絞る（「何について」は探し物と同じ）."""
    mode: Mode = "embed_ctx" if embedder is not None else "fts"
    try:
        hits = search(question, mode=mode, dsn=dsn, k=50, embedder=embedder)
    except NoEmbeddings:
        hits = search(question, mode="fts", dsn=dsn, k=50)
    docs = [h.doc_key for h in dedupe_by_document(hits)[:n_docs]]
    return Scopes(chunks=[h.chunk_id for h in hits[:n_chunks]], docs=docs)


@dataclass
class AsofAnswer:
    at: datetime | None
    docs: list[str]  # 文書の絞り込み候補（記録用）
    scope: str  # 'chunks' | 'docs' | 'all'
    fallback_to_history: bool
    hits: list[FactHit]
    chunks: list[int] = field(default_factory=list)  # 断片の絞り込み候補（記録用）


def answer_asof(
    question: str,
    *,
    dsn: str,
    embedder: Embedder | None = None,
    at: datetime | None = None,
    k: int = 5,
) -> AsofAnswer:
    """断片 → 文書 → 全体の順に範囲を広げ、各範囲で「時点の事実」→「履歴」を試す.

    狭い範囲に事実があるなら、そこで「その時点の記録は無い → 最初の記録は…」と
    答える方が、広い範囲の無関係な事実を返すより正しい（2026-09-29 Q16 の観察）。
    """
    if at is None:
        at = parse_at(question)
    sc = candidate_scopes(question, dsn=dsn, embedder=embedder)
    scopes: list[tuple[str, dict[str, Any]]] = []
    if sc.chunks:
        scopes.append(("chunks", {"chunks": sc.chunks}))
    if sc.docs:
        scopes.append(("docs", {"docs": sc.docs}))
    scopes.append(("all", {}))
    for scope, filt in scopes:
        if at is not None:
            hits = as_of(question, at, dsn=dsn, k=k, **filt)
            if hits:
                return AsofAnswer(at, sc.docs, scope, False, hits, chunks=sc.chunks)
            hist = history(question, dsn=dsn, k=k, by="score", **filt)
            if hist:
                return AsofAnswer(at, sc.docs, scope, True, hist, chunks=sc.chunks)
        else:
            hist = history(question, dsn=dsn, k=k, by="score", **filt)
            if hist:
                return AsofAnswer(at, sc.docs, scope, False, hist, chunks=sc.chunks)
    return AsofAnswer(at, sc.docs, "all", False, [], chunks=sc.chunks)


__all__ = [
    "AT_RE",
    "AsofAnswer",
    "FactHit",
    "Scopes",
    "answer_asof",
    "as_of",
    "candidate_scopes",
    "history",
    "parse_at",
    "parse_at_option",
]
