"""OKF フロントマターの解析。素の OKF v0.2 とくろこ拡張の両方を受ける（D-12）.

くろこ拡張＝ `description` 必須・`type` の閉じた語彙・memory の `metadata:` ネスト・
`updated:`・日付だけの `at`・`verified` の単一/リスト。
どの形式で読んだかを `format` に残す。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from typing import Any

import frontmatter as fm_lib

JST = timezone(timedelta(hours=9))

# くろこ規約の閉じた語彙（dev/recording.md「type は閉じた語彙」表）
KUROKO_TYPES = frozenset(
    {
        "Tech Note",
        "Life Data",
        "Domain Knowledge",
        "Scout Note",
        "Experiment Record",
        "Experiment Backlog",
        "Experiment Records Convention",
        "Charter",
        "Playbook",
        "Decision Log",
        "News Digest",
        "Index",
        "Change Log",
    }
)


class FrontmatterError(Exception):
    """YAML が解析できない。本文は含めない（パスと理由だけ）."""

    def __init__(self, rel_path: str, reason: str) -> None:
        self.rel_path = rel_path
        self.reason = reason
        super().__init__(f"{rel_path}: フロントマター不正 ({reason})")


@dataclass(frozen=True)
class ParsedDoc:
    fm: dict[str, Any]
    body: str
    format: str  # 'okf' | 'kuroko'
    type: str | None
    status: str
    generated_at: datetime | None
    verified_at: datetime | None
    stale_after: date | None


def to_datetime(value: object) -> datetime | None:
    """date / datetime / ISO 文字列を tz 付き datetime に。日付だけは JST 0時."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=JST)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=JST)
    if isinstance(value, str):
        s = value.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(s)
        except ValueError:
            return None
        if parsed.tzinfo is None:
            # 日付だけ（len==10）も時刻なしの datetime もここに来る
            parsed = parsed.replace(tzinfo=JST)
        return parsed.astimezone(UTC) if parsed.tzinfo is not JST else parsed
    return None


def to_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        dt = to_datetime(value)
        return dt.date() if dt else None
    return None


def latest_at(value: object) -> datetime | None:
    """`generated`/`verified` の `at`。リストなら最大（OKF §5: 最新性は max）."""
    if isinstance(value, dict):
        return to_datetime(value.get("at"))
    if isinstance(value, list):
        ats = [to_datetime(v.get("at")) for v in value if isinstance(v, dict)]
        found = [a for a in ats if a is not None]
        return max(found) if found else None
    return None


def parse(text: str, rel_path: str = "?") -> ParsedDoc:
    """本文とフロントマターを分け、形式を判定して ParsedDoc を返す."""
    try:
        post = fm_lib.loads(text)
    except Exception as exc:  # YAML の例外型は複数あるので広く受ける
        raise FrontmatterError(rel_path, type(exc).__name__) from exc

    meta: dict[str, Any] = dict(post.metadata)
    nested = meta.get("metadata")
    if isinstance(nested, dict) and "type" in nested:
        # memory 形式: OKF キーが metadata: 配下に1段下がっている
        src: dict[str, Any] = nested
        fmt = "kuroko"
    else:
        src = meta
        is_kuroko = "description" in meta and meta.get("type") in KUROKO_TYPES
        fmt = "kuroko" if is_kuroko else "okf"

    raw_type = src.get("type")
    doc_type = str(raw_type) if raw_type is not None else None
    raw_status = src.get("status")
    status = str(raw_status) if raw_status else "stable"

    return ParsedDoc(
        fm=meta,
        body=post.content,
        format=fmt,
        type=doc_type,
        status=status,
        generated_at=latest_at(src.get("generated")),
        verified_at=latest_at(src.get("verified")),
        stale_after=to_date(src.get("stale_after")),
    )
