"""client のユニット（ネットワーク・プロセス起動なし）: 自動起動の待ち方・環境変数・コマンド."""

from __future__ import annotations

import sys
from typing import Any

import pytest

from dbr.features.serve import DEFAULT_PORT, ENV_NO_DAEMON, ENV_PORT, port_from_env
from dbr.features.serve.client import (
    daemon_disabled,
    ensure_daemon,
    serve_command,
)


def test_port_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_PORT, raising=False)
    assert port_from_env() == DEFAULT_PORT
    monkeypatch.setenv(ENV_PORT, "50000")
    assert port_from_env() == 50000
    monkeypatch.setenv(ENV_PORT, "abc")
    with pytest.raises(ValueError):
        port_from_env()
    monkeypatch.setenv(ENV_PORT, "70000")
    with pytest.raises(ValueError):
        port_from_env()


def test_daemon_disabled_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_NO_DAEMON, raising=False)
    assert daemon_disabled() is False
    monkeypatch.setenv(ENV_NO_DAEMON, "1")
    assert daemon_disabled() is True


def test_serve_command_uses_this_interpreter() -> None:
    cmd = serve_command(47821)
    assert cmd[0] == sys.executable
    assert cmd[1:] == ["-m", "dbr.cli", "serve", "--port", "47821"]


def _clock() -> Any:
    """now() と sleep() を同じ仮想時計で動かす（実時間を使わない）."""
    state = {"t": 0.0}

    def now() -> float:
        return state["t"]

    def sleep(s: float) -> None:
        state["t"] += s

    return now, sleep


def test_ensure_daemon_returns_true_without_spawn_when_already_up() -> None:
    spawned: list[int] = []
    now, sleep = _clock()
    ok = ensure_daemon(
        1,
        spawn=spawned.append,
        probe=lambda _p: {"status": "ok"},
        sleep=sleep,
        now=now,
    )
    assert ok is True and spawned == []


def test_ensure_daemon_spawns_then_waits_until_health_ok() -> None:
    spawned: list[int] = []
    probes = iter([None, None, None, {"status": "ok"}])  # 起動前・待ち 2 回・ok
    now, sleep = _clock()
    ok = ensure_daemon(
        2,
        start_timeout=90.0,
        spawn=spawned.append,
        probe=lambda _p: next(probes),
        sleep=sleep,
        now=now,
        poll_s=0.5,
    )
    assert ok is True and spawned == [2]
    assert now() == pytest.approx(1.5)  # 3 回待った


class _Exited:
    """起こした子がすぐ終わったことを模す（code は exit code）."""

    def __init__(self, code: int) -> None:
        self.code = code

    def poll(self) -> int:
        return self.code


def test_ensure_daemon_stops_waiting_when_child_exits_with_model_missing() -> None:
    # 2 巡目の観察 4: 以前は子の終了を見ずに 90 秒待っていた
    now, sleep = _clock()
    ok = ensure_daemon(
        4,
        start_timeout=90.0,
        spawn=lambda _p: _Exited(5),
        probe=lambda _p: None,
        sleep=sleep,
        now=now,
        poll_s=0.5,
    )
    assert ok is False
    assert now() == pytest.approx(0.5)  # 1 回待っただけで諦めた


def test_ensure_daemon_keeps_waiting_when_port_was_taken_by_another_session() -> None:
    # 別セッションが同時に起こした常駐が bind 済み（自分の子は exit 6）→ そちらが答えるまで待つ
    probes = iter([None, None, None, {"status": "ok"}])
    now, sleep = _clock()
    ok = ensure_daemon(
        5,
        start_timeout=90.0,
        spawn=lambda _p: _Exited(6),
        probe=lambda _p: next(probes),
        sleep=sleep,
        now=now,
        poll_s=0.5,
    )
    assert ok is True
    assert now() == pytest.approx(1.5)


def test_ensure_daemon_stops_on_other_failures_too() -> None:
    # DSN 未設定（exit 1）・ループバック違反（exit 3）は待たない（追加レビューの観察 A）
    for code in (1, 3):
        now, sleep = _clock()

        def spawn(_p: int, c: int = code) -> _Exited:
            return _Exited(c)

        ok = ensure_daemon(
            6,
            start_timeout=90.0,
            spawn=spawn,
            probe=lambda _p: None,
            sleep=sleep,
            now=now,
            poll_s=0.5,
        )
        assert ok is False and now() == pytest.approx(0.5), code


def test_ensure_daemon_gives_up_after_timeout() -> None:
    spawned: list[int] = []
    now, sleep = _clock()
    ok = ensure_daemon(
        3,
        start_timeout=2.0,
        spawn=spawned.append,
        probe=lambda _p: None,
        sleep=sleep,
        now=now,
        poll_s=0.5,
    )
    assert ok is False and spawned == [3]
    assert now() >= 2.0
