"""統合テストの共通部。Docker の PostgreSQL が要る（未起動は skip ではなく失敗）."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from dbr.shared.db import connect
from dbr.shared.db.migrate import migrate

DEFAULT_DSN = "postgresql://dbr:dbr@127.0.0.1:5432/dbr"
ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def dsn() -> str:
    value = os.environ.get("DBR_DSN", DEFAULT_DSN)
    try:
        conn = connect(value)
    except psycopg.OperationalError as exc:  # pragma: no cover - 環境依存
        pytest.fail(f"DB 未起動（docker compose up -d が必要）: {exc}")
    with conn:
        migrate(conn, MIGRATIONS)
    return value


@pytest.fixture
def clean_db(dsn: str) -> Iterator[str]:
    """各テストの前に document/chunk を空にする."""
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute("TRUNCATE document CASCADE")
    yield dsn


def count_rows(dsn: str, table: str) -> int:
    assert table in {"document", "chunk"}  # 固定名だけ
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) AS n FROM {table}")  # 固定名のみ（上で検査）
        row = cur.fetchone()
    assert row is not None
    return int(str(row["n"]))
