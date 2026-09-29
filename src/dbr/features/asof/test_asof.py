from datetime import datetime

from dbr.features.asof import parse_at
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
    assert parse_at("2026-08-11 以前は") == datetime(
        2026, 8, 10, 23, 59, 59, tzinfo=JST
    )
    assert parse_at("2026-08 時点") == datetime(2026, 8, 31, 23, 59, 59, tzinfo=JST)


def test_parse_at_none_and_invalid() -> None:
    assert parse_at("いつ決めた？") is None
    assert parse_at("2026-13 時点") is None
