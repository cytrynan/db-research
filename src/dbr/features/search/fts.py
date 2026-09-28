"""全文検索側。質問も索引と同じ tokenize を通し、語を OR で結んだ tsquery にする.

AND（plainto_tsquery）だと質問中の語が1つでも索引に無い断片が全部落ちる。
OR にして ts_rank_cd（一致した語の数と近さ）で並べる方が「探し物」に合う
（2026-09-29 初回 bench: AND では 10 問中 8 問がヒット 0 件）。
"""

from __future__ import annotations

from typing import Any

import psycopg

from dbr.shared.text import tokenize

SQL = """
SELECT c.id AS chunk_id, d.bundle, d.rel_path, c.heading_path, c.body,
       ts_rank_cd(c.tsv, q) AS score
FROM chunk c
JOIN document d ON d.id = c.document_id,
     to_tsquery('simple', %(q)s) q
WHERE c.tsv @@ q
  AND (%(bundles)s::text[] IS NULL OR d.bundle = ANY(%(bundles)s::text[]))
ORDER BY score DESC, c.id
LIMIT %(limit)s
"""


def or_tsquery(question: str) -> str:
    """語をクォートして ' | ' で結ぶ（tsquery の特殊文字 & | ! ( ) : を無害化）."""
    terms = []
    for t in tokenize(question):
        terms.append("'" + t.replace("\\", "\\\\").replace("'", "''") + "'")
    return " | ".join(dict.fromkeys(terms))  # 重複語は1回


def fts_search(
    conn: psycopg.Connection[dict[str, object]],
    question: str,
    *,
    limit: int = 100,
    bundles: list[str] | None = None,
) -> list[dict[str, Any]]:
    q = or_tsquery(question)
    if not q:
        return []
    with conn.cursor() as cur:
        cur.execute(SQL, {"q": q, "bundles": bundles, "limit": limit})
        return [dict(r) for r in cur.fetchall()]
