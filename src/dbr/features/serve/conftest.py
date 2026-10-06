"""serve のテストが実運用のログ `~/.dbr/serve.log` に書かないように退避先を tmp に向ける.

追加レビュー（2026-10-06）の観察: テスト一式の経路名・件数の行が実ログに混ざっていた。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import dbr.features.serve as serve_mod


@pytest.fixture(autouse=True)
def _serve_log_to_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(serve_mod, "STATE_DIR", tmp_path / ".dbr")
    monkeypatch.setattr(serve_mod, "LOG_PATH", tmp_path / ".dbr" / "serve.log")
