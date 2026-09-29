"""③ 時点（F5）: 「YYYY-MM 時点はどうだったか」「いつ変わったか」に fact 表で答える."""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from dbr.features.ingest.frontmatter import JST
from dbr.features.search.fts import or_tsquery
from dbr.shared.db import connect

AT_RE = re.compile(r"(20\d{2})-(\d{2})(?:-(\d{2}))?")


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
    """`YYYY-MM-DD` はその日の終わり、`YYYY-MM` は月末の終わり（JST）。無ければ None."""
    m = AT_RE.search(text)
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    try:
        d = int(m.group(3)) if m.group(3) else calendar.monthrange(y, mo)[1]
        return datetime(y, mo, d, 23, 59, 59, tzinfo=JST)
    except ValueError:
        return None


_SELECT = """
SELECT f.id AS fact_id, d.bundle, d.rel_path, f.subject, f.value,
       f.valid_from, f.valid_to, f.recorded_at, f.valid_source,
       ts_rank_cd(f.tsv, q) AS score
FROM fact f
JOIN document d ON d.id = f.document_id,
     to_tsquery('simple', %(q)s) q
WHERE f.tsv @@ q
  AND (%(bundles)s::text[] IS NULL OR d.bundle = ANY(%(bundles)s::text[]))
"""
SQL_ASOF = (
    _SELECT
    + "  AND f.valid_from <= %(at)s AND (f.valid_to IS NULL OR %(at)s < f.valid_to)\n"
    + "ORDER BY score DESC, f.valid_from DESC, f.id\nLIMIT %(k)s\n"
)
SQL_HISTORY = _SELECT + "ORDER BY f.valid_from ASC, score DESC, f.id\nLIMIT %(k)s\n"


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
    k: int = 5,
) -> list[FactHit]:
    q = or_tsquery(question)
    if not q:
        return []
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute(SQL_ASOF, {"q": q, "bundles": bundles, "at": at, "k": k})
        return [_hit(dict(r)) for r in cur.fetchall()]


def history(
    question: str, *, dsn: str, bundles: list[str] | None = None, k: int = 20
) -> list[FactHit]:
    q = or_tsquery(question)
    if not q:
        return []
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute(SQL_HISTORY, {"q": q, "bundles": bundles, "k": k})
        return [_hit(dict(r)) for r in cur.fetchall()]


__all__ = ["AT_RE", "FactHit", "as_of", "history", "parse_at"]
