import pytest

from dbr.features.ingest import run
from dbr.shared.db import connect
from dbr.shared.text import lexemes
from tests.integration.conftest import FIXTURES

pytestmark = pytest.mark.db


def test_lexemes_filled_and_tsv_matches_fixture(clean_db: str) -> None:
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    conn = connect(clean_db)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM chunk WHERE lexemes = ''")
        row = cur.fetchone()
        assert row is not None and int(str(row["n"])) == 0

        cur.execute(
            """
            SELECT d.rel_path, ts_rank_cd(c.tsv, q) AS score
            FROM chunk c
            JOIN document d ON d.id = c.document_id,
                 plainto_tsquery('simple', %(q)s) q
            WHERE c.tsv @@ q
            ORDER BY score DESC
            """,
            {"q": lexemes("規約外キー")},
        )
        rows = cur.fetchall()
        assert rows and rows[0]["rel_path"] == "updated.md"
