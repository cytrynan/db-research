"""常駐サーバーへの薄いクライアント（CLI・MCP が使う）。torch 等は import しない.

- `health()`: 0.3 秒で応答が無ければ「居ない」とみなす
- `ensure_daemon()`: 居なければ `python -m dbr.cli serve` を切り離して起こし、health が
  ok になるまで待つ（モデル読み込み込みで既定 90 秒）
- `ask_remote()`: /ask に投げて `answer()` と同じ dict を返す。サーバー側の AskError は
  同じ code の AskError として投げ直す
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from typing import Any

from dbr.features.ask import AskError, AskOptions
from dbr.features.serve import (
    DEFAULT_PORT,
    ENV_NO_DAEMON,
    HOST,
    LOG_PATH,
    STATE_DIR,
)

# 居るかどうかの問い合わせ。0.3 秒だと起動直後の同期（CPU で埋め込み計算中）に応答が遅れて
# 「居ない」と誤判定し、二重起動→bind 失敗→単発へ倒れることがあった（2026-10-06 実測:
# serve.log に ConnectionAbortedError）。/health の処理自体は数 ms なので 2 秒で十分
HEALTH_TIMEOUT = 2.0
ASK_TIMEOUT = 300.0  # overview の LLM は 1 回答 37〜198 秒（v9）
START_TIMEOUT = 90.0


def daemon_disabled() -> bool:
    return os.environ.get(ENV_NO_DAEMON, "") == "1"


def _url(port: int, path: str) -> str:
    return f"http://{HOST}:{port}{path}"


def _request(
    port: int, path: str, payload: Mapping[str, Any] | None, timeout: float
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(
        _url(port, path), data=data, headers=headers, method="POST" if data else "GET"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            return int(resp.status), _loads(body)
    except urllib.error.HTTPError as exc:  # 4xx/5xx も本文を読む
        body = exc.read().decode("utf-8", errors="replace")
        return int(exc.code), _loads(body)


def _loads(body: str) -> dict[str, Any]:
    try:
        data = json.loads(body or "{}")
    except json.JSONDecodeError:
        return {"error": body[:200], "code": 1}
    return data if isinstance(data, dict) else {"error": "非オブジェクト", "code": 1}


def health(
    port: int = DEFAULT_PORT, *, timeout: float = HEALTH_TIMEOUT
) -> dict[str, Any] | None:
    """居れば /health の dict、居なければ None（接続拒否・タイムアウト・応答不正）."""
    try:
        status, data = _request(port, "/health", None, timeout)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return None
    if status != 200 or data.get("status") != "ok":
        return None
    return data


def ask_remote(
    question: str,
    opts: AskOptions,
    *,
    port: int = DEFAULT_PORT,
    timeout: float = ASK_TIMEOUT,
) -> dict[str, Any]:
    status, data = _request(
        port, "/ask", {"question": question, "opts": opts.to_dict()}, timeout
    )
    if status != 200:
        raise AskError(
            int(data.get("code", 1)), str(data.get("error", f"HTTP {status}"))
        )
    return data


def sync_remote(port: int = DEFAULT_PORT, *, timeout: float = 3600.0) -> dict[str, Any]:
    status, data = _request(port, "/sync", {}, timeout)
    if status != 200:
        raise RuntimeError(str(data.get("error", f"HTTP {status}")))
    return data


def stop_daemon(port: int = DEFAULT_PORT) -> bool:
    """居れば止めて True。居なければ False."""
    if health(port) is None:
        return False
    try:
        status, _ = _request(port, "/shutdown", {}, 5.0)
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError):
        return False
    return status == 200


def serve_command(port: int) -> list[str]:
    """切り離して起こすコマンド。uv の仮想環境の python を使う（dbr が入っている）."""
    return [sys.executable, "-m", "dbr.cli", "serve", "--port", str(port)]


def _detached_flags() -> int:
    # Windows: 親（CLI）が終わっても生き残る。他 OS では 0（start_new_session で代替）
    return int(getattr(subprocess, "DETACHED_PROCESS", 0)) | int(
        getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    )


def spawn_daemon(port: int, *, popen: Callable[..., Any] = subprocess.Popen) -> Any:
    """常駐を切り離して起こす。stdout/stderr は ~/.dbr/serve.log へ."""
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    log = LOG_PATH.open("a", encoding="utf-8")
    try:
        return popen(
            serve_command(port),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            close_fds=True,
            creationflags=_detached_flags(),
            start_new_session=(os.name != "nt"),
            env=dict(os.environ),
        )
    finally:
        log.close()  # 子はハンドルを継承済み。親側は閉じてよい


def ensure_daemon(
    port: int = DEFAULT_PORT,
    *,
    start_timeout: float = START_TIMEOUT,
    spawn: Callable[[int], Any] = spawn_daemon,
    probe: Callable[[int], dict[str, Any] | None] = health,
    sleep: Callable[[float], None] = time.sleep,
    now: Callable[[], float] = time.monotonic,
    poll_s: float = 0.5,
) -> bool:
    """居なければ起こして待つ。待ち切れなければ False（呼び手は単発経路へ倒す）.

    起こした子が先に終わった（モデル未取得で exit 5・ポート使用中 等）ときは、90 秒待たずに
    すぐ False を返す（2 巡目の観察 4: 以前は子の終了を見ず上限まで待っていた）。
    """
    if probe(port) is not None:
        return True
    proc = spawn(port)
    deadline = now() + start_timeout
    while now() < deadline:
        sleep(poll_s)
        if probe(port) is not None:
            return True
        poll = getattr(proc, "poll", None)
        if callable(poll) and poll() is not None:
            return False  # 子が終了＝起動失敗。理由は ~/.dbr/serve.log
    return False


def describe_route(argv: Sequence[str]) -> str:  # pragma: no cover - 説明用
    return " ".join(argv)


__all__ = [
    "ASK_TIMEOUT",
    "HEALTH_TIMEOUT",
    "START_TIMEOUT",
    "ask_remote",
    "daemon_disabled",
    "ensure_daemon",
    "health",
    "serve_command",
    "spawn_daemon",
    "stop_daemon",
    "sync_remote",
]
