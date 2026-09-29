"""bench の count / asof / overview を fixture＋fake で通す（dbr_test）."""

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dbr.cli import app
from dbr.features.bench.asof import is_correct, run_asof
from dbr.features.bench.count import run_count
from dbr.features.bench.overview import run_overview
from dbr.features.bench.questions import Question
from dbr.features.ingest import run
from dbr.features.ingest.embed import run_embed
from dbr.features.ingest.facts import run_facts
from dbr.features.ingest.summarize import run_summarize
from dbr.shared.embed import get_embedder
from tests.integration.conftest import FIXTURES

pytestmark = pytest.mark.db

NOTE = ("references/decisions-note.md",)
QS = [
    Question("Q11", "references のファイルは何件？", "count", (), (), ("v_by_bundle",)),
    Question("Q13", "期限切れの記録はいくつ？", "count", (), (), ("v_stale",)),
    Question("Q15", "扶養の制度知識を分けたのはいつ？", "asof", NOTE, ("2026-08-11",)),
    Question(
        "Q18",
        "2026-08 時点で扶養の年収の壁はどうなっていた？",
        "asof",
        NOTE,
        ("2026-08-11",),
    ),
    Question("Q19", "references の記録は全体としてどう？", "overview", ()),
]


def _prepare(dsn: str) -> None:
    run(FIXTURES / "dated", "references", dsn, log=lambda _m: None)
    run_facts("references", dsn)
    run_summarize("references", dsn)
    run_embed("references", "ctx", dsn, get_embedder("fake"))


def test_run_count_is_stable(clean_db: str) -> None:
    _prepare(clean_db)
    res = run_count(QS, dsn=clean_db)
    assert res["question_count"] == 2 and res["all_stable"] is True
    assert {p["view"] for p in res["per_question"]} == {"v_by_bundle", "v_stale"}
    assert res["all_views_ok"] is True  # 期待ビューとの一致も測る
    # 期待ビューが無い問いは view_ok=None で all_views_ok は False（正解扱いにしない）
    no_exp = run_count(
        [Question("Qx", "references のファイルは何件？", "count", ())], dsn=clean_db
    )
    assert no_exp["per_question"][0]["view_ok"] is None
    assert no_exp["all_views_ok"] is False


def test_run_asof_scores_by_file_and_date(clean_db: str) -> None:
    _prepare(clean_db)
    res = run_asof(QS, dsn=clean_db)
    assert res["question_count"] == 2 and res["correct"] == 2
    q18 = next(p for p in res["per_question"] if p["id"] == "Q18")
    assert q18["at"] == "2026-08-31"
    assert all(h["date"] <= "2026-08-31" for h in q18["hits"])  # 未来の事実は無い


def test_is_correct_rules() -> None:
    from datetime import datetime

    from dbr.features.asof import FactHit
    from dbr.features.ingest.frontmatter import JST

    d = datetime(2026, 8, 11, tzinfo=JST)
    h = FactHit(1, "references", "a.md", "s", "v", d, None, d, "dated_text", 1.0)
    assert is_correct([h], ("references/a.md",), ("2026-08-11",))
    assert not is_correct([h], ("references/b.md",), ("2026-08-11",))
    assert not is_correct([h], ("references/a.md",), ("2026-08-12",))
    # 期待の片方が空なら不正解（空側を「何でも一致」にしない。受入検証 D5）
    assert not is_correct([h], (), ("2026-08-11",))
    assert not is_correct([h], ("references/a.md",), ())
    assert not is_correct([], ("references/a.md",), ("2026-08-11",))


def test_run_overview_writes_answers_file(clean_db: str, tmp_path: Path) -> None:
    _prepare(clean_db)
    out = tmp_path / "overview-answers.md"
    res = run_overview(
        QS, dsn=clean_db, embedder=get_embedder("fake"), answers_path=out
    )
    assert res["question_count"] == 1 and out.exists()
    text = out.read_text(encoding="utf-8")
    assert "| Q19 |" in text and "K 採点" in text
    assert res["per_question"][0]["n_bundle_summaries"] == 1


def test_cli_bench_count_asof_overview_and_ask_all_kinds(
    clean_db: str, tmp_path: Path
) -> None:
    _prepare(clean_db)
    qfile = tmp_path / "q.md"
    qfile.write_text(
        "| # | 質問 | 型 | 期待 | 備考 |\n|---|---|---|---|---|\n"
        "| Q11 | references のファイルは何件？ | count | `v_by_bundle` | |\n"
        "| Q15 | 扶養の制度知識を分けたのはいつ？ | asof | "
        "`references/decisions-note.md` `2026-08-11` | |\n"
        "| Q19 | references の記録は全体としてどう？ | overview | - | |\n",
        encoding="utf-8",
    )
    out = tmp_path / "results"
    runner = CliRunner()
    common = [
        "--questions",
        str(qfile),
        "--out",
        str(out),
        "--dsn",
        clean_db,
        "--model",
        "fake",
    ]
    for kind in ("count", "asof"):
        r = runner.invoke(app, ["bench", "--kind", kind, *common])
        assert r.exit_code == 0, r.output
        assert next(out.glob(f"*-{kind}.json")).exists()
    r = runner.invoke(
        app,
        ["bench", "--kind", "overview", "--answers", str(tmp_path / "ans.md"), *common],
    )
    assert r.exit_code == 0, r.output
    assert (tmp_path / "ans.md").exists()
    asof_json = json.loads(next(out.glob("*-asof.json")).read_text(encoding="utf-8"))
    assert asof_json["correct"] == 1

    # ask の 4 型がすべて exit 0
    for q, extra in [
        ("扶養の制度知識を分けたのはいつ？", []),
        ("2026-08 時点で扶養の年収の壁は？", []),
        ("references の記録は全体としてどう？", ["--model", "fake"]),
        ("references のファイルは何件？", []),
    ]:
        r = runner.invoke(app, ["ask", q, "--dsn", clean_db, *extra])
        assert r.exit_code == 0, (q, r.output)
    r = runner.invoke(app, ["ask", "いつ？", "--at", "2026-13", "--dsn", clean_db])
    assert r.exit_code == 2
    # --at は全体一致（受入検証 D1）。asof 以外の型でも exit 2
    for bad_at in ("2026-08-1", "x2026-08-15y"):
        r = runner.invoke(app, ["ask", "いつ？", "--at", bad_at, "--dsn", clean_db])
        assert r.exit_code == 2, (bad_at, r.output)
    r = runner.invoke(
        app,
        ["ask", "references のファイルは何件？", "--kind", "count", "--at", "2026-13",
         "--dsn", clean_db],
    )  # fmt: skip
    assert r.exit_code == 2
    r = runner.invoke(app, ["ask", "x", "--kind", "bogus", "--dsn", clean_db])
    assert r.exit_code == 2  # 語彙外の --kind は overview に落ちない
