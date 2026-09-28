"""count のユニット（DB 不要）: 未定義名・変な名前・定義済み名."""

import pytest

from dbr.features.count import VIEWS, UnknownAggregate, sql_for


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
