"""`dbr usage` の配線テスト（DB 不要）: 実行時刻を基準に作った行で集計の数値を照合する.

固定日付の fixture は「テストを書いた日の姿」を仕様に焼き込み、日が経つだけで落ちる
（CLAUDE.md「実データのスナップショット」の原則）。ここでは now からの相対で行を作る。
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from typer.testing import CliRunner

from dbr.cli import app
from dbr.features.serve.usage import build_record, record

runner = CliRunner()
OPTS = {"kind": "auto", "k": 5}


def _hits(n: int) -> dict[str, object]:
    return {
        "kind": "find",
        "kind_fallback": n == 0,
        "hits": [{"doc": f"d{i}", "heading": "h", "score": 0.5} for i in range(n)],
    }


@pytest.fixture
def log_path(tmp_path: Path) -> Path:
    now = datetime.now(UTC)
    path = tmp_path / "usage.jsonl"
    rows = [
        ("mcp", "ok", 120.0, _hits(2), None, None, now - timedelta(hours=1)),
        ("mcp", "ok", 480.0, _hits(0), None, None, now - timedelta(hours=2)),
        ("cli", "ok", 240.0, _hits(1), None, None, now - timedelta(days=1)),
        ("cli-local", "ok", 9000.0, _hits(1), None, None, now - timedelta(days=2)),
        (
            "mcp",
            "error",
            5000.0,
            None,
            1,
            "ConnectionTimeout: x",
            now - timedelta(days=3),
        ),
        (
            "mcp",
            "daemon_unavailable",
            90000.0,
            None,
            None,
            "起こせません",
            now - timedelta(days=4),
        ),
        ("cli", "ok", 1.0, _hits(0), None, None, now - timedelta(days=30)),  # 対象外
    ]
    for client, status, ms, out, code, err, ts in rows:
        record(
            build_record(
                client=client,
                question=f"q-{client}-{status}",
                opts=OPTS,
                status=status,
                ms=ms,
                out=out,
                code=code,
                error=err,
                now=ts,
            ),
            path,
        )
    return path


def test_usage_json_matches_hand_computation(log_path: Path) -> None:
    result = runner.invoke(app, ["usage", "--path", str(log_path), "--json"])
    assert result.exit_code == 0, result.output
    s = json.loads(result.output)
    assert s["total"] == 6
    assert s["by_client_status"] == {
        "mcp": {"ok": 2, "error": 1, "daemon_unavailable": 1},
        "cli": {"ok": 1},
        "cli-local": {"ok": 1},
    }
    assert s["fallback_n"] == 1 and s["auto_n"] == 4
    # 成功 4 件の ms = 120, 240, 480, 9000 → p50 は 2 位・p90 は ceil(3.6)=4 位
    assert s["ms_p50"] == 240.0 and s["ms_p90"] == 9000.0
    assert [z["question"] for z in s["zero_hit_questions"]] == ["q-mcp-ok"]
    assert set(s["errors"]) == {"1", "daemon_unavailable"}


def test_usage_text_and_days_filter(log_path: Path) -> None:
    result = runner.invoke(app, ["usage", "--path", str(log_path), "--days", "2"])
    assert result.exit_code == 0, result.output
    assert "直近 2 日" in result.output and ": 3 件" in result.output
    assert "mcp: ok 2" in result.output and "cli: ok 1" in result.output
    assert "q-mcp-ok" in result.output  # 0 件だった質問


def test_usage_missing_file_and_bad_days(tmp_path: Path) -> None:
    result = runner.invoke(app, ["usage", "--path", str(tmp_path / "none.jsonl")])
    assert result.exit_code == 0 and ": 0 件" in result.output
    result = runner.invoke(app, ["usage", "--path", str(tmp_path / "x"), "--days", "0"])
    assert result.exit_code == 2


def test_ask_local_records_non_ask_errors(tmp_path: Path) -> None:
    """単発経路で DB に届かない時も 1 行残して投げ直す（必須 1）。count は埋め込みモデル不要."""
    import psycopg

    from dbr import cli
    from dbr.features.ask import AskOptions
    from dbr.features.serve.usage import iter_records

    with pytest.raises(psycopg.OperationalError):
        cli._ask_local(
            "未確認の記録は何件？",
            AskOptions(kind="count"),
            "postgresql://dbr:dbr@127.0.0.1:1/dbr?connect_timeout=2",
        )
    recs = iter_records()
    assert len(recs) == 1
    r = recs[0]
    assert r["client"] == "cli-local" and r["status"] == "error" and r["code"] == 1
    assert "OperationalError" in r["error"] or "Timeout" in r["error"]
    assert r["question"] == "未確認の記録は何件？"
