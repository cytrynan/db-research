"""利用ログのユニット: 許可リスト・切り詰め・本文を写さない・書込失敗を握る・集計の数値."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from dbr.features.serve import usage as u

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
OPTS = {
    "kind": "auto",
    "k": 5,
    "mode": "embed_ctx",
    "agg": "rrf_top3",
    "scope": "boost",
}


def _find_out(n_hits: int, *, fallback: bool = False) -> dict[str, object]:
    return {
        "kind": "find",
        "kind_fallback": fallback,
        "reason": "r",
        "mode": "embed_ctx",
        "agg": "rrf_top3",
        "scope": "boost",
        "scope_reason": "references←好き",
        "hits": [
            {
                "doc": f"references/a{i}.md",
                "heading": "見出し" * 100,  # 300 字
                "score": 0.123456,
                "source": "embed",
                "text": "断片本文は写さない",
            }
            for i in range(n_hits)
        ],
    }


def test_client_is_whitelisted() -> None:
    assert u.normalize_client("mcp") == "mcp"
    assert u.normalize_client("cli-local") == "cli-local"
    assert u.normalize_client("evil\nline") == "other"
    assert u.normalize_client(None) == "other"


def test_build_record_truncates_heading_and_never_copies_text() -> None:
    rec = u.build_record(
        client="mcp",
        question="好きな食べ物",
        opts=OPTS,
        status="ok",
        ms=12.34,
        out=_find_out(2, fallback=True),
        now=NOW,
    )
    assert rec["ts"] == "2026-10-13T12:00:00+00:00"
    assert rec["client"] == "mcp" and rec["status"] == "ok" and rec["ms"] == 12.3
    assert rec["kind"] == "find" and rec["kind_fallback"] is True
    assert rec["n_hits"] == 2 and len(rec["hits"]) == 2
    assert len(rec["hits"][0]["heading"]) == u.HEADING_MAX
    assert rec["hits"][0]["score"] == 0.1235
    assert "text" not in json.dumps(rec, ensure_ascii=False)
    assert rec["scope_reason"] == "references←好き"


def test_build_record_counts_other_kinds_and_errors() -> None:
    c = u.build_record(
        client="cli",
        question="何件？",
        opts={"kind": "count"},
        status="ok",
        ms=1,
        out={"kind": "count", "view": "v_by_bundle", "rows": [{}, {}, {}]},
    )
    assert c["view"] == "v_by_bundle" and c["n_rows"] == 3 and "hits" not in c
    a = u.build_record(
        client="cli",
        question="当時は？",
        opts={"kind": "asof", "at": "2026-09"},
        status="ok",
        ms=1,
        out={"kind": "asof", "at": "2026-09-30", "facts": [{}]},
    )
    assert a["n_facts"] == 1 and a["at"] == "2026-09-30"  # 回答側の解決値が勝つ
    e = u.build_record(
        client="other",
        question="x",
        opts={},
        status="error",
        ms=5,
        code=2,
        error="e" * 500,
    )
    assert e["code"] == 2 and len(e["error"]) == u.ERROR_MAX and "n_hits" not in e
    with pytest.raises(ValueError):
        u.build_record(client="cli", question="x", opts={}, status="bogus", ms=0)


def test_record_appends_json_line_and_swallows_os_error(tmp_path: Path) -> None:
    path = tmp_path / "deep" / "usage.jsonl"
    u.record({"a": 1}, path)
    u.record({"b": "日本語"}, path)
    lines = path.read_text(encoding="utf-8").splitlines()
    assert [json.loads(x) for x in lines] == [{"a": 1}, {"b": "日本語"}]
    # 書けない先（ディレクトリをファイル名にする）でも例外にしない＝要求を止めない
    u.record({"c": 1}, tmp_path)
    assert u.iter_records(path) == [{"a": 1}, {"b": "日本語"}]


def test_iter_records_skips_broken_lines_and_missing_file(tmp_path: Path) -> None:
    path = tmp_path / "usage.jsonl"
    path.write_text('{"ok": 1}\nnot json\n[1,2]\n\n{"ok": 2}\n', encoding="utf-8")
    assert u.iter_records(path) == [{"ok": 1}, {"ok": 2}]
    assert u.iter_records(tmp_path / "none.jsonl") == []


def _records() -> list[dict[str, object]]:
    def at(day: int, hour: int) -> datetime:
        return datetime(2026, 10, day, hour, tzinfo=UTC)

    return [
        u.build_record(
            client="mcp",
            question="q1",
            opts=OPTS,
            status="ok",
            ms=100,
            out=_find_out(3),
            now=at(12, 9),
        ),
        u.build_record(
            client="mcp",
            question="q2 ゼロ件",
            opts=OPTS,
            status="ok",
            ms=300,
            out=_find_out(0, fallback=True),
            now=at(12, 10),
        ),
        u.build_record(
            client="cli",
            question="q3",
            opts=OPTS,
            status="ok",
            ms=200,
            out=_find_out(1),
            now=at(13, 8),
        ),
        u.build_record(
            client="cli",
            question="q4",
            opts={"kind": "find", "k": 5},
            status="ok",
            ms=1000,
            out=_find_out(1),
            now=at(13, 9),
        ),
        u.build_record(
            client="mcp",
            question="q5",
            opts=OPTS,
            status="error",
            ms=5000,
            code=1,
            error="ConnectionTimeout: connection timeout expired",
            now=at(13, 10),
        ),
        u.build_record(
            client="mcp",
            question="q6",
            opts=OPTS,
            status="daemon_unavailable",
            ms=90000,
            error="常駐を起こせません",
            now=at(13, 11),
        ),
        u.build_record(
            client="cli",
            question="old",
            opts=OPTS,
            status="ok",
            ms=1,
            out=_find_out(0),
            now=at(1, 0),
        ),  # 12 日前＝対象外
    ]


def test_summarize_matches_hand_computation() -> None:
    s = u.summarize(_records(), days=7, now=NOW)
    assert s["total"] == 6  # old は除外
    assert s["by_client_status"] == {
        "mcp": {"ok": 2, "error": 1, "daemon_unavailable": 1},
        "cli": {"ok": 2},
    }
    # auto の成功要求は q1 q2 q3（q4 は kind=find 明示）→ 倒れたのは q2 だけ
    assert s["auto_n"] == 3 and s["fallback_n"] == 1
    assert s["fallback_rate"] == pytest.approx(1 / 3)
    # 成功 4 件の ms = 100, 200, 300, 1000 → p50 は 2 位（200）・p90 は ceil(3.6)=4 位（1000）
    assert s["ms_p50"] == 200 and s["ms_p90"] == 1000
    assert [z["question"] for z in s["zero_hit_questions"]] == ["q2 ゼロ件"]
    assert (
        s["errors"]["1"]["n"] == 1
        and "ConnectionTimeout" in s["errors"]["1"]["example"]
    )
    assert s["errors"]["daemon_unavailable"]["n"] == 1
    text = u.format_summary(s)
    assert "mcp: daemon_unavailable 1 / error 1 / ok 2" in text
    assert "33%（1/3）" in text and "p50 200 ms / p90 1000 ms" in text
    assert "q2 ゼロ件" in text and "ConnectionTimeout" in text


def test_summarize_handles_empty_and_rejects_bad_days() -> None:
    s = u.summarize([], days=7, now=NOW)
    assert s["total"] == 0 and s["fallback_rate"] is None and s["ms_p50"] is None
    assert "なし" in u.format_summary(s)
    with pytest.raises(ValueError):
        u.summarize([], days=0)


def test_log_request_never_raises_and_caps_hits(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """組み立て・書込の例外は握る（J2・必須 4）。hits は 50 件まで（J3）."""
    path = tmp_path / "usage.jsonl"
    monkeypatch.setattr(u, "USAGE_PATH", path)
    # score=None → float() が TypeError。要求を失敗させない
    u.log_request(
        client="cli",
        question="x",
        opts=OPTS,
        status="ok",
        ms=1,
        out={"kind": "find", "hits": [{"doc": "d", "heading": "h", "score": None}]},
    )
    # 孤立サロゲートは UTF-8 に書けない（UnicodeEncodeError は OSError ではない）
    u.log_request(client="cli", question="\ud800", opts=OPTS, status="ok", ms=1, out={})
    # 正常な行は書ける
    u.log_request(
        client="cli", question="ok", opts=OPTS, status="ok", ms=1, out=_find_out(80)
    )
    recs = u.iter_records(path)
    assert [r["question"] for r in recs] == ["ok"]
    assert recs[0]["n_hits"] == 80 and len(recs[0]["hits"]) == u.HITS_MAX


def test_summarize_tolerates_broken_counts_and_reports_latest_error() -> None:
    rows = [
        u.build_record(
            client="cli",
            question="a",
            opts=OPTS,
            status="ok",
            ms=1,
            out=_find_out(0),
            now=NOW,
        ),
        u.build_record(
            client="cli",
            question="e1",
            opts=OPTS,
            status="error",
            ms=1,
            code=1,
            error="first",
            now=datetime(2026, 10, 12, tzinfo=UTC),
        ),
        u.build_record(
            client="cli",
            question="e2",
            opts=OPTS,
            status="error",
            ms=1,
            code=1,
            error="latest",
            now=datetime(2026, 10, 13, tzinfo=UTC),
        ),
    ]
    rows[0]["n_hits"] = "broken"  # 壊れた行は 0 件扱いにせず飛ばす
    s = u.summarize(rows, days=7, now=NOW)
    assert s["zero_hit_questions"] == []
    assert s["errors"]["1"] == {
        "n": 2,
        "last": "2026-10-13T00:00:00+00:00",
        "example": "latest",
    }
