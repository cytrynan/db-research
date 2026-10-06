"""D-17: 語彙に当たらない質問は exit 2 で止めず、探し物として検索する（判定器は unknown のまま）."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from dbr.cli import app
from dbr.features.ingest import run
from dbr.features.ingest.embed import run_embed
from dbr.shared.embed.fake import FakeEmbedder
from tests.integration.conftest import FIXTURES

pytestmark = pytest.mark.db

# PRD の CLI 例文そのもの。2026-10-05 の実測では exit 2 で止まっていた
HELD_OUT = "Codex の起動で PATH の罠は何だった？"


def _prepare(dsn: str) -> None:
    run(FIXTURES / "okf-plain", "dev", dsn, log=lambda _m: None)
    for variant in ("plain", "ctx"):
        run_embed("dev", variant, dsn, FakeEmbedder())  # type: ignore[arg-type]


def test_unknown_question_falls_back_to_find(clean_db: str) -> None:
    _prepare(clean_db)
    runner = CliRunner()
    r = runner.invoke(
        app, ["ask", HELD_OUT, "--model", "fake", "--dsn", clean_db, "--json"]
    )
    assert r.exit_code == 0, r.output
    data = json.loads(r.output.strip().splitlines()[-1])
    assert data["kind"] == "find" and data["kind_fallback"] is True
    assert "推定" in data["reason"] and data["hits"]
    # テキスト出力にも推定である旨が出る
    r = runner.invoke(app, ["ask", HELD_OUT, "--model", "fake", "--dsn", clean_db])
    assert r.exit_code == 0 and "探し物として検索（推定）" in r.output, r.output
    # 判定器そのものは正直なまま
    r = runner.invoke(app, ["classify", HELD_OUT, "--json"])
    assert r.exit_code == 0 and json.loads(r.output)["kind"] == "unknown"


def test_explicit_kind_is_not_a_fallback(clean_db: str) -> None:
    _prepare(clean_db)
    r = CliRunner().invoke(
        app,
        ["ask", HELD_OUT, "--kind", "find", "--model", "fake", "--dsn", clean_db, "--json"],
    )  # fmt: skip
    assert r.exit_code == 0, r.output
    data = json.loads(r.output.strip().splitlines()[-1])
    assert data["kind"] == "find" and data["kind_fallback"] is False


def test_option_errors_still_exit_2_before_fallback(clean_db: str) -> None:
    r = CliRunner().invoke(app, ["ask", HELD_OUT, "--kind", "bogus", "--dsn", clean_db])
    assert r.exit_code == 2
    r = CliRunner().invoke(app, ["ask", HELD_OUT, "--at", "2026-13", "--dsn", clean_db])
    assert r.exit_code == 2
