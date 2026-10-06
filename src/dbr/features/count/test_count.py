"""count のユニット（DB 不要）: 未定義名・変な名前・定義済み名."""

import pytest

from dbr.features.count import VIEWS, UnknownAggregate, guess_view, sql_for


@pytest.mark.parametrize(
    ("question", "view"),
    [
        ("K が確認済み（verified）の記録は references に何件ある？", "v_verified"),
        ("未確認の記録は何件？", "v_unverified"),
        ("how many unverified docs", "v_unverified"),  # unverified は verified より先
        ("期限切れの記録はいくつ？", "v_stale"),
        ("type が Life Data のファイルは何件？", "v_by_type"),
        ("references のファイルは全部で何件？", "v_by_bundle"),
        ("今日の天気は？", None),
        # ビュー名そのもの（MCP の count ツール経由）。受入検証 2026-10-06 で v_by_bundle だけ None だった
        ("v_by_bundle", "v_by_bundle"),
        ("v_by_type", "v_by_type"),
        ("v_unverified", "v_unverified"),
        ("v_verified", "v_verified"),
        ("v_stale", "v_stale"),
        (" V_BY_BUNDLE ", "v_by_bundle"),  # 前後空白・大文字も同じ
        ("v_nope", None),
    ],
)
def test_guess_view(question: str, view: str | None) -> None:
    assert guess_view(question) == view


def test_sql_for_known_view() -> None:
    assert sql_for("v_by_bundle") == "SELECT * FROM v_by_bundle"


@pytest.mark.parametrize(
    "name",
    [
        "nope",
        "",
        "__proto__",
        "constructor",
        "v_by_bundle; DROP TABLE document",
        " v_by_bundle",
    ],
)
def test_sql_for_unknown_raises_with_known_list(name: str) -> None:
    with pytest.raises(UnknownAggregate) as ei:
        sql_for(name)
    assert ei.value.known == sorted(VIEWS)


def test_views_is_read_only() -> None:
    with pytest.raises(TypeError):
        VIEWS["x"] = "SELECT 1"  # type: ignore[index]
