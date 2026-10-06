"""Resources.run_sync の重なり（DB・モデル不要）: wait=False は飛ばす、wait=True は待って走る."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from dbr.features.serve import Resources, SyncBusy
from dbr.shared.embed.fake import FakeEmbedder


def _resources(gate: threading.Event, calls: list[str]) -> Resources:
    def runner(_dsn: str, _emb: Any) -> dict[str, Any]:
        calls.append("start")
        gate.wait(timeout=5)
        calls.append("end")
        return {"changed": False}

    return Resources(
        dsn="postgresql://dbr:dbr@127.0.0.1:5432/unused",
        embedder_for=lambda _n: FakeEmbedder(),
        model="fake",
        sync_runner=runner,
    )


def test_wait_false_skips_while_running_and_wait_true_waits() -> None:
    gate = threading.Event()
    calls: list[str] = []
    res = _resources(gate, calls)

    first = threading.Thread(target=res.run_sync)  # 定期スレッド相当（wait=False）
    first.start()
    for _ in range(200):  # runner が走り始めるまで
        if calls:
            break
        threading.Event().wait(0.01)
    assert calls == ["start"] and res.sync_running is True

    with pytest.raises(SyncBusy):  # 重なった周期は飛ばす
        res.run_sync()

    done: list[dict[str, Any]] = []
    second = threading.Thread(target=lambda: done.append(res.run_sync(wait=True)))
    second.start()  # HTTP /sync 相当: 終わるのを待つ
    second.join(timeout=0.3)
    assert second.is_alive() and done == []  # まだ待っている

    gate.set()  # 1 回目が終わる → 2 回目が走る
    first.join(timeout=5)
    second.join(timeout=5)
    assert not second.is_alive()
    assert calls == ["start", "end", "start", "end"]
    assert done == [{"changed": False}]
    assert res.sync_running is False and res.last_sync is not None
    assert res.last_sync["error"] is None
