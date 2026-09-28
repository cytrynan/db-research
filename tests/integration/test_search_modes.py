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


def test_bundle_filter(clean_db: str) -> None:
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    run(FIXTURES / "okf-plain", "dev", clean_db, log=lambda _m: None)
    hits = search("本文", mode="fts", dsn=clean_db, k=20, bundles=["dev"])
    assert hits and all(h.bundle == "dev" for h in hits)
