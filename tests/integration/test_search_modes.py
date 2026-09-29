import pytest

from dbr.features.ingest import run
from dbr.features.ingest.embed import run_embed
from dbr.features.search import NoEmbeddings, dedupe_by_document, search
from dbr.shared.embed import get_embedder
from tests.integration.conftest import FIXTURES

pytestmark = pytest.mark.db


def test_fts_ranks_matching_file_first(clean_db: str) -> None:
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    hits = search("規約外キー", mode="fts", dsn=clean_db, k=5)
    assert hits and hits[0].rel_path == "updated.md"
    assert dedupe_by_document(hits)[0].rel_path == "updated.md"


def test_embed_requires_embeddings(clean_db: str) -> None:
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    with pytest.raises(NoEmbeddings):
        search("x", mode="embed", dsn=clean_db, embedder=get_embedder("fake"))


def test_hybrid_contains_both_sources(clean_db: str) -> None:
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    fake = get_embedder("fake")
    run_embed("memory", "plain", clean_db, fake)
    run_embed("memory", "ctx", clean_db, fake)
    hits = search("規約外キー", mode="hybrid", dsn=clean_db, k=10, embedder=fake)
    assert hits
    assert any(h.source in {"fts", "both"} for h in hits)
    assert any(h.source in {"embed", "both"} for h in hits)
    # fake は意味を持たないので fts で当たった updated.md が RRF でも上位に残る
    assert any(h.rel_path == "updated.md" for h in hits[:3])
    ctx_hits = search(
        "規約外キー", mode="hybrid_ctx", dsn=clean_db, k=10, embedder=fake
    )
    assert ctx_hits


def test_large_k_yields_every_document_after_dedupe(clean_db: str) -> None:
    """bench 用: 断片を多めに取れば文書に畳んでも全文書が残る（打ち切りで消えない）."""
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    run(FIXTURES / "okf-plain", "dev", clean_db, log=lambda _m: None)
    fake = get_embedder("fake")
    for b in ("memory", "dev"):
        run_embed(b, "plain", clean_db, fake)
    docs = dedupe_by_document(
        search("本文", mode="hybrid", dsn=clean_db, k=500, embedder=fake)
    )
    assert len(docs) == 7  # fixture は 3 + 4 文書


def test_rerank_mode_is_deterministic_and_uses_context(clean_db: str) -> None:
    from dbr.shared.rerank import get_reranker

    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    fake = get_embedder("fake")
    run_embed("memory", "ctx", clean_db, fake)
    rr = get_reranker("fake")
    a = search(
        "規約外キー",
        mode="hybrid_ctx_rerank",
        dsn=clean_db,
        k=5,
        embedder=fake,
        reranker=rr,
    )
    b = search(
        "規約外キー",
        mode="hybrid_ctx_rerank",
        dsn=clean_db,
        k=5,
        embedder=fake,
        reranker=rr,
    )
    assert [h.chunk_id for h in a] == [h.chunk_id for h in b]
    assert a and all(h.source == "rerank" for h in a)
    assert all(h.context is not None for h in a)  # 並べ直しの入力に文脈が渡っている
    with pytest.raises(ValueError):
        search("x", mode="hybrid_ctx_rerank", dsn=clean_db, embedder=fake)


def test_forced_index_plan_uses_hnsw(clean_db: str) -> None:
    from dbr.features.search.vector import explain_vector_search, vector_literal
    from dbr.shared.db import connect

    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    fake = get_embedder("fake")
    # fixture だけ（十数行）だと planner は別索引＋Sort を選ぶ（2026-09-29 実測: 行数が
    # 少ないと enable_seqscan=off でも HNSW を使わない）。合成断片で現実的な行数にする
    conn = connect(clean_db)
    with conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO chunk
                (document_id, ordinal, heading_path, body, tokens, lexemes)
            SELECT (SELECT min(id) FROM document), 1000 + g, '',
                   'synthetic ' || g, 2, ''
            FROM generate_series(1, 400) AS g
            """
        )
    run_embed("memory", "plain", clean_db, fake)
    conn = connect(clean_db)
    with conn, conn.cursor() as cur:
        cur.execute("ANALYZE chunk_embedding")
        cur.execute("ANALYZE chunk")
        cur.execute("ANALYZE document")
    q = vector_literal(fake.embed_query("本文"))
    conn = connect(clean_db)
    with conn:
        forced = explain_vector_search(
            conn, q, variant="plain", model=fake.name, force_index=True
        )
        rows_forced = search(
            "本文", mode="embed", dsn=clean_db, k=3, embedder=fake, force_index=True
        )
    assert "Index Scan" in forced and "chunk_embedding_hnsw" in forced
    assert len(rows_forced) == 3


def test_bundle_filter(clean_db: str) -> None:
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    run(FIXTURES / "okf-plain", "dev", clean_db, log=lambda _m: None)
    hits = search("本文", mode="fts", dsn=clean_db, k=20, bundles=["dev"])
    assert hits and all(h.bundle == "dev" for h in hits)
