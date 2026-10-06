"""受入検証（2026-10-06）の回収分: ビュー名の count 中継・負の Content-Length・ログの経路名."""

from __future__ import annotations

import socket
import threading
from collections.abc import Iterator

import pytest

from dbr.features import serve as serve_mod
from dbr.features.ask import AskOptions
from dbr.features.count import VIEWS
from dbr.features.ingest import run
from dbr.features.serve import Resources, make_server
from dbr.features.serve.client import ask_remote
from dbr.shared.embed.fake import FakeEmbedder
from tests.integration.conftest import FIXTURES

pytestmark = pytest.mark.db


@pytest.fixture
def server(clean_db: str) -> Iterator[int]:
    run(FIXTURES / "okf-plain", "dev", clean_db, log=lambda _m: None)
    res = Resources(
        dsn=clean_db,
        embedder_for=lambda _n: FakeEmbedder(),  # type: ignore[arg-type,return-value]
        model="fake",
    )
    srv = make_server(0, res)
    t = threading.Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.1})
    t.start()
    try:
        yield srv.port
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=5)


def test_every_view_name_relays_as_count(server: int) -> None:
    # 指摘 1: MCP の count ツールは検査済みのビュー名を質問として渡す。5 つ全部通ること
    for view in sorted(VIEWS):
        out = ask_remote(view, AskOptions(kind="count", model="fake"), port=server)
        assert out["kind"] == "count" and out["view"] == view, (view, out)


def test_negative_content_length_is_rejected(server: int) -> None:
    # 観察: read(-1) で上限検査を回避できた。生ソケットで負値を送る
    req = (
        b"POST /ask HTTP/1.1\r\nHost: 127.0.0.1\r\nContent-Type: application/json\r\n"
        b"Content-Length: -1\r\nConnection: close\r\n\r\n"
    )
    with socket.create_connection(("127.0.0.1", server), timeout=5) as s:
        s.sendall(req)
        s.settimeout(5)
        head = b""
        while b"\r\n\r\n" not in head:
            chunk = s.recv(4096)
            if not chunk:
                break
            head += chunk
    status_line = head.split(b"\r\n", 1)[0]
    assert status_line.startswith(b"HTTP/1.1 400"), status_line


def test_unknown_route_is_logged_as_other(
    server: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    lines: list[str] = []
    monkeypatch.setattr(serve_mod, "_log_line", lines.append)
    from dbr.features.serve.client import _request

    status, _ = _request(server, "/secret%20question%20text", {}, 5.0)
    assert status == 404
    assert any(line == "POST other" for line in lines), lines
    assert not any("secret" in line for line in lines)
