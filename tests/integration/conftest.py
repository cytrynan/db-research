"""統合テストの共通部。Docker の PostgreSQL が要る（未起動は skip ではなく失敗）."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest

from dbr.shared.db import connect
from dbr.shared.db.migrate import migrate

# 統合テストは document を TRUNCATE するので、実データの `dbr` とは別 DB（`dbr_test`）。
# 作成: docker exec dbr_pg psql -U dbr -d dbr -c "CREATE DATABASE dbr_test"
DEFAULT_DSN = "postgresql://dbr:dbr@127.0.0.1:5432/dbr_test"
ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"
FIXTURES = ROOT / "tests" / "fixtures"


@pytest.fixture(scope="session")
def dsn() -> str:
    value = os.environ.get("DBR_TEST_DSN", DEFAULT_DSN)
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
        # summary は FK を持たない（target_key は文字列）ので別に空にする
        cur.execute("TRUNCATE summary")
    yield dsn


def count_rows(dsn: str, table: str) -> int:
    assert table in {"document", "chunk"}  # 固定名だけ
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute(f"SELECT count(*) AS n FROM {table}")  # 固定名のみ（上で検査）
        row = cur.fetchone()
    assert row is not None
    return int(str(row["n"]))


@pytest.fixture(autouse=True)
def _serve_log_to_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """serve のログを実運用の ~/.dbr/serve.log に書かない（追加レビューの観察 B）."""
    import dbr.features.serve as serve_mod

    monkeypatch.setattr(serve_mod, "STATE_DIR", tmp_path / ".dbr")
    monkeypatch.setattr(serve_mod, "LOG_PATH", tmp_path / ".dbr" / "serve.log")
