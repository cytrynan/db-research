"""埋め込み検索側。cosine 距離昇順。ef_search は整数を検証してから SET LOCAL."""

from __future__ import annotations

from typing import Any

import psycopg

from dbr.shared.embed import Embedder


class NoEmbeddings(Exception):
    """指定の variant / model の埋め込みが 1 件も無い（`dbr embed` が未実行）."""

    def __init__(self, variant: str, model: str) -> None:
        super().__init__(
            f"埋め込みがありません（variant={variant}, model={model}）。"
            " 先に `dbr embed --variant ... --model ...` を実行してください"
        )


SQL = """
SELECT c.id AS chunk_id, d.bundle, d.rel_path, c.heading_path, c.body,
       1 - (e.embedding <=> %(q)s::vector) AS score
FROM chunk_embedding e
JOIN chunk c ON c.id = e.chunk_id
JOIN document d ON d.id = c.document_id
WHERE e.variant = %(variant)s AND e.model = %(model)s
  AND (%(bundles)s::text[] IS NULL OR d.bundle = ANY(%(bundles)s::text[]))
ORDER BY e.embedding <=> %(q)s::vector, c.id
LIMIT %(limit)s
"""
# 末尾の c.id は同点（同一本文の断片＝同一ベクトル）の順序を固定するため。
# 無いと UPDATE 後にヒープ順が変わっただけで順位が揺れる（2026-09-29 bench v1→v2）。
# ※ 現状 ~2,000 行では planner が Seq Scan（厳密計算）を選び HNSW を使わない
#   （EXPLAIN で確認）。ef_search の実験は enable_seqscan=off で索引を強制してから。


def vector_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def vector_search(
    conn: psycopg.Connection[dict[str, object]],
    question: str,
    *,
    embedder: Embedder,
    variant: str,
    limit: int = 100,
    ef_search: int = 40,
    bundles: list[str] | None = None,
) -> list[dict[str, Any]]:
    if not isinstance(ef_search, int) or not 1 <= ef_search <= 1000:
        raise ValueError("ef_search は 1..1000 の整数")
    q = vector_literal(embedder.embed_query(question))
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM chunk_embedding "
            "WHERE variant = %(v)s AND model = %(m)s LIMIT 1",
            {"v": variant, "m": embedder.name},
        )
        row = cur.fetchone()
        if not row or int(str(row["n"])) == 0:
            raise NoEmbeddings(variant, embedder.name)
        cur.execute(f"SET LOCAL hnsw.ef_search = {int(ef_search)}")  # 整数検証済み
        cur.execute(
            SQL,
            {
                "q": q,
                "variant": variant,
                "model": embedder.name,
                "bundles": bundles,
                "limit": limit,
            },
        )
        return [dict(r) for r in cur.fetchall()]
