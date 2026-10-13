"""DB の自動復旧（D-21）: フラグが立つ時に `dbr_pg` を docker で起こす.

2026-10-08〜13 に DB コンテナが「稼働中なのに応答しない」まま 3 日放置された。検知（D-20 の
フラグ）だけでは次に人が座るまで直らないので、常駐が自分で `docker` を打つ。

- 打つのは `docker inspect` / `restart` / `unpause` / `start` の 4 つだけ。コンテナ名は定数（J1）
- **exit code 0 で止まっている（手で `docker stop` した）コンテナは起こさない**（J2）
- 1 常駐あたり 10 分に 1 回まで（再起動ループ防止・J3）。進行中の試行があれば待たずに戻る
- 復旧の成功判定は「DB に接続して SELECT 1 が返る」こと（コンテナの状態ではない・J5）。
  **操作の直前にも 1 回見て、既に届くなら何も打たない**（受入検証 2026-10-13 P2）
- probe は別スレッドで走らせ、残り時間で打ち切る（接続後に固まる DB でも attempt は必ず返る・P1）
- Docker 自体が居ない／応答しないときは記録して終わる（Docker Desktop の復旧は人の作業・J6）
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any

CONTAINER = (
    "dbr_pg"  # compose.yaml の container_name と同じ。環境変数からは取らない（J1）
)
COOLDOWN_S = 600.0
WAIT_READY_S = 60.0
CMD_TIMEOUT_S = 60.0
POLL_S = 2.0
PRECHECK_S = 5.0  # 操作直前の生存確認に使う上限
ENV_NO_AUTO_RECOVER = "DBR_NO_AUTO_RECOVER"

STATUSES = frozenset(
    {
        "recovered",  # 打って、DB に接続できた
        "started_not_ready",  # 打ったが、待ち時間内に DB へ接続できなかった
        "skipped_healthy",  # 打つ直前の確認で DB に届いた（別の経路で復旧済み）
        "skipped_clean_stop",  # exit 0 で止まっている＝手で止めた。触らない
        "skipped_cooldown",  # 前回の試行から 10 分経っていない
        "skipped_in_progress",  # 別スレッドの試行が走行中
        "skipped_disabled",  # --no-auto-recover / DBR_NO_AUTO_RECOVER=1
        "docker_unavailable",  # docker が無い・応答しない・inspect が失敗
        "failed",  # docker コマンドが非 0 で終わった／扱えない状態／予期しない例外
    }
)

Runner = Callable[[list[str]], tuple[int, str]]


def default_runner(argv: list[str]) -> tuple[int, str]:
    """docker を実行して (returncode, 出力の先頭) を返す。docker が無ければ FileNotFoundError をそのまま上げる."""
    try:
        proc = subprocess.run(  # 引数は定数の組み合わせだけ（J1）
            argv,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=CMD_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return 124, f"timeout {CMD_TIMEOUT_S:.0f}s"
    out = (proc.stdout or "") + (proc.stderr or "")
    return int(proc.returncode), out.strip()[:200]


@dataclass(frozen=True)
class RecoveryResult:
    at: str
    action: str  # restart | unpause | start | none
    status: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class _TimedProbe:
    """probe を別スレッドで 1 回走らせ、答えが出るまで待つ（上限つき）。固まった probe は置き去りにする."""

    def __init__(self, probe: Callable[[], bool]) -> None:
        self._probe = probe
        self._thread: threading.Thread | None = None
        self._answer: bool | None = None

    def _run(self) -> None:
        try:
            self._answer = bool(self._probe())
        except Exception:  # 接続失敗は「まだ」扱い
            self._answer = False

    def poll(self, wait_s: float) -> bool | None:
        """答えが出れば True/False、上限内に出なければ None（次回の poll は同じ試行を待つ）."""
        if self._thread is None or (
            not self._thread.is_alive() and self._answer is not None
        ):
            self._answer = None
            self._thread = threading.Thread(
                target=self._run, daemon=True, name="dbr-probe"
            )
            self._thread.start()
        self._thread.join(max(0.0, wait_s))
        if self._thread.is_alive():
            return None
        return self._answer


class Recoverer:
    """1 常駐に 1 つ。`attempt()` は同時に 1 件だけ走り、抑止時間を跨いだ再試行だけ docker を打つ."""

    def __init__(
        self,
        probe: Callable[[], bool],
        *,
        runner: Runner = default_runner,
        now: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        enabled: bool = True,
        container: str = CONTAINER,
        cooldown_s: float = COOLDOWN_S,
        wait_ready_s: float = WAIT_READY_S,
        poll_s: float = POLL_S,
        precheck_s: float = PRECHECK_S,
    ) -> None:
        self._probe = probe
        self._runner = runner
        self._now = now
        self._sleep = sleep
        self._enabled = enabled
        self.container = container
        self.cooldown_s = cooldown_s
        self.wait_ready_s = wait_ready_s
        self.poll_s = poll_s
        self.precheck_s = precheck_s
        self.last: RecoveryResult | None = None
        self._last_attempt_at: float | None = None
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self._enabled and os.environ.get(ENV_NO_AUTO_RECOVER, "") != "1"

    def _result(self, action: str, status: str, detail: str) -> RecoveryResult:
        assert status in STATUSES
        res = RecoveryResult(
            at=datetime.now(UTC).isoformat(timespec="seconds"),
            action=action,
            status=status,
            detail=detail[:200],
        )
        self.last = res
        return res

    def _inspect(self) -> tuple[str, int] | None:
        """(State.Status, State.ExitCode)。docker が応答しない・コンテナが無いときは None."""
        rc, out = self._runner(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.Status}} {{.State.ExitCode}}",
                self.container,
            ]
        )
        if rc != 0:
            return None
        parts = out.split()
        if len(parts) != 2:
            return None
        try:
            return parts[0], int(parts[1])
        except ValueError:
            return None

    def attempt(self, reason: str) -> RecoveryResult:
        """1 回の復旧試行。呼び手（同期スレッド・HTTP ハンドラ）は別スレッドから呼ぶ（J4）.

        別の試行が走行中なら待たずに `skipped_in_progress` を返す（障害中の要求が行列を作り、
        復旧後に古い要求が健全な DB を再起動するのを防ぐ・P2）。
        """
        if not self.enabled:
            return self._result("none", "skipped_disabled", reason)
        if not self._lock.acquire(blocking=False):
            return self._result("none", "skipped_in_progress", reason)
        try:
            return self._attempt_locked(reason)
        except (
            Exception
        ) as exc:  # runner の OSError 等。結果として残し、呼び手には上げない
            return self._result("none", "failed", f"{type(exc).__name__}: {exc}")
        finally:
            self._lock.release()

    def _attempt_locked(self, reason: str) -> RecoveryResult:
        # 先に状態を見る（inspect は無害）。手で止めた停止は抑止中でも「触らない」と正しく言う
        try:
            state = self._inspect()
        except FileNotFoundError:
            return self._result("none", "docker_unavailable", "docker が見つからない")
        if state is None:
            return self._result(
                "none",
                "docker_unavailable",
                "docker inspect が失敗（Docker 停止かコンテナ不在）",
            )
        status, code = state
        if status == "running":
            action = "restart"
        elif status == "paused":
            action = "unpause"
        elif status in ("exited", "created", "dead"):
            if status == "exited" and code == 0:
                return self._result(
                    "none",
                    "skipped_clean_stop",
                    "exit 0 で停止＝手で止められています。復旧: docker start dbr_pg",
                )
            action = "start"
        else:  # restarting / removing
            return self._result("none", "failed", f"扱えない状態 {status}")
        t = self._now()
        if (
            self._last_attempt_at is not None
            and t - self._last_attempt_at < self.cooldown_s
        ):
            remain = self.cooldown_s - (t - self._last_attempt_at)
            return self._result(
                "none",
                "skipped_cooldown",
                f"前回の試行から {remain:.0f} 秒（状態 {status}/{code}）",
            )
        # 操作の直前にもう 1 回 DB を見る。既に届くなら打たない（P2。running の時だけ意味がある）
        if (
            status == "running"
            and _TimedProbe(self._probe).poll(self.precheck_s) is True
        ):
            return self._result(
                "none", "skipped_healthy", f"状態 {status}/{code}・DB 接続 OK"
            )
        self._last_attempt_at = t
        try:
            rc, out = self._runner(["docker", action, self.container])
        except FileNotFoundError:
            return self._result(action, "docker_unavailable", "docker が見つからない")
        if rc != 0:
            return self._result(action, "failed", f"docker {action} exit {rc}: {out}")
        return self._wait_ready(action, f"{status}/{code}")

    def _wait_ready(self, action: str, before: str) -> RecoveryResult:
        """DB に届くまで wait_ready_s を上限に待つ。probe が固まっても上限で必ず返る（P1）."""
        deadline = self._now() + self.wait_ready_s
        probe = _TimedProbe(self._probe)
        while True:
            remaining = deadline - self._now()
            if remaining <= 0:
                return self._result(
                    action,
                    "started_not_ready",
                    f"docker {action} は成功したが {self.wait_ready_s:.0f} 秒以内に DB へ接続できない",
                )
            answer = probe.poll(min(self.poll_s, remaining))
            if answer is True:
                return self._result(action, "recovered", f"{before} → DB 接続 OK")
            if answer is False:
                # 残り時間を超えて眠らない（2 巡目の必須 1: 上限 wait_ready_s を守る）
                remaining = deadline - self._now()
                if remaining <= 0:
                    continue  # ループ先頭で started_not_ready
                self._sleep(min(self.poll_s, remaining))


__all__ = [
    "CONTAINER",
    "COOLDOWN_S",
    "ENV_NO_AUTO_RECOVER",
    "STATUSES",
    "WAIT_READY_S",
    "Recoverer",
    "RecoveryResult",
    "default_runner",
]
