"""常駐サーバー（F8）: 埋め込みモデルを 1 回だけ読み、ループバック HTTP で ask / sync に答える.

2026-10-05 の実測では `dbr ask` 1 回につき 25〜29 秒かかり、その大半がモデルの読み込み
（オフラインでも約 20 秒）だった。モデルを持ったプロセスを常駐させ、CLI と MCP はそこへ
JSON を投げる薄いクライアントになる（D-18）。

- bind は **127.0.0.1 固定**（引数で変えられない。D-5 と同じ境界。認証は持たない＝
  単一利用者の PC で、ローカルプロセスは正本ファイルも直接読める）
- `GET /health` / `POST /ask` / `POST /sync` / `POST /shutdown` の 4 経路だけ
- 埋め込み器・並べ直し器・LLM は名前ごとに 1 個保持し、推論は Lock で直列化する
- 同期（features/sync）は起動直後に 1 回、以後 `sync_interval_min` 分ごとに別スレッドで走る
- ログは `~/.dbr/serve.log`（件数・時刻だけ。質問文も本文も書かない）
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from dbr.features.ask import AskError, AskOptions, answer
from dbr.shared.embed import DEFAULT_MODEL, Embedder, get_embedder
from dbr.shared.llm import get_llm
from dbr.shared.rerank import Reranker, get_reranker

HOST = "127.0.0.1"
DEFAULT_PORT = 47821
ENV_PORT = "DBR_PORT"
ENV_NO_DAEMON = "DBR_NO_DAEMON"
DEFAULT_SYNC_INTERVAL_MIN = 30
STATE_DIR = Path.home() / ".dbr"
LOG_PATH = STATE_DIR / "serve.log"
MAX_BODY = 64 * 1024  # 質問とオプションだけ。本文は来ない
KNOWN_ROUTES = frozenset({"/health", "/ask", "/sync", "/shutdown"})


def port_from_env(default: int = DEFAULT_PORT) -> int:
    raw = os.environ.get(ENV_PORT)
    if not raw:
        return default
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"{ENV_PORT} は整数（{raw!r}）") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{ENV_PORT} は 1〜65535（{port}）")
    return port


def _log_line(message: str) -> None:
    """件数・時刻だけを書く。失敗しても呼び手を止めない（ログは補助）."""
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        with LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(f"{datetime.now(UTC).isoformat(timespec='seconds')} {message}\n")
    except OSError:
        pass


class _Locked:
    """推論を直列化する薄い包み（CPU 推論の安全側）。name / dims は中身に委譲."""

    def __init__(self, inner: Any) -> None:
        self._inner = inner
        self._lock = threading.Lock()

    @property
    def name(self) -> str:
        return str(self._inner.name)

    @property
    def dims(self) -> int:
        return int(getattr(self._inner, "dims", 0))

    def embed_passages(self, texts: list[str]) -> list[list[float]]:
        with self._lock:
            return list(self._inner.embed_passages(texts))

    def embed_query(self, text: str) -> list[float]:
        with self._lock:
            return list(self._inner.embed_query(text))

    def score(self, query: str, passages: list[str]) -> list[float]:
        with self._lock:
            return list(self._inner.score(query, passages))

    def generate(self, *args: Any, **kwargs: Any) -> Any:
        with self._lock:
            return self._inner.generate(*args, **kwargs)


class SyncBusy(Exception):
    """同期が走行中（409）."""


@dataclass
class Resources:
    """プロセスに 1 つ。モデルのキャッシュと同期の状態を持つ."""

    dsn: str
    embedder_for: Callable[[str], Embedder] = get_embedder
    reranker_for: Callable[[str], Reranker] = get_reranker
    llm_for: Callable[[str], Any] = get_llm
    # 同期の実行体。省略時は features/sync.run_sync（テストでは差し替える）
    sync_runner: Callable[[str, Embedder], Mapping[str, Any]] | None = None
    model: str = DEFAULT_MODEL
    started_at: float = field(default_factory=time.monotonic)
    last_sync: dict[str, Any] | None = None
    sync_running: bool = False
    _cache: dict[tuple[str, str], Any] = field(default_factory=dict)
    _load_lock: threading.Lock = field(default_factory=threading.Lock)
    _sync_lock: threading.Lock = field(default_factory=threading.Lock)

    def _get(self, kind: str, name: str, loader: Callable[[str], Any]) -> Any:
        key = (kind, name)
        with self._load_lock:  # 同じモデルを 2 回読まない
            if key not in self._cache:
                self._cache[key] = _Locked(loader(name))
            return self._cache[key]

    def embedder(self, name: str) -> Embedder:
        got: Embedder = self._get("embed", name, self.embedder_for)
        return got

    def reranker(self, name: str) -> Reranker:
        got: Reranker = self._get("rerank", name, self.reranker_for)
        return got

    def llm(self, name: str) -> Any:
        return self._get("llm", name, self.llm_for)

    def loaded(self) -> list[str]:
        return sorted(f"{k}:{n}" for k, n in self._cache)

    def run_sync(self, *, wait: bool = False) -> dict[str, Any]:
        """同期を 1 回走らせる。走行中なら wait=False は SyncBusy、wait=True は終わるのを待って走る.

        定期スレッドは wait=False（重なったら飛ばす）、HTTP の /sync は wait=True
        （起動直後の同期と重なっても 409 にせず、最新の状態を返す）。
        """
        if not self._sync_lock.acquire(blocking=wait):
            raise SyncBusy("同期が走行中")
        self.sync_running = True
        t0 = time.monotonic()
        try:
            runner = self.sync_runner or _default_sync_runner
            report = dict(runner(self.dsn, self.embedder(self.model)))
            self.last_sync = {
                "at": datetime.now(UTC).isoformat(timespec="seconds"),
                "seconds": round(time.monotonic() - t0, 1),
                "changed": bool(report.get("changed", False)),
                "error": None,
            }
            _log_line(
                f"sync ok {self.last_sync['seconds']}s changed={self.last_sync['changed']}"
            )
            return report
        except Exception as exc:  # 同期の失敗で常駐を止めない（次回また試す）
            self.last_sync = {
                "at": datetime.now(UTC).isoformat(timespec="seconds"),
                "seconds": round(time.monotonic() - t0, 1),
                "changed": False,
                "error": f"{type(exc).__name__}: {exc}"[:200],
            }
            _log_line(f"sync error {self.last_sync['error']}")
            raise
        finally:
            self.sync_running = False
            self._sync_lock.release()

    def health(self) -> dict[str, Any]:
        return {
            "status": "ok",
            "pid": os.getpid(),
            "model": self.model,
            "loaded": self.loaded(),
            "uptime_s": round(time.monotonic() - self.started_at, 1),
            "last_sync": self.last_sync,
            "sync_running": self.sync_running,
        }


def _default_sync_runner(dsn: str, embedder: Embedder) -> Mapping[str, Any]:
    from dbr.features.sync import run_sync

    report = run_sync(dsn, embedder, log=_log_line)
    out = dict(report.to_dict())
    out.setdefault("changed", report.changed())
    return out


class DbrServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False  # 二重起動を bind 失敗で検知する

    def __init__(self, port: int, resources: Resources) -> None:
        super().__init__((HOST, port), _Handler)
        self.resources = resources
        self.stopping = False

    def handle_error(self, request: Any, client_address: Any) -> None:
        """クライアントが先に切った等の例外はトレースバックでなく 1 行だけ残す.

        実測（2026-10-06）: 起動直後の同期中に health の問い合わせ（当時 0.3 秒）が待ち切れず
        切断 → ConnectionAbortedError のトレースバックが serve.log に 5 回出た。
        """
        exc = sys.exc_info()[1]
        _log_line(f"client error {type(exc).__name__ if exc else 'unknown'}")

    @property
    def port(self) -> int:
        return int(self.server_address[1])


def _status_for(code: int) -> HTTPStatus:
    return {
        2: HTTPStatus.BAD_REQUEST,
        3: HTTPStatus.FORBIDDEN,
        5: HTTPStatus.SERVICE_UNAVAILABLE,
    }.get(code, HTTPStatus.INTERNAL_SERVER_ERROR)


class _Handler(BaseHTTPRequestHandler):
    server: DbrServer
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: Any) -> None:
        """stderr に出さない。経路は既知の 4 つだけ名前で残す（未知の path 文字列は書かない）."""
        # リクエスト行が壊れていると self.path / self.command が無いまま呼ばれる（2 巡目の観察 1）
        route = str(getattr(self, "path", "") or "").split("?")[0]
        method = str(getattr(self, "command", "") or "")
        _log_line(
            f"{method if method in ('GET', 'POST') else 'other'} "
            f"{route if route in KNOWN_ROUTES else 'other'}"
        )

    def _send(self, status: HTTPStatus, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False, default=str).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise AskError(2, "Content-Length は整数") from exc
        # 負値は read(-1)＝無制限読みになり上限検査を回避できる（受入検証 2026-10-06 の観察）
        if not 0 <= length <= MAX_BODY:
            raise AskError(2, f"本文の長さが範囲外（{length}。上限 {MAX_BODY}）")
        raw = self.rfile.read(length) if length else b"{}"
        try:
            data = json.loads(raw.decode("utf-8") or "{}")
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AskError(2, f"JSON を読めません: {exc}") from exc
        if not isinstance(data, dict):
            raise AskError(2, "本文は JSON オブジェクト")
        return data

    def do_GET(self) -> None:
        if self.path.split("?")[0] == "/health":
            self._send(HTTPStatus.OK, self.server.resources.health())
            return
        self._send(HTTPStatus.NOT_FOUND, {"error": "not found", "code": 2})

    def do_POST(self) -> None:
        path = self.path.split("?")[0]
        res = self.server.resources
        try:
            if path == "/ask":
                data = self._read_json()
                question = data.get("question")
                if not isinstance(question, str) or not question.strip():
                    raise AskError(2, "question は空でない文字列")
                opts = AskOptions.from_dict(data.get("opts") or {})
                out = answer(
                    question,
                    opts,
                    dsn=res.dsn,
                    embedder_for=res.embedder,
                    reranker_for=res.reranker,
                    llm_for=res.llm,
                )
                self._send(HTTPStatus.OK, out)
                return
            if path == "/sync":
                try:
                    report = res.run_sync(wait=True)
                except SyncBusy:  # wait=True では起きないが、契約として残す
                    self._send(
                        HTTPStatus.CONFLICT, {"error": "同期が走行中", "code": 1}
                    )
                    return
                self._send(HTTPStatus.OK, report)
                return
            if path == "/shutdown":
                self.server.stopping = True
                self._send(HTTPStatus.OK, {"status": "stopping"})
                threading.Thread(target=self.server.shutdown, daemon=True).start()
                return
            self._send(HTTPStatus.NOT_FOUND, {"error": "not found", "code": 2})
        except AskError as exc:
            self._send(_status_for(exc.code), {"error": str(exc), "code": exc.code})
        except Exception as exc:  # 1 リクエストの失敗で常駐を落とさない
            _log_line(f"error {type(exc).__name__}")
            self._send(
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"{type(exc).__name__}: {exc}"[:300], "code": 1},
            )


def make_server(port: int, resources: Resources) -> DbrServer:
    """bind だけして返す（テストは port=0 で空きポートを取る）."""
    return DbrServer(port, resources)


def _sync_loop(server: DbrServer, interval_s: float, stop: threading.Event) -> None:
    """起動直後に 1 回、以後 interval ごと。失敗しても次の周期で再試行する."""
    while not stop.is_set():
        try:
            server.resources.run_sync()
        except SyncBusy:
            pass
        except Exception:  # run_sync 側で last_sync.error に記録済み
            pass
        if stop.wait(interval_s):
            break


def serve(
    port: int,
    dsn: str,
    *,
    sync_interval_min: int = DEFAULT_SYNC_INTERVAL_MIN,
    resources: Resources | None = None,
    ready: threading.Event | None = None,
) -> int:
    """常駐の本体。shutdown まで返らない。戻り値は実際に bind したポート."""
    res = resources or Resources(dsn=dsn)
    server = make_server(port, res)
    stop = threading.Event()
    _log_line(
        f"start pid={os.getpid()} port={server.port} sync_interval={sync_interval_min}"
    )
    try:
        # モデルは起動時に読んでおく（最初の質問を待たせない）
        res.embedder(res.model)
        if sync_interval_min > 0:
            threading.Thread(
                target=_sync_loop,
                args=(server, sync_interval_min * 60.0, stop),
                daemon=True,
                name="dbr-sync",
            ).start()
        if ready is not None:
            ready.set()
        server.serve_forever(poll_interval=0.5)
    finally:
        stop.set()
        server.server_close()
        _log_line("stop")
    return server.port


__all__ = [
    "DEFAULT_PORT",
    "DEFAULT_SYNC_INTERVAL_MIN",
    "ENV_NO_DAEMON",
    "ENV_PORT",
    "HOST",
    "LOG_PATH",
    "DbrServer",
    "Resources",
    "SyncBusy",
    "make_server",
    "port_from_env",
    "serve",
]
