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


def test_missing_dsn_is_an_error(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.delenv("DBR_DSN", raising=False)
    result = runner.invoke(app, ["count", "v_by_bundle"])
    assert result.exit_code != 0
