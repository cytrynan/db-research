"""全テスト共通: 利用ログと DB フラグを実運用の ~/.dbr に書かない（tmp へ退避）.

serve.log の退避は serve/conftest.py と tests/integration/conftest.py にある。利用ログは
CLI の単発経路（cli.py）や MCP 入口（mcp_server/）からも書くので、rootdir の conftest で
testpaths（src・tests）の全部に効かせる。
"""

from __future__ import annotations

from pathlib import Path

import pytest

import dbr.features.serve as serve_mod
import dbr.features.serve.usage as usage_mod


@pytest.fixture(autouse=True)
def _usage_and_flag_to_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(usage_mod, "USAGE_PATH", tmp_path / ".dbr" / "usage.jsonl")
    monkeypatch.setattr(
        serve_mod, "FLAG_PATH", tmp_path / ".dbr" / "DB-UNREACHABLE.flag"
    )
