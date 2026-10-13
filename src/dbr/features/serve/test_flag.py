"""DB 停止の検知フラグ（DB・モデル不要）.

同期の DB 接続失敗 2 回連続で書く（DB 以外の失敗は数えない）・成功で消す・ask の接続失敗で即書く。

監視役は故障注入で検証してから完了扱いにする（「異常を OK と報告する故障」が最悪の形）。
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

import psycopg
import pytest

import dbr.features.serve as serve_mod
from dbr.features.serve import Resources, make_server
from dbr.features.serve.client import _request, health
from dbr.features.serve.usage import iter_records
from dbr.shared.embed.fake import FakeEmbedder


def _resources(
    runner: Any, dsn: str = "postgresql://dbr:dbr@127.0.0.1:5432/unused"
) -> Resources:
    return Resources(
        dsn=dsn,
        embedder_for=lambda _n: FakeEmbedder(),
        model="fake",
        sync_runner=runner,
    )


def test_flag_appears_after_two_consecutive_failures_and_clears_on_success() -> None:
    fail = {"on": True}

    def runner(_dsn: str, _emb: Any) -> dict[str, Any]:
        if fail["on"]:
            raise psycopg.errors.ConnectionTimeout("connection timeout expired")
        return {"changed": False}

    res = _resources(runner)
    assert not serve_mod.FLAG_PATH.exists()

    with pytest.raises(psycopg.OperationalError):
        res.run_sync()
    assert res.consecutive_sync_failures == 1
    assert not serve_mod.FLAG_PATH.exists()  # 1 回は一過性を許す
    assert res.health()["db_unreachable"] is False

    with pytest.raises(psycopg.OperationalError):
        res.run_sync()
    assert res.consecutive_sync_failures == 2
    body = serve_mod.FLAG_PATH.read_text(encoding="utf-8")
    assert "ConnectionTimeout: connection timeout expired" in body
    assert "docker start dbr_pg" in body
    h = res.health()
    assert h["db_unreachable"] is True and h["consecutive_sync_failures"] == 2

    fail["on"] = False
    res.run_sync()
    assert not serve_mod.FLAG_PATH.exists()
    assert res.consecutive_sync_failures == 0
    assert res.health()["db_unreachable"] is False


def test_non_db_sync_failures_do_not_raise_the_db_flag() -> None:
    """正本の取り込み拒否など DB 以外の失敗が続いても「DB に接続できません」とは言わない（必須 3）."""

    def runner(_dsn: str, _emb: Any) -> dict[str, Any]:
        raise ValueError("references/private.md は取り込まない")

    res = _resources(runner)
    for _ in range(3):
        with pytest.raises(ValueError):
            res.run_sync()
    assert res.consecutive_sync_failures == 0
    assert not serve_mod.FLAG_PATH.exists()
    assert res.last_sync is not None and "private.md" in str(res.last_sync["error"])


def test_mark_db_unreachable_writes_reason() -> None:
    res = _resources(lambda _d, _e: {"changed": False})
    res.mark_db_unreachable("ask: ConnectionTimeout: connection timeout expired")
    assert "ConnectionTimeout" in serve_mod.FLAG_PATH.read_text(encoding="utf-8")


@pytest.fixture
def dead_db_server() -> Iterator[int]:
    """DB の居ないポート（127.0.0.1:1）を指す常駐。ask は接続段で落ちる."""
    res = _resources(
        lambda _d, _e: {"changed": False},
        dsn="postgresql://dbr:dbr@127.0.0.1:1/dbr?connect_timeout=2",
    )
    srv = make_server(0, res)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.1})
    t.start()
    try:
        yield srv.port
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


def test_ask_connection_failure_flags_immediately_and_is_logged(
    dead_db_server: int,
) -> None:
    port = dead_db_server
    assert not serve_mod.FLAG_PATH.exists()
    status, data = _request(
        port,
        "/ask",
        {
            "question": "好きな食べ物",
            "opts": {"kind": "find", "model": "fake"},
            "client": "mcp",
        },
        30.0,
    )
    assert status == 500 and data["code"] == 1
    assert "OperationalError" in data["error"] or "connect" in data["error"].lower()
    assert serve_mod.FLAG_PATH.exists()  # 1 回で即（利用者がいま困っている信号）
    h = health(port)
    assert h is not None and h["db_unreachable"] is True
    recs = iter_records()
    assert len(recs) == 1
    r = recs[0]
    assert r["client"] == "mcp" and r["status"] == "error" and r["code"] == 1
    assert r["question"] == "好きな食べ物" and r["ms"] > 0
    assert "n_hits" not in r


def test_unreadable_body_still_leaves_one_usage_line(dead_db_server: int) -> None:
    """壊れた JSON・非オブジェクトも 400 を返しつつ client=other で 1 行残す（必須 2）."""
    import urllib.error
    import urllib.request

    from dbr.features.serve import HOST

    for raw in (b'{"question": "x", "client": "mcp"', b'["x"]'):
        req = urllib.request.Request(
            f"http://{HOST}:{dead_db_server}/ask",
            data=raw,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(urllib.error.HTTPError) as err:
            urllib.request.urlopen(req, timeout=5.0)
        assert err.value.code == 400
    recs = iter_records()
    assert [(r["client"], r["status"], r["code"]) for r in recs] == [
        ("other", "error", 2),
        ("other", "error", 2),
    ]
    assert all(r["question"] == "" for r in recs)
    assert not serve_mod.FLAG_PATH.exists()  # 本文不正は DB 停止ではない
