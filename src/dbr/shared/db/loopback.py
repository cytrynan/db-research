"""接続先がループバックであることを、接続を試みる前に検査する.

個人データを置く DB は手元でしか動かさない（docs/decisions.md D-5）。
文章の規範ではなく機構で止めるため、全ての接続はこの検査を通る。

検査するのは `host` だけではない。libpq は `hostaddr` があれば `host` より優先して
そのアドレスへ繋ぎ、`PGHOSTADDR` 環境変数でも同じことが起きる（2026-09-29 受入検証で
反例が出た）。そのため ①`hostaddr` も同じ許可集合で検査し ②`service`（外部ファイルで
接続先を差し替えられる）は拒否し ③接続時は `hostaddr` を明示して環境変数を無効化する。
"""

from __future__ import annotations

# 例外は psycopg 不要の層（dsn.py）に置き、ここから再エクスポートする（既存の import 経路を保つ）。
# psycopg.conninfo は各関数の中で import する（モジュール読み込みを軽く保つ。CLI の起動用）
from dbr.shared.db.dsn import LoopbackViolation

__all__ = [
    "LOOPBACK_ADDRS",
    "LOOPBACK_HOSTS",
    "LoopbackViolation",
    "assert_loopback",
    "effective_conninfo",
    "host_of",
]

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})
LOOPBACK_ADDRS = frozenset({"127.0.0.1", "::1"})


def host_of(dsn: str) -> str | None:
    """DSN（URI または key=value 形式）からホスト名を取り出す。無ければ None."""
    from psycopg.conninfo import conninfo_to_dict

    info = conninfo_to_dict(dsn)
    host = info.get("host")
    return str(host) if host is not None else None


def assert_loopback(dsn: str) -> None:
    """接続先がループバックでなければ LoopbackViolation を投げる.

    - `host` 無し（Unix ソケット想定）も拒否する。Windows では存在せず、
      「どこに繋ぐか分からない」状態を通さないため。
    - `hostaddr` があれば同じ許可集合で検査する（`host` より優先されるため）。
    - `service` は接続先を外部ファイルで差し替えられるので拒否する。
    """
    from psycopg.conninfo import conninfo_to_dict

    info = conninfo_to_dict(dsn)
    if "service" in info:
        raise LoopbackViolation(str(info["service"]), reason="service")
    host = info.get("host")
    if host is None or str(host).lower() not in LOOPBACK_HOSTS:
        raise LoopbackViolation(str(host) if host is not None else None)
    hostaddr = info.get("hostaddr")
    if hostaddr is not None and str(hostaddr) not in LOOPBACK_ADDRS:
        raise LoopbackViolation(str(hostaddr), reason="hostaddr")


def effective_conninfo(dsn: str) -> str:
    """検査済み DSN を、実際に接続する形に正規化して返す（純粋関数・テスト可能）.

    - `localhost` → `127.0.0.1`（Windows で ::1 が先に解決され Docker に届かない実測）
    - `hostaddr` を明示して `PGHOSTADDR` 等の環境変数を無効化する
    - `connect_timeout` 既定 5 秒
    """
    from psycopg.conninfo import conninfo_to_dict, make_conninfo

    assert_loopback(dsn)
    info = conninfo_to_dict(dsn)
    host = str(info["host"]).lower()
    if host == "localhost":
        host = "127.0.0.1"
    info["host"] = host
    info["hostaddr"] = "::1" if host == "::1" else "127.0.0.1"
    info.setdefault("connect_timeout", 5)
    return make_conninfo("", **info)
