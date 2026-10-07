"""DSN の解決順（--dsn → 環境変数 → リポ直下 .env）のユニット（DB 不要）."""

from __future__ import annotations

from pathlib import Path

import pytest

from dbr.shared.db import dsn as d

FILE_DSN = "postgresql://dbr:dbr@127.0.0.1:5432/from_file"
ENV_VALUE = "postgresql://dbr:dbr@127.0.0.1:5432/from_env"


@pytest.fixture
def env_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / ".env"
    monkeypatch.setattr(d, "ENV_FILE", path)
    monkeypatch.delenv(d.ENV_DSN, raising=False)
    return path


def test_env_file_is_the_repo_root_dotenv() -> None:
    assert d.ENV_FILE.name == ".env"
    assert (d.ENV_FILE.parent / "pyproject.toml").is_file()


def test_falls_back_to_env_file(env_file: Path) -> None:
    env_file.write_text(
        f"# コメント DBR_DSN=x\n\nOTHER=1\nDBR_DSN={FILE_DSN}\n", "utf-8"
    )
    assert d.resolve_dsn() == FILE_DSN


def test_env_var_wins_over_env_file(
    env_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file.write_text(f"DBR_DSN={FILE_DSN}\n", "utf-8")
    monkeypatch.setenv(d.ENV_DSN, ENV_VALUE)
    assert d.resolve_dsn() == ENV_VALUE


def test_explicit_wins_over_everything(
    env_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file.write_text(f"DBR_DSN={FILE_DSN}\n", "utf-8")
    monkeypatch.setenv(d.ENV_DSN, ENV_VALUE)
    assert d.resolve_dsn("postgresql://x@127.0.0.1/y") == "postgresql://x@127.0.0.1/y"


def test_env_file_tolerates_bom_quotes_and_spaces(env_file: Path) -> None:
    env_file.write_text(f'﻿ DBR_DSN = "{FILE_DSN}" \n', "utf-8")
    assert d.resolve_dsn() == FILE_DSN


def test_env_file_does_not_leak_other_keys(
    env_file: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DBR_SOMETHING_ELSE", raising=False)
    env_file.write_text(f"DBR_SOMETHING_ELSE=1\nDBR_DSN={FILE_DSN}\n", "utf-8")
    d.resolve_dsn()
    import os

    assert "DBR_SOMETHING_ELSE" not in os.environ


def test_undecodable_env_file_names_the_file(env_file: Path) -> None:
    """cp932 で保存された .env は素の UnicodeDecodeError でなく、場所つきの ValueError（受入検証の指摘）."""
    env_file.write_bytes(f"# 日本語のコメント\nDBR_DSN={FILE_DSN}\n".encode("cp932"))
    with pytest.raises(ValueError, match="UTF-8 で読めません") as err:
        d.resolve_dsn()
    assert str(env_file) in str(err.value)


@pytest.mark.parametrize("content", [None, "", "OTHER=1\n", "DBR_DSN=\n"])
def test_missing_everywhere_is_an_error_naming_the_file(
    env_file: Path, content: str | None
) -> None:
    if content is not None:
        env_file.write_text(content, "utf-8")
    with pytest.raises(ValueError, match="未指定") as err:
        d.resolve_dsn()
    assert str(env_file) in str(err.value)
