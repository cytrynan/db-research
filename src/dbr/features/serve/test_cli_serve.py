"""`dbr serve` の CLI 層（ネットワーク・モデルなし）: モデル未取得は単発 ask と同じ exit 5."""

from __future__ import annotations

from typing import Any

import pytest
from typer.testing import CliRunner

import dbr.features.serve as serve_mod
import dbr.features.serve.client as client_mod
from dbr.cli import app
from dbr.shared.embed import EmbedderUnavailable
from dbr.shared.embed.offline import ONLINE_HINT

LOOPBACK_DSN = "postgresql://dbr:dbr@127.0.0.1:5432/dbr_test"


def test_serve_exits_5_with_hint_when_model_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # 受入検証 2026-10-06 指摘 2: 起動時のモデル読み込み失敗が exit 1 で落ちていた
    def boom(*_a: Any, **_k: Any) -> int:
        raise EmbedderUnavailable(f"x を読み込めません: offline。{ONLINE_HINT}")

    monkeypatch.setattr(serve_mod, "serve", boom)
    monkeypatch.setattr(client_mod, "health", lambda *_a, **_k: None)
    r = CliRunner().invoke(
        app, ["serve", "--port", "1", "--sync-interval", "0", "--dsn", LOOPBACK_DSN]
    )
    assert r.exit_code == 5, r.output
    assert "DBR_HF_ONLINE=1" in r.output


def test_serve_refuses_non_loopback_dsn_before_loading_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        serve_mod, "serve", lambda *_a, **_k: pytest.fail("モデル読み込みに進んだ")
    )
    monkeypatch.setattr(client_mod, "health", lambda *_a, **_k: None)
    r = CliRunner().invoke(
        app,
        ["serve", "--port", "1", "--dsn", "postgresql://dbr:dbr@example.com:5432/dbr"],
    )
    assert r.exit_code == 3, r.output
