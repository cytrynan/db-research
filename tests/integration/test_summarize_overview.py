import pytest

from dbr.features.ingest import run
from dbr.features.ingest.embed import run_embed
from dbr.features.ingest.summarize import run_summarize
from dbr.features.overview import answer, pick_bundles
from dbr.shared.db import connect
from dbr.shared.embed import get_embedder
from tests.integration.conftest import FIXTURES

pytestmark = pytest.mark.db


def _counts(dsn: str) -> dict[str, int]:
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT level, count(*) AS n FROM summary GROUP BY level")
        return {str(r["level"]): int(str(r["n"])) for r in cur.fetchall()}


def test_summarize_three_levels_and_idempotent(clean_db: str) -> None:
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    r1 = run_summarize("memory", clean_db)
    c1 = _counts(clean_db)
    assert r1.documents == 4 and c1["document"] == 4 and c1["bundle"] == 1
    assert r1.sections == c1["section"] > 0
    r2 = run_summarize("memory", clean_db)
    assert _counts(clean_db) == c1 and r2.documents == 4
    conn = connect(clean_db)
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT text FROM summary WHERE level='bundle' AND target_key='memory'"
        )
        row = cur.fetchone()
        assert (
            row is not None
            and "文書 4" in str(row["text"])
            and "updated.md" in str(row["text"])
        )


def test_overview_answer_with_embeddings_and_fallback(clean_db: str) -> None:
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    run_summarize("memory", clean_db)
    fake = get_embedder("fake")
    run_embed("memory", "ctx", clean_db, fake)
    a = answer("memory の記録は全体としてどう？", dsn=clean_db, embedder=fake)
    assert a.bundles == ["memory"] and len(a.bundle_summaries) == 1
    assert 1 <= len(a.doc_summaries) <= 5 and a.evidence_ids
    assert all("見出し:" in d["text"] for d in a.doc_summaries)
    b = answer("規約外キー", dsn=clean_db, embedder=None)  # fts で代替
    assert b.doc_summaries and b.doc_summaries[0]["doc"] == "memory/updated.md"
    assert pick_bundles("dev と memory を比べて") == ["dev", "memory"]
    assert pick_bundles("全部") is None
