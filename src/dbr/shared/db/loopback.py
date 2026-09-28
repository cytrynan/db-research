"""接続先がループバックであることを、接続を試みる前に検査する.

個人データを置く DB は手元でしか動かさない（docs/decisions.md D-5）。
文章の規範ではなく機構で止めるため、全ての接続はこの検査を通る。
"""

from __future__ import annotations

from psycopg.conninfo import conninfo_to_dict

LOOPBACK_HOSTS = frozenset({"localhost", "127.0.0.1", "::1"})


class LoopbackViolation(Exception):
    """DSN のホストがループバック以外だった."""

    def __init__(self, host: str | None) -> None:
        self.host = host
        super().__init__(
            f"拒否: 個人データの DB はローカル接続のみ（host={host!r}）。"
            " localhost / 127.0.0.1 / ::1 を指定してください"
        )


def host_of(dsn: str) -> str | None:
    """DSN（URI または key=value 形式）からホスト名を取り出す。無ければ None."""
    info = conninfo_to_dict(dsn)
    host = info.get("host")
    return str(host) if host is not None else None


def assert_loopback(dsn: str) -> None:
    """ホストがループバックでなければ LoopbackViolation を投げる.

    ホスト無し（Unix ソケット想定）も拒否する。Windows では存在せず、
    「どこに繋ぐか分からない」状態を通さないため。
    """
    host = host_of(dsn)
    if host is None or host.lower() not in LOOPBACK_HOSTS:
        raise LoopbackViolation(host)
