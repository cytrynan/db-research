"""常駐サーバーの統合（dbr_test・fake 埋め込み・空きポート）: 4 経路と、単発経路との一致."""

from __future__ import annotations

import threading
from collections.abc import Iterator
from typing import Any

import pytest

from dbr.features.ask import AskOptions, answer
from dbr.features.ingest import run
from dbr.features.ingest.embed import run_embed
from dbr.features.serve import Resources, make_server
from dbr.features.serve.client import (
    _request,
    ask_remote,
    health,
    stop_daemon,
    sync_remote,
)
from dbr.shared.embed.fake import FakeEmbedder
from dbr.shared.llm import get_llm
from dbr.shared.rerank import get_reranker
from tests.integration.conftest import FIXTURES

pytestmark = pytest.mark.db

FALLBACK_Q = "Codex の起動で PATH の罠は何だった？"


def _prepare(dsn: str) -> None:
    run(FIXTURES / "okf-plain", "dev", dsn, log=lambda _m: None)
    for variant in ("plain", "ctx"):
        run_embed("dev", variant, dsn, FakeEmbedder())  # type: ignore[arg-type]


@pytest.fixture
def server(clean_db: str) -> Iterator[tuple[int, Resources]]:
    _prepare(clean_db)
    calls: list[str] = []

    def fake_sync(dsn: str, embedder: Any) -> dict[str, Any]:
        calls.append(embedder.name)
        return {"bundles": [], "seconds": 0.0, "changed": False}

    res = Resources(
        dsn=clean_db,
        embedder_for=lambda _n: FakeEmbedder(),  # type: ignore[arg-type,return-value]
        model="fake",
        sync_runner=fake_sync,
    )
    srv = make_server(0, res)  # 空きポート
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.1})
    t.start()
    try:
        yield srv.port, res
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


def test_health_and_ask_roundtrip_matches_in_process(
    server: tuple[int, Resources],
) -> None:
    port, res = server
    h = health(port)
    assert h is not None and h["status"] == "ok" and h["model"] == "fake"
    opts = AskOptions(model="fake")
    remote = ask_remote(FALLBACK_Q, opts, port=port)
    local = answer(
        FALLBACK_Q,
        opts,
        dsn=res.dsn,
        embedder_for=lambda _n: FakeEmbedder(),  # type: ignore[arg-type,return-value]
        reranker_for=get_reranker,
        llm_for=get_llm,
    )
    # 揮発値は無い（find）。鍵集合も値も一致する＝常駐経由と単発経路は同じ計算
    assert remote == local
    assert remote["kind"] == "find" and remote["kind_fallback"] is True
    # count は 1 往復で、JSON 化で date 等が文字列になる以外は同じ
    remote_c = ask_remote("未確認の記録は何件？", AskOptions(model="fake"), port=port)
    assert remote_c["kind"] == "count" and remote_c["view"] == "v_unverified"
    h2 = health(port)
    assert h2 is not None and h2["loaded"] == ["embed:fake"]  # 2 問でモデルは 1 個だけ


def test_ask_errors_map_to_http_status_and_code(server: tuple[int, Resources]) -> None:
    port, _ = server
    status, data = _request(
        port, "/ask", {"question": "x", "opts": {"kind": "bogus"}}, 5.0
    )
    assert status == 400 and data["code"] == 2
    status, data = _request(port, "/ask", {"question": "", "opts": {}}, 5.0)
    assert status == 400 and data["code"] == 2
    status, data = _request(port, "/ask", {"question": "x", "opts": {"foo": 1}}, 5.0)
    assert status == 400 and "foo" in data["error"]
    status, data = _request(port, "/nope", {}, 5.0)
    assert status == 404


def test_sync_endpoint_runs_runner_and_records_last_sync(
    server: tuple[int, Resources],
) -> None:
    port, _ = server
    assert health(port)["last_sync"] is None  # type: ignore[index]
    report = sync_remote(port)
    assert report["changed"] is False
    h = health(port)
    assert h is not None and h["last_sync"]["changed"] is False
    assert h["last_sync"]["error"] is None and h["sync_running"] is False


def test_shutdown_stops_server(clean_db: str) -> None:
    res = Resources(
        dsn=clean_db,
        embedder_for=lambda _n: FakeEmbedder(),  # type: ignore[arg-type,return-value]
        model="fake",
    )
    srv = make_server(0, res)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.1})
    t.start()
    try:
        assert stop_daemon(srv.port) is True
        t.join(timeout=5)
        assert not t.is_alive() and srv.stopping is True
        assert health(srv.port) is None
        assert stop_daemon(srv.port) is False  # 居ないときは False
    finally:
        srv.server_close()
