"""自動復旧のユニット（docker・DB 不要）: 状態ごとの分岐・抑止・無効化・故障注入."""

from __future__ import annotations

import threading
import time
from typing import Any

import pytest

from dbr.features.serve import recovery as r


class FakeDocker:
    """docker の代わり。inspect の返事と各コマンドの終了コードを決め、呼ばれた argv を記録する."""

    def __init__(
        self, state: str | None = "running 0", *, rc: int = 0, missing: bool = False
    ) -> None:
        self.state = state
        self.rc = rc
        self.missing = missing
        self.calls: list[list[str]] = []

    def __call__(self, argv: list[str]) -> tuple[int, str]:
        if self.missing:
            raise FileNotFoundError("docker")
        self.calls.append(argv)
        if argv[1] == "inspect":
            return (0, self.state) if self.state is not None else (1, "No such object")
        return self.rc, "" if self.rc == 0 else "Error response from daemon"

    def actions(self) -> list[str]:
        return [c[1] for c in self.calls if c[1] != "inspect"]


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0

    def now(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.t += s


def _recoverer(
    docker: FakeDocker,
    *,
    probe: Any = lambda: True,
    clock: Clock | None = None,
    **kw: Any,
) -> tuple[r.Recoverer, Clock]:
    clock = clock or Clock()
    kw.setdefault("poll_s", 1.0)
    rec = r.Recoverer(probe, runner=docker, now=clock.now, sleep=clock.sleep, **kw)
    return rec, clock


def _down_then_up() -> Any:
    """1 回目（操作直前の確認）は届かない → 操作後は届く."""
    answers = iter([False])
    return lambda: next(answers, True)


@pytest.mark.parametrize(
    ("state", "action"),
    [
        ("running 0", "restart"),
        ("paused 0", "unpause"),
        ("exited 137", "start"),
        ("exited 255", "start"),
        ("dead 1", "start"),
    ],
)
def test_action_follows_container_state(state: str, action: str) -> None:
    docker = FakeDocker(state)
    rec, _ = _recoverer(docker, probe=_down_then_up())
    res = rec.attempt("sync: ConnectionTimeout")
    assert res.status == "recovered" and res.action == action
    assert docker.actions() == [action]
    assert docker.calls[-1] == ["docker", action, "dbr_pg"]


def test_clean_stop_is_left_alone() -> None:
    """exit 0＝手で docker stop した。K の意思なので起こさない（J2）."""
    docker = FakeDocker("exited 0")
    rec, _ = _recoverer(docker)
    res = rec.attempt("x")
    assert res.status == "skipped_clean_stop" and res.action == "none"
    assert docker.actions() == [] and "docker start dbr_pg" in res.detail


def test_docker_missing_or_inspect_failing() -> None:
    rec, _ = _recoverer(FakeDocker(missing=True))
    assert rec.attempt("x").status == "docker_unavailable"
    rec2, _ = _recoverer(FakeDocker(None))  # No such object
    assert rec2.attempt("x").status == "docker_unavailable"
    rec3, _ = _recoverer(FakeDocker("garbage"))  # 形が違う
    assert rec3.attempt("x").status == "docker_unavailable"


def test_disabled_by_flag_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    docker = FakeDocker()
    rec, _ = _recoverer(docker, enabled=False)
    assert rec.attempt("x").status == "skipped_disabled" and docker.calls == []
    rec2, _ = _recoverer(docker)
    monkeypatch.setenv(r.ENV_NO_AUTO_RECOVER, "1")
    assert rec2.attempt("x").status == "skipped_disabled" and docker.calls == []


def test_clean_stop_is_reported_even_during_cooldown() -> None:
    """抑止中でも手動停止は正しく見分ける（実機 2026-10-13: 抑止判定が先だと skipped_cooldown になった）."""
    docker = FakeDocker("running 0")
    rec, clock = _recoverer(docker, probe=_down_then_up())
    assert rec.attempt("a").status == "recovered"
    docker.state = "exited 0"
    clock.t += 10
    assert rec.attempt("b").status == "skipped_clean_stop"
    docker.state = "running 0"
    assert rec.attempt("c").status == "skipped_cooldown"
    assert docker.actions() == ["restart"]


def test_cooldown_blocks_second_attempt_until_elapsed() -> None:
    docker = FakeDocker()
    rec, clock = _recoverer(
        docker, probe=lambda: False, cooldown_s=600.0, wait_ready_s=0.0
    )
    assert rec.attempt("a").status == "started_not_ready"
    clock.t += 100
    second = rec.attempt("b")
    assert second.status == "skipped_cooldown" and "秒" in second.detail
    assert docker.actions() == [
        "restart"
    ]  # 2 回目は inspect だけで docker 操作を打たない
    clock.t += 600
    assert rec.attempt("c").status == "started_not_ready"
    assert docker.actions() == ["restart", "restart"]


def test_failed_command_is_reported_and_not_retried_in_cooldown() -> None:
    """故障注入: docker restart が非 0 → failed。抑止中は再試行しない（R3）."""
    docker = FakeDocker("running 0", rc=1)
    rec, clock = _recoverer(docker, probe=lambda: False)
    res = rec.attempt("x")
    assert res.status == "failed" and res.action == "restart"
    assert "exit 1" in res.detail
    clock.t += 1
    assert rec.attempt("x").status == "skipped_cooldown"
    assert docker.actions() == ["restart"]


def test_not_ready_after_wait_and_probe_exceptions_count_as_not_ready() -> None:
    calls = {"n": 0}

    def probe() -> bool:
        calls["n"] += 1
        raise ConnectionError("still down")

    docker = FakeDocker("exited 137")
    rec, _clock = _recoverer(docker, probe=probe, wait_ready_s=10.0)
    res = rec.attempt("x")
    assert res.status == "started_not_ready" and res.action == "start"
    assert calls["n"] >= 10  # 1 秒ごとに 10 秒待った
    assert rec.last is res and res.to_dict()["status"] == "started_not_ready"


def test_hung_probe_still_returns_within_deadline() -> None:
    """probe が固まっても attempt は上限で返る（P1）。残り時間が 0 で started_not_ready."""
    gate = threading.Event()

    def hung_probe() -> bool:
        gate.wait(30)  # テスト終了時に解放する
        return True

    docker = FakeDocker("exited 137")
    # 期限の消費は join（実時間）で起きるので、この試験は実時計で走らせる
    rec = r.Recoverer(hung_probe, runner=docker, wait_ready_s=1.0, poll_s=0.2)
    t0 = time.monotonic()
    res = rec.attempt("x")
    gate.set()
    assert res.status == "started_not_ready"
    assert time.monotonic() - t0 < 5.0  # 実時間でも固まらない
    assert docker.actions() == ["start"]


def test_precheck_skips_restart_when_db_already_healthy() -> None:
    """running なら操作直前に DB を見て、届くなら打たない（P2）."""
    docker = FakeDocker("running 0")
    rec, _ = _recoverer(docker, probe=lambda: True)
    res = rec.attempt("古い要求")
    assert res.status == "skipped_healthy" and docker.actions() == []
    # exited は precheck せず start する（止まっている DB に接続は試さない）
    docker2 = FakeDocker("exited 137")
    rec2, _ = _recoverer(docker2, probe=lambda: True)
    assert rec2.attempt("x").status == "recovered" and docker2.actions() == ["start"]


def test_concurrent_attempt_returns_in_progress_without_waiting() -> None:
    started = threading.Event()
    release = threading.Event()

    def slow_probe() -> bool:
        started.set()
        release.wait(30)
        return True

    docker = FakeDocker("exited 137")
    rec, _ = _recoverer(docker, probe=slow_probe, wait_ready_s=5.0, poll_s=0.2)
    out: list[Any] = []
    t = threading.Thread(target=lambda: out.append(rec.attempt("a")))
    t.start()
    assert started.wait(5)
    second = rec.attempt("b")
    assert second.status == "skipped_in_progress"
    release.set()
    t.join(10)
    assert out and out[0].status == "recovered"
    assert docker.actions() == ["start"]


def test_runner_os_error_is_recorded_as_failed() -> None:
    def bad_runner(_argv: list[str]) -> tuple[int, str]:
        raise PermissionError("denied")

    rec = r.Recoverer(lambda: True, runner=bad_runner)
    res = rec.attempt("x")
    assert res.status == "failed" and "PermissionError" in res.detail


def test_recovered_after_db_comes_back_during_wait() -> None:
    answers = iter([False, False, False, True])  # 1 回目は操作直前の確認
    docker = FakeDocker("running 0")
    rec, clock = _recoverer(docker, probe=lambda: next(answers))
    res = rec.attempt("x")
    assert res.status == "recovered" and clock.t == 1002.0  # 2 回待った


def test_wait_never_sleeps_past_deadline() -> None:
    """False の後も残り時間を超えて眠らない（2 巡目の必須 1）. wait 1 秒・poll 2 秒 → 合計 1 秒で返る."""
    docker = FakeDocker("exited 137")
    rec, clock = _recoverer(docker, probe=lambda: False, wait_ready_s=1.0, poll_s=2.0)
    res = rec.attempt("x")
    assert res.status == "started_not_ready"
    assert clock.t == 1001.0  # 1 秒だけ進んだ（2 秒眠っていない）
