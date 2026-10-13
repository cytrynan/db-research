"""利用ログ（1 要求 = 1 行の JSON・`~/.dbr/usage.jsonl`）と、その集計.

serve.log（経路名・件数・時刻だけ）と違い、**改善に使うために質問文と上位ヒットを書く**
（K 指示 2026-10-13）。断片本文は書かない。置き場は正本 `references/` と同じローカル境界
（`~/.dbr/`・リポ外）。torch・psycopg は import しない（client・MCP からも呼ぶ）。
"""

from __future__ import annotations

import contextlib
import json
import math
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

USAGE_PATH = Path.home() / ".dbr" / "usage.jsonl"
# 呼び出し元は許可リストに閉じる（ペイロードの任意文字列をログに流し込ませない。KNOWN_ROUTES と同じ流儀）
CLIENTS = frozenset({"mcp", "cli", "cli-local", "bench", "other"})
STATUSES = frozenset({"ok", "error", "daemon_unavailable"})
HEADING_MAX = 120
HITS_MAX = 50  # J3: 記録する上位の上限（k の上限と同じ。CLI は k を制限しないため）
ERROR_MAX = 200
ZERO_HIT_RECENT = 10


def normalize_client(value: object) -> str:
    return value if isinstance(value, str) and value in CLIENTS else "other"


def build_record(
    *,
    client: str,
    question: str,
    opts: Mapping[str, Any],
    status: str,
    ms: float,
    out: Mapping[str, Any] | None = None,
    code: int | None = None,
    error: str | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """1 行ぶんの dict を作る。`out` は answer() の戻り（成功時）。本文（text）は決して写さない."""
    if status not in STATUSES:
        raise ValueError(f"status は {sorted(STATUSES)}")
    o = out or {}
    rec: dict[str, Any] = {
        "ts": (now or datetime.now(UTC)).isoformat(timespec="seconds"),
        "client": normalize_client(client),
        "question": question,
        "kind_requested": opts.get("kind", "auto"),
        "kind": o.get("kind"),
        "kind_fallback": bool(o.get("kind_fallback", False)),
        "reason": o.get("reason"),
        "k": opts.get("k"),
        "at": o.get("at", opts.get("at")),
        "mode": o.get("mode", opts.get("mode")),
        "agg": o.get("agg", opts.get("agg")),
        "scope": o.get("scope", opts.get("scope")),
        "scope_reason": o.get("scope_reason"),
        "status": status,
        "code": code,
        "error": error[:ERROR_MAX] if error else None,
        "ms": round(float(ms), 1),
    }
    if "hits" in o:
        hits = list(o["hits"])
        rec["n_hits"] = len(hits)
        rec["hits"] = [
            {
                "doc": h.get("doc"),
                "heading": str(h.get("heading") or "")[:HEADING_MAX],
                "score": round(float(h.get("score", 0.0)), 4),
                "source": h.get("source"),
            }
            for h in hits[:HITS_MAX]
        ]
    if "rows" in o:
        rec["view"] = o.get("view")
        rec["n_rows"] = len(o["rows"])
    if "facts" in o:
        rec["n_facts"] = len(o["facts"])
    if "summaries" in o:
        rec["n_summaries"] = len(o["summaries"])
    return rec


def record(rec: Mapping[str, Any], path: Path | None = None) -> None:
    """1 行追記する。失敗しても呼び手を止めない（ログは補助。serve の _log_line と同じ）.

    OSError だけでなく全例外を握る（孤立サロゲートの UnicodeEncodeError 等。受入検証 2026-10-13 必須 4）。
    """
    target = path or USAGE_PATH
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False, default=str) + "\n")
    except Exception:  # ログの失敗で要求を失敗させない（J2）
        pass


def log_request(**kw: Any) -> None:
    """build_record → record を 1 つにまとめ、組み立ての例外も握る（J2。呼び手はこれだけを使う）."""
    with contextlib.suppress(Exception):  # 同上
        record(build_record(**kw))


def iter_records(path: Path | None = None) -> list[dict[str, Any]]:
    """読めた行だけ返す（壊れた行・非オブジェクトは飛ばす）。無ければ空."""
    target = path or USAGE_PATH
    try:
        lines = target.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    out: list[dict[str, Any]] = []
    for line in lines:
        if not line.strip():
            continue
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(data, dict):
            out.append(data)
    return out


def _parse_ts(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)


def _percentile(values: list[float], p: float) -> float | None:
    """最近接順位法（n が小さくても定義どおり）。空なら None."""
    if not values:
        return None
    s = sorted(values)
    rank = max(1, math.ceil(p * len(s)))
    return s[rank - 1]


def _is_zero_hit(r: Mapping[str, Any]) -> bool:
    for key in ("n_hits", "n_rows", "n_facts", "n_summaries"):
        if key in r:
            try:
                return int(r[key] or 0) == 0
            except (TypeError, ValueError):  # 壊れた行は iter_records と同じく飛ばす
                return False
    return False


def summarize(
    records: Iterable[Mapping[str, Any]],
    *,
    days: int = 7,
    now: datetime | None = None,
) -> dict[str, Any]:
    """直近 days 日の利用を「改善に使える形」に畳む.

    - by_client_status: 誰がどれだけ呼び、どれだけ失敗したか
    - fallback_rate: kind=auto の成功要求のうち、語彙に当たらず探し物へ倒れた割合（判定器の語彙の穴）
    - ms_p50 / ms_p90: 成功要求の応答時間
    - zero_hit_questions: 返すものが 0 件だった質問（直近 ZERO_HIT_RECENT 件）＝記録の穴か検索の穴
    - errors: code 別の件数・最後の時刻・文言の例
    """
    if days < 1:
        raise ValueError("days は 1 以上")
    now_dt = now or datetime.now(UTC)
    since = now_dt - timedelta(days=days)
    rows = [r for r in records if (ts := _parse_ts(r.get("ts"))) and ts >= since]
    rows.sort(key=lambda r: str(r.get("ts")))

    by: dict[str, dict[str, int]] = {}
    for r in rows:
        c = normalize_client(r.get("client"))
        s = str(r.get("status") or "other")
        by.setdefault(c, {})
        by[c][s] = by[c].get(s, 0) + 1

    ok = [r for r in rows if r.get("status") == "ok"]
    auto = [r for r in ok if r.get("kind_requested", "auto") == "auto"]
    fallback = sum(1 for r in auto if r.get("kind_fallback"))
    ms = [float(r["ms"]) for r in ok if isinstance(r.get("ms"), int | float)]

    zero = [r for r in ok if _is_zero_hit(r)]
    errors: dict[str, dict[str, Any]] = {}
    for r in rows:
        if r.get("status") == "ok":
            continue
        key = str(r.get("code") if r.get("code") is not None else r.get("status"))
        e = errors.setdefault(key, {"n": 0, "last": None, "example": None})
        e["n"] += 1
        e["last"] = r.get("ts")
        if r.get("error"):  # 表示で隣り合う last と同じ＝最新の文言
            e["example"] = str(r["error"])[:ERROR_MAX]

    return {
        "days": days,
        "since": since.isoformat(timespec="seconds"),
        "total": len(rows),
        "by_client_status": by,
        "fallback_rate": (fallback / len(auto)) if auto else None,
        "fallback_n": fallback,
        "auto_n": len(auto),
        "ms_p50": _percentile(ms, 0.5),
        "ms_p90": _percentile(ms, 0.9),
        "zero_hit_questions": [
            {
                "ts": r.get("ts"),
                "client": r.get("client"),
                "question": r.get("question"),
            }
            for r in zero[-ZERO_HIT_RECENT:]
        ],
        "errors": errors,
    }


def format_summary(s: Mapping[str, Any]) -> str:
    lines = [f"直近 {s['days']} 日（{s['since']} 以降）: {s['total']} 件"]
    for client, statuses in sorted(s["by_client_status"].items()):
        parts = " / ".join(f"{k} {v}" for k, v in sorted(statuses.items()))
        lines.append(f"  {client}: {parts}")
    fr = s["fallback_rate"]
    lines.append(
        "フォールバック率（kind=auto の成功要求のうち探し物へ倒れた）: "
        + (f"{fr:.0%}（{s['fallback_n']}/{s['auto_n']}）" if fr is not None else "—")
    )
    p50, p90 = s["ms_p50"], s["ms_p90"]
    lines.append(
        "応答時間（成功）: "
        + (f"p50 {p50:.0f} ms / p90 {p90:.0f} ms" if p50 is not None else "—")
    )
    zero = s["zero_hit_questions"]
    lines.append(f"0 件だった質問（直近 {len(zero)}）:")
    lines.extend(f"  {z['ts']} [{z['client']}] {z['question']}" for z in zero)
    if not zero:
        lines.append("  なし")
    lines.append("エラー（code 別）:")
    for code, e in sorted(s["errors"].items()):
        ex = f" 例: {e['example']}" if e.get("example") else ""
        lines.append(f"  {code}: {e['n']} 件（最後 {e['last']}）{ex}")
    if not s["errors"]:
        lines.append("  なし")
    return "\n".join(lines)


__all__ = [
    "CLIENTS",
    "HEADING_MAX",
    "USAGE_PATH",
    "build_record",
    "format_summary",
    "iter_records",
    "log_request",
    "normalize_client",
    "record",
    "summarize",
]
