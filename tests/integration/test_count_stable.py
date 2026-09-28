import pytest

from dbr.features.count import ask_view
from dbr.features.ingest import run
from tests.integration.conftest import FIXTURES

pytestmark = pytest.mark.db


def test_views_match_fixture_and_are_stable(clean_db: str) -> None:
    run(FIXTURES / "okf-plain", "dev", clean_db, log=lambda _m: None)
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)

    by_bundle = {
        r["bundle"]: (int(r["docs"]), int(r["chunks"]))
        for r in ask_view("v_by_bundle", clean_db)
    }
    assert by_bundle["dev"][0] == 3
    assert by_bundle["memory"][0] == 4

    unverified = {r["bundle"]: int(r["n"]) for r in ask_view("v_unverified", clean_db)}
    # dev: alpha=verified 済み / beta=deprecated（除外） / notype=未確認 → 1
    # memory: memory-note, verified-list=verified 済み / dateonly, updated=未確認 → 2
    assert unverified == {"dev": 1, "memory": 2}

    stale = {r["bundle"]: int(r["n"]) for r in ask_view("v_stale", clean_db)}
    assert stale == {"dev": 1}  # beta だけ

    by_type = {
        (r["bundle"], r["type"]): int(r["n"]) for r in ask_view("v_by_type", clean_db)
    }
    assert by_type[("dev", None)] == 1
    assert by_type[("memory", "Tech Note")] == 3

    # 同じ質問を3回 → 3回とも同じ
    runs = [ask_view("v_by_bundle", clean_db) for _ in range(3)]
    assert runs[0] == runs[1] == runs[2]
