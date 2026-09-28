"""境界の故障注入: 実際に落として拒否を観測する（監視役は検証してから完了扱い）."""

import psycopg
import pytest

from dbr.features.count import UnknownAggregate, ask_view
from dbr.features.ingest import run
from dbr.shared.db import LoopbackViolation, connect
from tests.integration.conftest import FIXTURES, count_rows

pytestmark = pytest.mark.db


def test_remote_host_rejected_before_any_db_work(clean_db: str) -> None:
    with pytest.raises(LoopbackViolation):
        run(
            FIXTURES / "okf-plain",
            "dev",
            "postgresql://dbr:dbr@example.com:5432/dbr",
            log=lambda _m: None,
        )
    assert count_rows(clean_db, "document") == 0


def test_private_md_excluded_by_walk_and_rejected_by_trigger(clean_db: str) -> None:
    r = run(FIXTURES / "with-private", "references", clean_db, log=lambda _m: None)
    assert r.inserted == 1
    assert r.excluded == 1  # private.md（*.bak-* は .md でないので走査にすら乗らない）
    assert r.rejected == 0

    conn = connect(clean_db)
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT count(*) AS n FROM document WHERE rel_path LIKE '%private.md%'"
        )
        row = cur.fetchone()
        assert row is not None and int(str(row["n"])) == 0

    # 走査をすり抜けたと仮定して直接 INSERT → DB 側トリガーが拒否する
    conn = connect(clean_db)
    with pytest.raises(psycopg.errors.CheckViolation), conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO document (bundle, rel_path, format, fm, content_hash) "
            "VALUES ('references', 'private.md', 'okf', '{}'::jsonb, 'x')"
        )
    assert count_rows(clean_db, "document") == 1

    # 大文字始まり（Windows では同一ファイル）も migration 0005 で拒否される
    conn = connect(clean_db)
    with pytest.raises(psycopg.errors.CheckViolation), conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO document (bundle, rel_path, format, fm, content_hash) "
            "VALUES ('references', 'sub/Private.md', 'okf', '{}'::jsonb, 'y')"
        )
    assert count_rows(clean_db, "document") == 1


def test_unknown_view_rejected_without_query(clean_db: str) -> None:
    with pytest.raises(UnknownAggregate) as ei:
        ask_view("v_by_bundle; DROP TABLE document", clean_db)
    assert "v_by_bundle" in ei.value.known
    assert count_rows(clean_db, "document") == 0  # 何も壊れていない
