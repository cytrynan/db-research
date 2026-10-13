"""フラグ → 自動復旧 → 同期 → フラグ消滅 の合流（DB・docker 不要・同期的に走らせる）."""

from __future__ import annotations

from typing import Any

import pytest

import dbr.features.serve as serve_mod
from dbr.features.serve import Resources, SyncBusy
from dbr.features.serve.recovery import Recoverer
from dbr.features.serve.test_recovery import Clock, FakeDocker
from dbr.shared.embed.fake import FakeEmbedder


def _resources(
    docker: FakeDocker, *, probe: Any = lambda: True, **kw: Any
) -> tuple[Resources, list[str]]:
    calls: list[str] = []

    def runner(_dsn: str, _emb: Any) -> dict[str, Any]:
        calls.append("sync")
        return {"changed": False}

    clock = Clock()
    rec = Recoverer(
        probe, runner=docker, now=clock.now, sleep=clock.sleep, poll_s=1.0, **kw
    )
    res = Resources(
        dsn="postgresql://dbr:dbr@127.0.0.1:5432/unused",
        embedder_for=lambda _n: FakeEmbedder(),
        model="fake",
        sync_runner=runner,
        recoverer=rec,
        recover_in_thread=False,
    )
    return res, calls


def test_recovered_triggers_sync_and_clears_flag() -> None:
    docker = FakeDocker("exited 137")
    res, calls = _resources(docker)
    res.mark_db_unreachable("ask: ConnectionTimeout")
    assert docker.actions() == ["start"]
    assert calls == ["sync"]
    assert not serve_mod.FLAG_PATH.exists()  # 同期成功で消えた
    h = res.health()
    assert h["last_recovery"]["status"] == "recovered" and h["auto_recover"] is True
    assert h["db_unreachable"] is False


def test_not_ready_leaves_flag_with_attempt_note() -> None:
    docker = FakeDocker("running 0")
    res, calls = _resources(docker, probe=lambda: False, wait_ready_s=0.0)
    res.mark_db_unreachable("sync: ConnectionTimeout")
    assert docker.actions() == ["restart"] and calls == []
    body = serve_mod.FLAG_PATH.read_text(encoding="utf-8")
    assert "自動復旧" in body and "started_not_ready" in body
    assert res.health()["last_recovery"]["status"] == "started_not_ready"


def test_clean_stop_note_tells_how_to_start() -> None:
    docker = FakeDocker("exited 0")
    res, calls = _resources(docker)
    res.mark_db_unreachable("sync: ConnectionTimeout")
    assert docker.actions() == [] and calls == []
    body = serve_mod.FLAG_PATH.read_text(encoding="utf-8")
    assert "skipped_clean_stop" in body and "docker start dbr_pg" in body


def test_disabled_recoverer_never_calls_docker() -> None:
    docker = FakeDocker("running 0")
    res, calls = _resources(docker, enabled=False)
    res.mark_db_unreachable("x")
    assert docker.calls == [] and calls == []
    assert res.health()["auto_recover"] is False
    assert res.health()["last_recovery"]["status"] == "skipped_disabled"
    assert serve_mod.FLAG_PATH.exists()


def test_append_does_not_recreate_a_cleared_flag() -> None:
    """同期が消した後の追記はフラグを作らない（P3。"a" だと作ってしまう）."""
    serve_mod._clear_flag()
    serve_mod._append_flag("自動復旧 …")
    assert not serve_mod.FLAG_PATH.exists()
    serve_mod._write_flag("x")
    serve_mod._append_flag("追記")
    assert serve_mod.FLAG_PATH.read_text(encoding="utf-8").rstrip().endswith("追記")


def test_without_recoverer_only_flag_is_written() -> None:
    res = Resources(
        dsn="postgresql://dbr:dbr@127.0.0.1:5432/unused",
        embedder_for=lambda _n: FakeEmbedder(),
        model="fake",
    )
    res.mark_db_unreachable("x")
    assert serve_mod.FLAG_PATH.exists() and res.health()["last_recovery"] is None
    assert res.health()["auto_recover"] is False


def test_sync_busy_after_recovery_is_tolerated() -> None:
    """復旧直後に同期が走行中なら飛ばす（例外にしない）。フラグは次の周期で消える."""
    docker = FakeDocker("exited 137")
    res, calls = _resources(docker)
    res._sync_lock.acquire()  # 同期が走行中の体
    try:
        res.mark_db_unreachable("x")
    finally:
        res._sync_lock.release()
    assert calls == [] and res.health()["last_recovery"]["status"] == "recovered"
    assert serve_mod.FLAG_PATH.exists()
    with pytest.raises(
        SyncBusy
    ):  # 同じ状況の素の run_sync は SyncBusy を投げる＝握ったのは _recover
        res._sync_lock.acquire()
        try:
            res.run_sync()
        finally:
            res._sync_lock.release()


def test_skipped_healthy_also_runs_sync_and_clears_flag() -> None:
    """running のまま接続障害が自然復旧した場合: 打たずに同期へ合流しフラグを消す（2 巡目の必須 2）."""
    docker = FakeDocker("running 0")
    res, calls = _resources(docker, probe=lambda: True)
    res.mark_db_unreachable("ask: ConnectionTimeout")
    assert docker.actions() == []  # 状態変更コマンドは 0 回
    assert calls == ["sync"]
    assert not serve_mod.FLAG_PATH.exists()
    assert res.health()["last_recovery"]["status"] == "skipped_healthy"
