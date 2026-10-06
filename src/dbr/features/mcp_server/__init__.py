"""エージェントの入口（F9）: stdio の MCP サーバー。常駐（features/serve）へ中継するだけ.

Claude Code のセッションごとに 1 プロセス起きるので、torch 等の重い import はしない
（`dbr.features.serve.client` は urllib と subprocess だけ）。モデルを持つのは常駐 1 つ。

登録（K 承認後に 1 回・README 参照）:
  claude mcp add --scope user dbr -- uv run --project C:\\Users\\meer0\\dev\\db-research dbr mcp
"""

from __future__ import annotations

from typing import Any

from dbr.features.ask import ASK_KINDS, AskError, AskOptions
from dbr.features.count import VIEWS
from dbr.features.serve import port_from_env
from dbr.features.serve.client import (
    ask_remote,
    ensure_daemon,
    sync_remote,
)
from dbr.features.serve.client import (
    health as daemon_health,
)

SERVER_NAME = "dbr"


def _port() -> int:
    return port_from_env()


def _ensure() -> int:
    port = _port()
    if not ensure_daemon(port):
        raise RuntimeError(
            f"常駐（dbr serve）を {port} 番で起こせませんでした。"
            "`dbr serve` を手で起動するか ~/.dbr/serve.log を確認してください"
        )
    return port


def tool_ask(
    question: str, kind: str = "auto", at: str | None = None, k: int = 5
) -> dict[str, Any]:
    """K の個人記録（references / dev / memory / stock / tax / scout / experiments）を質問の型で検索する.

    kind: auto（型を推定。語彙に当たらなければ探し物として検索）| find | count | asof | overview。
    at: asof 用の時点（YYYY-MM-DD / YYYY-MM）。戻り値は `dbr ask --json` と同じ dict
    （find: hits[doc, heading, score] / count: view, rows / asof: facts / overview: summaries）。
    """
    if kind not in ASK_KINDS:
        raise ValueError(f"kind は {' | '.join(ASK_KINDS)}")
    if not 1 <= k <= 50:
        raise ValueError("k は 1〜50")
    opts = AskOptions(kind=kind, at=at, k=k)
    try:
        return ask_remote(question, opts, port=_ensure())
    except AskError as exc:
        raise ValueError(f"[exit {exc.code}] {exc}") from exc


def tool_count(view: str) -> dict[str, Any]:
    """② 数える: 定義済みビュー（v_by_bundle / v_by_type / v_unverified / v_verified / v_stale）の結果."""
    if view not in VIEWS:
        raise ValueError(f"view は {', '.join(sorted(VIEWS))} のいずれか")
    try:
        return ask_remote(view, AskOptions(kind="count"), port=_ensure())
    except AskError as exc:
        raise ValueError(f"[exit {exc.code}] {exc}") from exc


def tool_sync() -> dict[str, Any]:
    """正本フォルダの変更・新規・削除を DB に反映する（取り込み → 埋め込み → fact → summary）."""
    return sync_remote(_ensure())


def tool_health() -> dict[str, Any]:
    """常駐の状態（読み込み済みモデル・最後の同期）。居なければ起こしてから返す."""
    data = daemon_health(_ensure(), timeout=5.0)
    return data if data is not None else {"status": "unreachable"}


def build_server() -> Any:
    """MCPServer（SDK 2.x。1.x の FastMCP）を組み立てる。テストはツール関数を直接呼ぶ."""
    from mcp.server.mcpserver import MCPServer

    mcp = MCPServer(SERVER_NAME)
    mcp.tool(name="ask")(tool_ask)
    mcp.tool(name="count")(tool_count)
    mcp.tool(name="sync")(tool_sync)
    mcp.tool(name="health")(tool_health)
    return mcp


def run_stdio() -> None:
    build_server().run()  # stdio が既定


__all__ = [
    "SERVER_NAME",
    "build_server",
    "run_stdio",
    "tool_ask",
    "tool_count",
    "tool_health",
    "tool_sync",
]
