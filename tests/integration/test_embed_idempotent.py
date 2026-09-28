import pytest

from dbr.features.ingest import run
from dbr.features.ingest.embed import run_embed
from dbr.shared.db import connect
from dbr.shared.embed import get_embedder
from tests.integration.conftest import FIXTURES

pytestmark = pytest.mark.db


def _rows(dsn: str) -> int:
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM chunk_embedding")
        row = cur.fetchone()
    assert row is not None
    return int(str(row["n"]))


def test_embed_twice_does_not_add_rows(clean_db: str) -> None:
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    fake = get_embedder("fake")
    r1 = run_embed("memory", "plain", clean_db, fake)
    n1 = _rows(clean_db)
    assert r1.computed == n1 > 0 and r1.skipped_existing == 0
    r2 = run_embed("memory", "plain", clean_db, fake)
    assert r2.computed == 0 and r2.skipped_existing == n1
    assert _rows(clean_db) == n1
    # 別 variant は別行として増える（比較のため）
    r3 = run_embed("memory", "ctx", clean_db, fake)
    assert r3.computed == n1 and _rows(clean_db) == 2 * n1


def test_embedding_is_384_dims_and_searchable(clean_db: str) -> None:
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    fake = get_embedder("fake")
    run_embed("memory", "plain", clean_db, fake)
    q = "[" + ",".join(f"{x:.7g}" for x in fake.embed_query("本文。")) + "]"
    conn = connect(clean_db)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT vector_dims(embedding) AS d FROM chunk_embedding LIMIT 1")
        row = cur.fetchone()
        assert row is not None and int(str(row["d"])) == 384
        cur.execute(
            "SELECT chunk_id, embedding <=> %(q)s::vector AS dist "
            "FROM chunk_embedding ORDER BY dist LIMIT 1",
            {"q": q},
        )
        assert cur.fetchone() is not None
