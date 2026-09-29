from datetime import datetime

from dbr.features.asof import parse_at, parse_at_option
from dbr.features.ingest.frontmatter import JST


def test_parse_at_day_and_month() -> None:
    assert parse_at("2026-08-15 時点では") == datetime(
        2026, 8, 15, 23, 59, 59, tzinfo=JST
    )
    assert parse_at("2026-09 時点で動いていた？") == datetime(
        2026, 9, 30, 23, 59, 59, tzinfo=JST
    )
    assert parse_at("2024-02 の状況") == datetime(2024, 2, 29, 23, 59, 59, tzinfo=JST)


def test_parse_at_before_means_instant_before_period() -> None:
    assert parse_at("2026-08 より前の時点では") == datetime(
        2026, 7, 31, 23, 59, 59, tzinfo=JST
    )
    assert parse_at("2026-08-11 より以前は") == datetime(
        2026, 8, 10, 23, 59, 59, tzinfo=JST
    )
    assert parse_at("2026-08 時点") == datetime(2026, 8, 31, 23, 59, 59, tzinfo=JST)


def test_parse_at_izen_and_madeni_include_the_day() -> None:
    # 「以前」「までに」は基準日を含む（受入検証 D2）。直前扱いは「より前」だけ
    end_0811 = datetime(2026, 8, 11, 23, 59, 59, tzinfo=JST)
    assert parse_at("2026-08-11 以前は") == end_0811
    assert parse_at("2026-08-11 までに決めたことは") == end_0811
    assert parse_at("2026-08 以前") == datetime(2026, 8, 31, 23, 59, 59, tzinfo=JST)


def test_parse_at_option_requires_full_match() -> None:
    assert parse_at_option("2026-08-15") == datetime(
        2026, 8, 15, 23, 59, 59, tzinfo=JST
    )
    assert parse_at_option("2026-08") == datetime(2026, 8, 31, 23, 59, 59, tzinfo=JST)
    assert parse_at_option(" 2026-08 ") is not None  # 前後の空白だけは許す
    for bad in ("2026-08-1", "x2026-08-15y", "2026-08-15 時点", "2026-13", ""):
        assert parse_at_option(bad) is None, bad  # 受入検証 D1


def test_parse_at_none_and_invalid() -> None:
    assert parse_at("いつ決めた？") is None
    assert parse_at("2026-13 時点") is None
