"""DB 接続の唯一の入口。psycopg.connect を直接呼ばず、必ずここを通す."""

from __future__ import annotations

import os

import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row

from dbr.shared.db.loopback import LoopbackViolation, assert_loopback

__all__ = ["LoopbackViolation", "connect", "resolve_dsn"]

ENV_DSN = "DBR_DSN"


def resolve_dsn(explicit: str | None = None) -> str:
    """--dsn 引数 → 環境変数 DBR_DSN の順。どちらも無ければ例外."""
    dsn = explicit or os.environ.get(ENV_DSN)
    if not dsn:
        raise ValueError(f"DSN が未指定です（--dsn か環境変数 {ENV_DSN}）")
    return dsn


def connect(dsn: str) -> psycopg.Connection[dict[str, object]]:
    """ループバック検査を通してから接続する（検査は接続前）.

    host が `localhost` のときは `127.0.0.1` に置き換える。Windows では localhost が
    先に ::1 へ解決され、Docker Desktop は 127.0.0.1 にしかポートを出さないため、
    IPv6 側のタイムアウト（実測 130 秒）を待ってから IPv4 に落ちる（2026-09-29 実測）。
    """
    assert_loopback(dsn)
    info = conninfo_to_dict(dsn)
    if str(info.get("host", "")).lower() == "localhost":
        info["host"] = "127.0.0.1"
    info.setdefault("connect_timeout", 5)
    return psycopg.connect(make_conninfo("", **info), row_factory=dict_row)
