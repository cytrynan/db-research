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


_SELECT = """
SELECT c.id AS chunk_id, d.bundle, d.rel_path, c.heading_path, c.body, c.context,
       1 - (e.embedding <=> %(q)s::vector) AS score
FROM chunk_embedding e
JOIN chunk c ON c.id = e.chunk_id
JOIN document d ON d.id = c.document_id
WHERE e.variant = %(variant)s AND e.model = %(model)s
  AND (%(bundles)s::text[] IS NULL OR d.bundle = ANY(%(bundles)s::text[]))
"""
# 厳密（既定）: 同点（同一本文の断片＝同一ベクトル）の順序を c.id で固定する。
# 無いと UPDATE 後にヒープ順が変わっただけで順位が揺れる（2026-09-29 bench v1→v2）。
SQL = _SELECT + "ORDER BY e.embedding <=> %(q)s::vector, c.id\nLIMIT %(limit)s\n"
# 索引強制: HNSW は距離順しか提供できず、`, c.id` を付けると planner は索引を使えない。
# JOIN 形だと表が小さいとき planner が chunk/document 側から結合して Sort に落ちる
# （2026-09-29 実測: enable_seqscan=off でも）。そこでサブクエリで HNSW 側を先に LIMIT
# してから JOIN する形に固定し、enable_sort=off でソート経路も塞ぐ
# （EXPLAIN で Index Scan using chunk_embedding_hnsw を確認）。
# 同点固定（c.id）は諦める。bundles の絞り込みは LIMIT 後になるので強制時は受けない。
SQL_INDEX = """
SELECT c.id AS chunk_id, d.bundle, d.rel_path, c.heading_path, c.body, c.context,
       1 - s.dist AS score
FROM (
    SELECT e.chunk_id, e.embedding <=> %(q)s::vector AS dist
    FROM chunk_embedding e
    WHERE e.variant = %(variant)s AND e.model = %(model)s
    ORDER BY dist
    LIMIT %(limit)s
) s
JOIN chunk c ON c.id = s.chunk_id
JOIN document d ON d.id = c.document_id
ORDER BY s.dist
"""


def vector_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def _check_ef(ef_search: int) -> None:
    if not isinstance(ef_search, int) or not 1 <= ef_search <= 1000:
        raise ValueError("ef_search は 1..1000 の整数")


def _params(
    q: str, variant: str, model: str, bundles: list[str] | None, limit: int
) -> dict[str, Any]:
    return {
        "q": q,
        "variant": variant,
        "model": model,
        "bundles": bundles,
        "limit": limit,
    }


def _set_session(cur: psycopg.Cursor[dict[str, object]], ef: int, force: bool) -> None:
    cur.execute(f"SET LOCAL hnsw.ef_search = {int(ef)}")  # 整数検証済み
    if force:
        cur.execute("SET LOCAL enable_seqscan = off")
        # 表が小さいと別索引＋Sort を選ぶので、ソート経路も塞いで索引順だけにする
        cur.execute("SET LOCAL enable_sort = off")
        # WHERE（variant/model）は索引走査後のフィルタなので、そのままだと結果が
        # limit に届かない。iterative scan で届くまで走査を続けさせる（pgvector 0.8+）
        cur.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")


def vector_search_vec(
    conn: psycopg.Connection[dict[str, object]],
    q: str,
    *,
    variant: str,
    model: str,
    limit: int = 100,
    ef_search: int = 40,
    bundles: list[str] | None = None,
    force_index: bool = False,
) -> list[dict[str, Any]]:
    """質問ベクトル（リテラル文字列）を受ける低レベル版。埋め込み時間を含めずに測るため."""
    _check_ef(ef_search)
    if force_index and bundles is not None:
        raise ValueError(
            "force_index=True では bundles の絞り込みは使えない（LIMIT 後になる）"
        )
    with conn.transaction(), conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM chunk_embedding "
            "WHERE variant = %(v)s AND model = %(m)s LIMIT 1",
            {"v": variant, "m": model},
        )
        row = cur.fetchone()
        if not row or int(str(row["n"])) == 0:
            raise NoEmbeddings(variant, model)
        _set_session(cur, ef_search, force_index)
        cur.execute(
            SQL_INDEX if force_index else SQL,
            _params(q, variant, model, bundles, limit),
        )
        rows = [dict(r) for r in cur.fetchall()]
    if force_index:
        # enable_sort=off と relaxed_order の組では外側の ORDER BY が保証されない
        # （受入検証で limit=500 のとき順序の崩れを観測）。返す前にスコア降順に揃える
        rows.sort(key=lambda r: (-float(str(r["score"])), int(str(r["chunk_id"]))))
    return rows


def vector_search(
    conn: psycopg.Connection[dict[str, object]],
    question: str,
    *,
    embedder: Embedder,
    variant: str,
    limit: int = 100,
    ef_search: int = 40,
    bundles: list[str] | None = None,
    force_index: bool = False,
) -> list[dict[str, Any]]:
    q = vector_literal(embedder.embed_query(question))
    return vector_search_vec(
        conn,
        q,
        variant=variant,
        model=embedder.name,
        limit=limit,
        ef_search=ef_search,
        bundles=bundles,
        force_index=force_index,
    )


def explain_vector_search(
    conn: psycopg.Connection[dict[str, object]],
    q: str,
    *,
    variant: str,
    model: str,
    limit: int = 20,
    ef_search: int = 40,
    force_index: bool = False,
) -> str:
    """実行計画（EXPLAIN）の文字列。索引が使われているか（Index Scan）の記録用."""
    _check_ef(ef_search)
    with conn.transaction(), conn.cursor() as cur:
        _set_session(cur, ef_search, force_index)
        sql = SQL_INDEX if force_index else SQL
        cur.execute(
            "EXPLAIN (COSTS OFF) " + sql, _params(q, variant, model, None, limit)
        )
        return "\n".join(str(r["QUERY PLAN"]) for r in cur.fetchall())
