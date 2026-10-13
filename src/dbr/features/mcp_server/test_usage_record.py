"""MCP 入口の利用ログ: 常駐を起こせなかった失敗は常駐側に記録されないので、入口が 1 行残す."""

from __future__ import annotations

import pytest

from dbr.features import mcp_server as m
from dbr.features.serve.usage import iter_records


def test_daemon_unavailable_is_recorded_with_question(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(m, "ensure_daemon", lambda _p: False)
    with pytest.raises(RuntimeError, match="起こせません"):
        m.tool_ask("メガネの度数どこ？", k=3)
    recs = iter_records()
    assert len(recs) == 1
    r = recs[0]
    assert r["client"] == "mcp" and r["status"] == "daemon_unavailable"
    assert r["question"] == "メガネの度数どこ？" and r["k"] == 3
    assert "起こせません" in r["error"] and r["kind"] is None


def test_successful_relay_does_not_double_log(monkeypatch: pytest.MonkeyPatch) -> None:
    """成功は常駐側が書く。入口で二重に書かない."""
    monkeypatch.setattr(m, "ensure_daemon", lambda _p: True)
    monkeypatch.setattr(m, "ask_remote", lambda *_a, **_k: {"kind": "find", "hits": []})
    m.tool_ask("x")
    assert iter_records() == []
