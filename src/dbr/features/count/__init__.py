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


__all__ = ["VIEWS", "UnknownAggregate", "ask_view", "sql_for"]
