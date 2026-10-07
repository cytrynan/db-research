"""CLI の配線テスト（DB 不要）: exit code 規約と境界の入口."""

from pathlib import Path

from typer.testing import CliRunner

from dbr.cli import app

runner = CliRunner()
REMOTE = "postgresql://dbr:dbr@example.com:5432/dbr"


def test_migrate_remote_dsn_exits_3() -> None:
    result = runner.invoke(app, ["migrate", "--dsn", REMOTE])
    assert result.exit_code == 3
    assert "example.com" in result.output


def test_ingest_remote_dsn_exits_3(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["ingest", str(tmp_path), "--bundle", "dev", "--dsn", REMOTE]
    )
    assert result.exit_code == 3


def test_ingest_unknown_bundle_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["ingest", str(tmp_path), "--bundle", "nope", "--dsn", REMOTE]
    )
    assert result.exit_code == 2
    assert "references" in result.output


def test_count_unknown_view_exits_2() -> None:
    result = runner.invoke(app, ["count", "nope", "--dsn", REMOTE])
    assert result.exit_code == 2
    assert "v_by_bundle" in result.output


def test_count_remote_dsn_exits_3() -> None:
    result = runner.invoke(app, ["count", "v_by_bundle", "--dsn", REMOTE])
    assert result.exit_code == 3


def test_missing_dsn_is_an_error(monkeypatch, tmp_path: Path) -> None:  # type: ignore[no-untyped-def]
    from dbr.shared.db import dsn

    monkeypatch.delenv("DBR_DSN", raising=False)
    # 実リポの .env を読ませない
    monkeypatch.setattr(dsn, "ENV_FILE", tmp_path / "no.env")
    result = runner.invoke(app, ["count", "v_by_bundle"])
    assert result.exit_code != 0


def test_scope_defaults_share_the_same_constants() -> None:
    """ask・bench・overview・run_find の既定が DEFAULT_SCOPE/DEFAULT_BOOST そのもの（受入検証 R3）.

    値でなく同一オブジェクトで照合する（リテラル 1.0 の直書きは別オブジェクトになる）。
    """
    import inspect

    from dbr import cli
    from dbr.features import scope as sc
    from dbr.features.bench import run_find
    from dbr.features.overview import answer

    for fn in (cli.ask, cli.bench, answer, run_find):
        assert inspect.signature(fn).parameters["boost_w"].default is sc.DEFAULT_BOOST
    for fn in (cli.ask, answer):
        assert inspect.signature(fn).parameters["scope"].default is sc.DEFAULT_SCOPE
