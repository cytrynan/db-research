"""② 数える（F4 最小）: 名前付きビューを実行するだけ。LLM に SQL を書かせない.

識別子契約: ビュー名はユーザー入力。固定 dict のキー照合だけに使い、
入力を SQL に連結しない・入力をキーとして書き込まない。
"""

from __future__ import annotations

from types import MappingProxyType
from typing import Any

from dbr.shared.db import connect

# ビュー名 → 実行する SQL（migrations/0004_views_count.sql が定義の正本）
VIEWS: MappingProxyType[str, str] = MappingProxyType(
    {
        "v_by_bundle": "SELECT * FROM v_by_bundle",
        "v_by_type": "SELECT * FROM v_by_type",
        "v_unverified": "SELECT * FROM v_unverified",
        "v_stale": "SELECT * FROM v_stale",
    }
)


class UnknownAggregate(Exception):
    """定義されていない集計を求められた。定義済み一覧を持つ."""

    def __init__(self, name: str) -> None:
        self.name = name
        self.known = sorted(VIEWS)
        super().__init__(
            f"この集計は定義されていません: {name!r}。定義済み: {', '.join(self.known)}"
        )


def sql_for(name: str) -> str:
    """名前から SQL を引く。不在は UnknownAggregate（dict のキー照合のみ）."""
    sql = VIEWS.get(name)
    if sql is None:
        raise UnknownAggregate(name)
    return sql


def ask_view(name: str, dsn: str) -> list[dict[str, Any]]:
    sql = sql_for(name)
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute(sql)  # 固定文字列のみ（VIEWS の値）
        return [dict(r) for r in cur.fetchall()]


def guess_view(question: str) -> str | None:
    """② の質問 → ビュー名。語彙の固定対応だけ（LLM に SQL を書かせない）."""
    q = question.lower()
    if "verified" in q or "確認済" in q or "未確認" in q:
        return "v_unverified"
    if "stale" in q or "期限" in q:
        return "v_stale"
    if "type" in q or "種別" in q:
        return "v_by_type"
    if "ファイル" in q or "記録" in q or "件" in q:
        return "v_by_bundle"
    return None


__all__ = ["VIEWS", "UnknownAggregate", "ask_view", "guess_view", "sql_for"]
