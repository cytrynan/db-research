"""bench の sweep / hnsw / find（rerank 含む）を fake モデルで通す（dbr_test）."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dbr.cli import app
from dbr.features.bench.hnsw import run_hnsw
from dbr.features.bench.questions import Question
from dbr.features.bench.sweep import run_sweep
from dbr.features.ingest import run
from dbr.features.ingest.embed import run_embed
from dbr.shared.embed import get_embedder
from tests.integration.conftest import FIXTURES

pytestmark = pytest.mark.db

QS = [
    Question("Q01", "規約外キー", "find", ("memory/updated.md",)),
    Question("Q02", "verified がリスト", "find", ("memory/verified-list.md",)),
    Question("Q03", "何件？", "count", ()),
]


def _prepare(dsn: str) -> None:
    run(FIXTURES / "kuroko", "memory", dsn, log=lambda _m: None)
    fake = get_embedder("fake")
    run_embed("memory", "plain", dsn, fake)
    run_embed("memory", "ctx", dsn, fake)


def test_run_sweep_shape(clean_db: str) -> None:
    _prepare(clean_db)
    res = run_sweep(
        QS,
        dsn=clean_db,
        embedder=get_embedder("fake"),
        weights=(0.0, 1.0),
        cands=(20, 100),
    )
    assert res["kind"] == "sweep" and res["question_count"] == 2
    assert len(res["cells"]) == 4
    cell = res["cells"][0]
    assert {"w_fts", "candidates", "recall@5", "recall@20", "mrr", "ranks"} <= set(cell)
    assert set(cell["ranks"]) == {"Q01", "Q02"}
    assert res["best"]["w_fts"] in (0.0, 1.0)


def test_run_hnsw_shape_and_index_flag(clean_db: str) -> None:
    _prepare(clean_db)
    res = run_hnsw(
        QS, dsn=clean_db, embedder=get_embedder("fake"), efs=(40, 100), repeats=1
    )
    assert res["kind"] == "hnsw" and [e["ef_search"] for e in res["ef"]] == [40, 100]
    for e in res["ef"]:
        assert 0.0 <= e["recall@20_vs_exact"] <= 1.0
        assert e["latency_ms_median"] >= 0.0
    assert "explain_forced" in res and isinstance(res["index_used_when_forced"], bool)


def test_cli_bench_all_kinds_with_fake_models(clean_db: str, tmp_path: Path) -> None:
    _prepare(clean_db)
    qfile = tmp_path / "q.md"
    qfile.write_text(
        "| # | 質問 | 型 | 期待 | 備考 |\n|---|---|---|---|---|\n"
        "| Q01 | 規約外キー | find | `memory/updated.md` | |\n"
        "| Q02 | 日付だけ | find | `memory/dateonly.md` | |\n",
        encoding="utf-8",
    )
    out = tmp_path / "results"
    runner = CliRunner()
    common = [
        "--questions", str(qfile), "--out", str(out), "--dsn", clean_db,
        "--model", "fake", "--label", "t",
    ]  # fmt: skip
    r = runner.invoke(
        app,
        ["bench", "--kind", "find",
         "--modes", "fts,embed,hybrid,hybrid_ctx,hybrid_ctx_rerank,embed_ctx_rerank",
         "--reranker", "fake", *common],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    find_json = next(out.glob("*-find-t.json"))
    data = json.loads(find_json.read_text(encoding="utf-8"))
    assert set(data["modes"]) == {
        "fts",
        "embed",
        "hybrid",
        "hybrid_ctx",
        "hybrid_ctx_rerank",
        "embed_ctx_rerank",
    }
    assert data["reranker"] == "fake" and data["agg"] == "max"
    r = runner.invoke(
        app,
        [
            "bench",
            "--kind",
            "find",
            "--modes",
            "embed_ctx",
            "--agg",
            "rrf_top3",
            *common,
        ],
    )
    assert r.exit_code == 0, r.output
    r = runner.invoke(app, ["bench", "--kind", "find", "--agg", "mean", *common])
    assert r.exit_code == 2

    r = runner.invoke(app, ["bench", "--kind", "tune", "--reranker", "fake", *common])
    assert r.exit_code == 0, r.output
    tune = json.loads(next(out.glob("*-tune-t.json")).read_text(encoding="utf-8"))
    assert len(tune["cells"]) == 1 * 3 + 4 * 3  # embed_ctx 1 + rerank_top 4 → × agg 3
    assert {c["agg"] for c in tune["cells"]} == {"max", "rrf_all", "rrf_top3"}
    assert all(set(c["ranks"]) == {"Q01", "Q02"} for c in tune["cells"])

    r = runner.invoke(app, ["bench", "--kind", "sweep", *common])
    assert r.exit_code == 0, r.output
    assert next(out.glob("*-sweep-t.json")).exists()

    r = runner.invoke(app, ["bench", "--kind", "hnsw", *common])
    assert r.exit_code == 0, r.output
    assert next(out.glob("*-hnsw-t.json")).exists()

    r = runner.invoke(app, ["bench", "--kind", "nope", *common])
    assert r.exit_code == 2
    r = runner.invoke(
        app, ["bench", "--kind", "find", "--label", "a/b", "--dsn", clean_db]
    )
    assert r.exit_code == 2


def test_cli_ask_rerank_mode_with_fake(clean_db: str) -> None:
    _prepare(clean_db)
    r = CliRunner().invoke(
        app,
        ["ask", "規約外キーはどこに書いた？", "--mode", "hybrid_ctx_rerank",
         "--model", "fake", "--reranker", "fake", "--dsn", clean_db, "--json"],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    data = json.loads(r.output.strip().splitlines()[-1])
    assert data["kind"] == "find" and data["hits"]
    assert all(h["source"] == "rerank" for h in data["hits"])
    r = CliRunner().invoke(
        app,
        ["ask", "規約外キーはどこに書いた？", "--mode", "embed_ctx_rerank", "--agg",
         "rrf_top3", "--model", "fake", "--reranker", "fake", "--dsn", clean_db],
    )  # fmt: skip
    assert r.exit_code == 0 and "agg=rrf_top3" in r.output, r.output
    r = CliRunner().invoke(
        app, ["ask", "規約外キーはどこに書いた？", "--model", "fake", "--dsn", clean_db]
    )  # 既定（D-14）: embed_ctx + rrf_top3
    assert r.exit_code == 0 and "mode=embed_ctx / agg=rrf_top3" in r.output, r.output
    r = CliRunner().invoke(
        app, ["ask", "x", "--kind", "find", "--agg", "mean", "--dsn", clean_db]
    )
    assert r.exit_code == 2  # 語彙外の agg
