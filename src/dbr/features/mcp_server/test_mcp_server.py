"""MCP 入口のユニット: ツールの公開名・入力検査・常駐への中継（ネットワークは差し替え）."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from dbr.features import mcp_server as m
from dbr.features.ask import AskError, AskOptions


def test_build_server_exposes_four_tools() -> None:
    srv = m.build_server()
    tools = asyncio.run(srv.list_tools())
    assert sorted(t.name for t in tools) == ["ask", "count", "health", "sync"]
    ask = next(t for t in tools if t.name == "ask")
    assert "question" in ask.input_schema["properties"]  # SDK 2.x は snake_case
    assert "個人記録" in (ask.description or "")


def test_tool_ask_relays_to_daemon(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def fake_ask_remote(q: str, opts: AskOptions, *, port: int) -> dict[str, Any]:
        seen.update({"q": q, "opts": opts, "port": port})
        return {"kind": "find", "hits": []}

    monkeypatch.setattr(m, "ensure_daemon", lambda _p: True)
    monkeypatch.setattr(m, "ask_remote", fake_ask_remote)
    monkeypatch.setenv("DBR_PORT", "50123")
    out = m.tool_ask("メガネの度数どこ？", kind="find", k=3)
    assert out == {"kind": "find", "hits": []}
    assert seen["q"] == "メガネの度数どこ？" and seen["port"] == 50123
    assert seen["opts"] == AskOptions(kind="find", k=3)


def test_tool_ask_rejects_bad_kind_and_k_before_network(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        m, "ensure_daemon", lambda _p: pytest.fail("ネットワークに出た")
    )
    with pytest.raises(ValueError):
        m.tool_ask("x", kind="bogus")
    with pytest.raises(ValueError):
        m.tool_ask("x", k=0)
    with pytest.raises(ValueError):
        m.tool_count("v_nope")


def test_tool_ask_maps_ask_error_to_value_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(m, "ensure_daemon", lambda _p: True)

    def boom(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise AskError(5, "モデル無し")

    monkeypatch.setattr(m, "ask_remote", boom)
    with pytest.raises(ValueError, match=r"\[exit 5\] モデル無し"):
        m.tool_ask("x")


def test_tool_health_raises_when_daemon_cannot_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(m, "ensure_daemon", lambda _p: False)
    with pytest.raises(RuntimeError, match="起こせません"):
        m.tool_health()


@pytest.mark.parametrize(
    ("tool", "args", "expected"),
    [
        ("health", {}, "起こせません"),  # RuntimeError
        ("ask", {"question": "x", "kind": "bogus"}, "kind は"),  # ValueError
    ],
)
def test_server_surfaces_anticipated_errors_to_client(
    monkeypatch: pytest.MonkeyPatch, tool: str, args: dict[str, Any], expected: str
) -> None:
    """SDK 2.x は ToolError 以外を `Error executing tool <name>` だけに潰す（2026-10-07〜08 の症状）."""
    from mcp.server.mcpserver.exceptions import ToolError, UnexpectedToolError

    monkeypatch.setattr(m, "ensure_daemon", lambda _p: False)
    srv = m.build_server()
    with pytest.raises(ToolError, match=expected) as err:
        asyncio.run(srv.call_tool(tool, args))
    assert not isinstance(err.value, UnexpectedToolError)
