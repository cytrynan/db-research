"""DSN の解決とループバック違反の例外。psycopg を import しない軽い層.

CLI の起動時（特に常駐経由の `dbr ask`）に psycopg（約 0.3 秒）を読み込まないため、
`resolve_dsn` と `LoopbackViolation` はここに置き、`shared/db/__init__.py` と
`shared/db/loopback.py` から再エクスポートする（既存の import 経路は変えない）。
"""

from __future__ import annotations

import os

ENV_DSN = "DBR_DSN"


class LoopbackViolation(Exception):
    """DSN の接続先がループバック以外だった（host / hostaddr / service）."""

    def __init__(self, host: str | None, *, reason: str = "host") -> None:
        self.host = host
        self.reason = reason
        super().__init__(
            f"拒否: 個人データの DB はローカル接続のみ（{reason}={host!r}）。"
            " localhost / 127.0.0.1 / ::1 を指定してください"
        )


def resolve_dsn(explicit: str | None = None) -> str:
    """--dsn 引数 → 環境変数 DBR_DSN の順。どちらも無ければ例外."""
    dsn = explicit or os.environ.get(ENV_DSN)
    if not dsn:
        raise ValueError(f"DSN が未指定です（--dsn か環境変数 {ENV_DSN}）")
    return dsn


__all__ = ["ENV_DSN", "LoopbackViolation", "resolve_dsn"]
