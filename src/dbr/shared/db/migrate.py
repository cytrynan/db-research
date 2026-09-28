"""migrations/NNNN_*.sql を番号順に適用する薄い runner.

- 適用済みは `schema_migrations` で管理し飛ばす（再実行は no-op）
- 1ファイル＝1トランザクション。途中で失敗したらそのファイルだけ rollback して例外
- 既存ファイルは編集しない運用（docs/development-guidelines.md）。変更は新番号で
"""

from __future__ import annotations

import re
from pathlib import Path

import psycopg

MIGRATION_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")

_BOOTSTRAP = """
CREATE TABLE IF NOT EXISTS schema_migrations (
    version    text PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);
"""


def list_migrations(directory: Path) -> list[Path]:
    """命名規則に合うファイルを番号順で返す。規則外の .sql は例外 (黙って飛ばさない)."""
    files: list[Path] = []
    for p in sorted(directory.glob("*.sql")):
        if not MIGRATION_NAME.match(p.name):
            raise ValueError(f"マイグレーション名が規則外: {p.name} (NNNN_snake_case.sql)")
        files.append(p)
    return files


def applied_versions(conn: psycopg.Connection[dict[str, object]]) -> set[str]:
    with conn.cursor() as cur:
        cur.execute(_BOOTSTRAP)
        cur.execute("SELECT version FROM schema_migrations")
        rows = cur.fetchall()
    conn.commit()
    return {str(r["version"]) for r in rows}


def migrate(conn: psycopg.Connection[dict[str, object]], directory: Path) -> list[str]:
    """未適用のマイグレーションを適用し、適用したファイル名を返す."""
    done = applied_versions(conn)
    applied: list[str] = []
    for path in list_migrations(directory):
        if path.name in done:
            continue
        sql = path.read_text(encoding="utf-8")
        try:
            with conn.cursor() as cur:
                cur.execute(sql)  # type: ignore[arg-type]  # 生 SQL ファイルをそのまま流す
                cur.execute(
                    "INSERT INTO schema_migrations(version) VALUES (%(v)s)",
                    {"v": path.name},
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        applied.append(path.name)
    return applied
