"""常駐の利用ログ（dbr_test・fake 埋め込み）: 成功・AskError の両方が 1 行ずつ残り、本文は写さない."""

from __future__ import annotations

import json

import pytest

from dbr.features.ask import AskOptions
from dbr.features.serve import Resources
from dbr.features.serve.client import _request, ask_remote
from dbr.features.serve.usage import iter_records
from tests.integration.test_serve import FALLBACK_Q, server  # noqa: F401 - fixture

pytestmark = pytest.mark.db


def test_ok_and_error_requests_each_leave_one_line(
    server: tuple[int, Resources],  # noqa: F811 - fixture
) -> None:
    port, _ = server
    out = ask_remote(FALLBACK_Q, AskOptions(model="fake"), port=port, client="mcp")
    status, _data = _request(
        port, "/ask", {"question": "x", "opts": {"kind": "bogus"}, "client": "cli"}, 5.0
    )
    assert status == 400
    # client を省くと other、未知の値も other
    ask_remote("未確認の記録は何件？", AskOptions(model="fake"), port=port)
    _request(
        port,
        "/ask",
        {"question": "x", "opts": {"model": "fake"}, "client": "evil\nline"},
        5.0,
    )

    recs = iter_records()
    assert [r["client"] for r in recs] == ["mcp", "cli", "other", "other"]
    ok = recs[0]
    assert ok["status"] == "ok" and ok["kind"] == "find" and ok["kind_fallback"] is True
    assert ok["question"] == FALLBACK_Q and ok["ms"] > 0
    assert ok["n_hits"] == len(out["hits"]) and ok["n_hits"] >= 1
    assert ok["hits"][0]["doc"] == out["hits"][0]["doc"]
    err = recs[1]
    assert err["status"] == "error" and err["code"] == 2 and "kind" in err["error"]
    assert "n_hits" not in err
    cnt = recs[2]
    assert cnt["status"] == "ok" and cnt["kind"] == "count" and cnt["n_rows"] >= 0
    assert "text" not in json.dumps(recs, ensure_ascii=False)
