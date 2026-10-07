"""DSN の解決とループバック違反の例外。psycopg を import しない軽い層.

CLI の起動時（特に常駐経由の `dbr ask`）に psycopg（約 0.3 秒）を読み込まないため、
`resolve_dsn` と `LoopbackViolation` はここに置き、`shared/db/__init__.py` と
`shared/db/loopback.py` から再エクスポートする（既存の import 経路は変えない）。
"""

from __future__ import annotations

import os
from pathlib import Path

ENV_DSN = "DBR_DSN"
# 環境変数が無いときに読むリポ直下の .env（README の `cp .env.example .env`）。cwd は見ない:
# MCP は Claude Code の cwd で起き、そこから起こした常駐も DSN を持たずに即死していた（2026-10-07〜08）
ENV_FILE = Path(__file__).resolve().parents[4] / ".env"


class LoopbackViolation(Exception):
    """DSN の接続先がループバック以外だった（host / hostaddr / service）."""

    def __init__(self, host: str | None, *, reason: str = "host") -> None:
        self.host = host
        self.reason = reason
        super().__init__(
            f"拒否: 個人データの DB はローカル接続のみ（{reason}={host!r}）。"
            " localhost / 127.0.0.1 / ::1 を指定してください"
        )


def dsn_from_env_file(path: Path) -> str | None:
    """.env から DBR_DSN の値だけを読む（他のキーは os.environ に流さない）。無ければ None."""
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()  # BOM 付きでも読む
    except OSError:
        return None
    # cp932 で保存された等。場所を言わないと原因が追えない（素の UnicodeDecodeError はパス無し）
    except UnicodeDecodeError as exc:
        raise ValueError(f"{path} を UTF-8 で読めません（{exc}）") from exc
    for line in lines:
        key, sep, value = line.partition("=")
        if sep and key.strip() == ENV_DSN:
            return value.strip().strip("'\"") or None
    return None


def resolve_dsn(explicit: str | None = None) -> str:
    """--dsn 引数 → 環境変数 DBR_DSN → リポ直下 .env の DBR_DSN の順。どれも無ければ例外.

    ループバック検査はここでなく下流（`connect()` / `assert_loopback`）で効く。
    """
    dsn = explicit or os.environ.get(ENV_DSN) or dsn_from_env_file(ENV_FILE)
    if not dsn:
        raise ValueError(
            f"DSN が未指定です（--dsn・環境変数 {ENV_DSN}・{ENV_FILE} のいずれか）"
        )
    return dsn


__all__ = [
    "ENV_DSN",
    "ENV_FILE",
    "LoopbackViolation",
    "dsn_from_env_file",
    "resolve_dsn",
]
