"""assert_loopback の故障注入（通すもの3・拒否するもの3）."""

import pytest

from dbr.shared.db.loopback import LoopbackViolation, assert_loopback, host_of


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://dbr:dbr@localhost:5432/dbr",
        "postgresql://dbr:dbr@127.0.0.1:5432/dbr",
        "postgresql://dbr:dbr@[::1]:5432/dbr",
        "host=LOCALHOST dbname=dbr user=dbr",
    ],
)
def test_assert_loopback_local_passes(dsn: str) -> None:
    assert_loopback(dsn)


@pytest.mark.parametrize(
    "dsn,host",
    [
        ("postgresql://dbr:dbr@example.com:5432/dbr", "example.com"),
        ("postgresql://dbr:dbr@db.supabase.co:5432/dbr", "db.supabase.co"),
        ("postgresql://dbr:dbr@10.0.0.5:5432/dbr", "10.0.0.5"),
    ],
)
def test_assert_loopback_remote_rejected(dsn: str, host: str) -> None:
    with pytest.raises(LoopbackViolation) as ei:
        assert_loopback(dsn)
    assert ei.value.host == host


def test_assert_loopback_no_host_rejected() -> None:
    assert host_of("dbname=dbr user=dbr") is None
    with pytest.raises(LoopbackViolation):
        assert_loopback("dbname=dbr user=dbr")
