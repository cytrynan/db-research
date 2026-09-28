"""`dbr reindex`: 分かち書き規則を変えたら lexemes だけ計算し直す（埋め込みは不変）."""

from __future__ import annotations

from dbr.shared.db import connect
from dbr.shared.text import lexemes


def run_reindex(bundle: str, dsn: str) -> int:
    """bundle 内の全断片の lexemes を再計算し、更新した行数を返す."""
    conn = connect(dsn)
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id, c.heading_path, c.context, c.body
                FROM chunk c JOIN document d ON d.id = c.document_id
                WHERE d.bundle = %(b)s ORDER BY c.id
                """,
                {"b": bundle},
            )
            rows = cur.fetchall()
        updated = 0
        with conn.cursor() as cur:
            for r in rows:
                lx = lexemes(f"{r['heading_path']}\n{r['context'] or ''}\n{r['body']}")
                cur.execute(
                    "UPDATE chunk SET lexemes = %(lx)s "
                    "WHERE id = %(id)s AND lexemes <> %(lx)s",
                    {"lx": lx, "id": r["id"]},
                )
                updated += cur.rowcount
    return updated
