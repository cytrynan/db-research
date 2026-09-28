"""`dbr embed`: 埋め込み未生成の断片だけ計算して chunk_embedding へ（冪等）."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from dbr.shared.db import connect
from dbr.shared.embed import Embedder

Variant = Literal["plain", "ctx"]
BATCH = 64


@dataclass
class EmbedReport:
    bundle: str
    variant: str
    model: str
    computed: int = 0
    skipped_existing: int = 0

    def to_dict(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _text_for(variant: Variant, body: str, context: str | None) -> str:
    if variant == "ctx" and context:
        return f"{context}\n{body}"
    return body


def _vector_literal(v: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in v) + "]"


def run_embed(
    bundle: str, variant: Variant, dsn: str, embedder: Embedder
) -> EmbedReport:
    report = EmbedReport(bundle=bundle, variant=variant, model=embedder.name)
    conn = connect(dsn)
    with conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS n
                FROM chunk c JOIN document d ON d.id = c.document_id
                JOIN chunk_embedding e ON e.chunk_id = c.id
                WHERE d.bundle = %(b)s AND e.variant = %(v)s AND e.model = %(m)s
                """,
                {"b": bundle, "v": variant, "m": embedder.name},
            )
            row = cur.fetchone()
            report.skipped_existing = int(str(row["n"])) if row else 0
            cur.execute(
                """
                SELECT c.id, c.body, c.context
                FROM chunk c JOIN document d ON d.id = c.document_id
                WHERE d.bundle = %(b)s
                  AND NOT EXISTS (
                      SELECT 1 FROM chunk_embedding e
                      WHERE e.chunk_id = c.id AND e.variant = %(v)s AND e.model = %(m)s)
                ORDER BY c.id
                """,
                {"b": bundle, "v": variant, "m": embedder.name},
            )
            pending = cur.fetchall()
        for i in range(0, len(pending), BATCH):
            batch = pending[i : i + BATCH]
            texts = [
                _text_for(
                    variant,
                    str(r["body"]),
                    str(r["context"]) if r["context"] is not None else None,
                )
                for r in batch
            ]
            vectors = embedder.embed_passages(texts)
            with (
                conn.cursor() as cur,
                cur.copy(
                    "COPY chunk_embedding (chunk_id, variant, model, embedding) "
                    "FROM STDIN"
                ) as copy,
            ):
                for r, v in zip(batch, vectors, strict=True):
                    copy.write_row(
                        (r["id"], variant, embedder.name, _vector_literal(v))
                    )
            report.computed += len(batch)
    return report
