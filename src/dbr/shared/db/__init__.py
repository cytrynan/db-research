"""DB 接続の唯一の入口。psycopg.connect を直接呼ばず、必ずここを通す."""

from __future__ import annotations

from typing import TYPE_CHECKING

from dbr.shared.db.dsn import ENV_DSN, LoopbackViolation, resolve_dsn
from dbr.shared.db.loopback import assert_loopback, effective_conninfo

if TYPE_CHECKING:
    import psycopg

__all__ = [
    "ENV_DSN",
    "LoopbackViolation",
    "assert_loopback",
    "connect",
    "resolve_dsn",
]


def connect(
    dsn: str, *, connect_timeout: int | None = None
) -> psycopg.Connection[dict[str, object]]:
    """ループバック検査を通してから接続する（検査は接続前・環境変数の影響を遮断）.

    connect_timeout（秒）は DSN の値を上書きする。自動復旧の生存確認（短く待ちたい）が使う。
    """
    # psycopg（約 0.3 秒）は接続する時に初めて読む。CLI の起動（常駐経由の ask）を軽く保つため
    import psycopg
    from psycopg.rows import dict_row

    if connect_timeout is None:
        return psycopg.connect(effective_conninfo(dsn), row_factory=dict_row)
    return psycopg.connect(
        effective_conninfo(dsn), row_factory=dict_row, connect_timeout=connect_timeout
    )
