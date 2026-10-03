import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dbr.cli import app
from dbr.features.ingest import run
from dbr.features.ingest.embed import run_embed
from dbr.features.ingest.summarize import run_summarize, stale_summaries
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


def test_stale_summaries_detects_changed_source_and_cli_check(
    clean_db: str, tmp_path: Path
) -> None:
    src = tmp_path / "dated"
    shutil.copytree(FIXTURES / "dated", src)
    run(src, "references", clean_db, log=lambda _m: None)
    run_summarize("references", clean_db)
    assert stale_summaries(clean_db, ["references"]) == []
    runner = CliRunner()
    r = runner.invoke(
        app, ["summarize", "--bundle", "references", "--check", "--dsn", clean_db]
    )
    assert r.exit_code == 0, r.output

    # description を変えて再取り込み（summarize はしない）→ その文書と bundle が古い
    note = src / "decisions-note.md"
    note.write_text(
        note.read_text(encoding="utf-8").replace("時点テスト用のダミー", "書き換えた"),
        encoding="utf-8",
    )
    run(src, "references", clean_db, log=lambda _m: None)
    stale = stale_summaries(clean_db, ["references"])
    assert {(s.level, s.reason) for s in stale} == {
        ("document", "changed"),
        ("bundle", "changed"),
    }
    assert all(s.bundle == "references" for s in stale)
    a = answer("references の扶養は全体としてどう？", dsn=clean_db, embedder=None)
    assert any("要約が古い: 変更 2 件・無い 0 件" in w for w in a.warnings)
    r = runner.invoke(
        app, ["summarize", "--bundle", "references", "--check", "--dsn", clean_db]
    )
    assert r.exit_code == 6, r.output
    assert "document" in r.output and "書き換えた" not in r.output  # 本文は出さない

    run_summarize("references", clean_db)  # 作り直せば解消
    assert stale_summaries(clean_db, ["references"]) == []
    r = runner.invoke(
        app, ["summarize", "--bundle", "references", "--check", "--dsn", clean_db]
    )
    assert r.exit_code == 0, r.output


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
    assert pick_bundles("devcontainer の設定は？") is None  # 部分一致はしない


def test_overview_scope_filter_and_boost_use_guessed_bundles(clean_db: str) -> None:
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    run(FIXTURES / "dated", "references", clean_db, log=lambda _m: None)
    run_summarize("memory", clean_db)
    run_summarize("references", clean_db)
    fake = get_embedder("fake")
    run_embed("memory", "ctx", clean_db, fake)
    run_embed("references", "ctx", clean_db, fake)
    q = "扶養と健康の記録は全体としてどう？"  # 扶養・健康 → references
    a0 = answer(
        q, dsn=clean_db, embedder=fake, scope="none"
    )  # none: 全 bundle（既定は boost）
    assert set(a0.bundles) == {"memory", "references"}
    a1 = answer(q, dsn=clean_db, embedder=fake, scope="filter")
    assert a1.bundles == ["references"]
    assert all(d["doc"].startswith("references/") for d in a1.doc_summaries)
    assert any("bundle を推定（filter）" in w and "対象外" in w for w in a1.warnings)
    a2 = answer(q, dsn=clean_db, embedder=fake, scope="boost", boost_w=2.0)
    assert a2.bundles == ["references"]  # 証拠の bundle 要約は推定側
    assert any("bundle を推定（boost）" in w and "残す" in w for w in a2.warnings)
    with pytest.raises(ValueError, match="scope"):  # 語彙外は黙って filter にしない
        answer(q, dsn=clean_db, embedder=fake, scope="nope")
    # bundle 名の明示は推定より優先
    a3 = answer("memory の健康の記録は？", dsn=clean_db, embedder=fake, scope="filter")
    assert a3.bundles == ["memory"] and not any("推定" in w for w in a3.warnings)


def test_overview_falls_back_to_fts_when_target_bundle_has_no_embeddings(
    clean_db: str,
) -> None:
    # memory にだけ埋め込みがあり references には無い → 対象 bundle が references
    # のとき、黙って空にせず全文検索で代替して WARN を出す（受入検証 D4）
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    run(FIXTURES / "dated", "references", clean_db, log=lambda _m: None)
    run_summarize("memory", clean_db)
    run_summarize("references", clean_db)
    fake = get_embedder("fake")
    run_embed("memory", "ctx", clean_db, fake)
    a = answer("references の扶養の記録は全体としてどう？", dsn=clean_db, embedder=fake)
    assert a.bundles == ["references"]
    assert any("全文検索で代替" in w for w in a.warnings)
    assert a.doc_summaries
    assert all(d["doc"].startswith("references/") for d in a.doc_summaries)
