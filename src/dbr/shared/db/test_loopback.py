"""assert_loopback / effective_conninfo の故障注入.

2026-09-29 受入検証の反例（hostaddr / PGHOSTADDR / service で検査を回避）を固定する。
"""

import pytest
from psycopg.conninfo import conninfo_to_dict

from dbr.shared.db.loopback import (
    LoopbackViolation,
    assert_loopback,
    effective_conninfo,
    host_of,
)


@pytest.mark.parametrize(
    "dsn",
    [
        "postgresql://dbr:dbr@localhost:5432/dbr",
        "postgresql://dbr:dbr@127.0.0.1:5432/dbr",
        "postgresql://dbr:dbr@[::1]:5432/dbr",
        "host=LOCALHOST dbname=dbr user=dbr",
        "host=127.0.0.1 hostaddr=127.0.0.1 dbname=dbr",
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
        ("postgresql://dbr:dbr@127.0.0.1:5432/dbr?host=example.com", "example.com"),
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


@pytest.mark.parametrize(
    "dsn",
    [
        "host=localhost hostaddr=192.0.2.1 dbname=dbr",
        "postgresql://dbr:dbr@127.0.0.1:5432/dbr?hostaddr=192.0.2.1",
    ],
)
def test_hostaddr_bypass_rejected(dsn: str) -> None:
    with pytest.raises(LoopbackViolation) as ei:
        assert_loopback(dsn)
    assert ei.value.reason == "hostaddr"
    assert ei.value.host == "192.0.2.1"


def test_service_rejected() -> None:
    with pytest.raises(LoopbackViolation) as ei:
        assert_loopback("service=remote-db host=localhost")
    assert ei.value.reason == "service"


def test_effective_conninfo_pins_hostaddr_and_ignores_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PGHOSTADDR", "192.0.2.1")
    info = conninfo_to_dict(
        effective_conninfo("postgresql://dbr:dbr@localhost:5432/dbr")
    )
    assert info["host"] == "127.0.0.1"
    assert info["hostaddr"] == "127.0.0.1"  # 明示されるので PGHOSTADDR は効かない
    assert str(info["connect_timeout"]) == "5"


def test_effective_conninfo_ipv6_keeps_v6() -> None:
    info = conninfo_to_dict(effective_conninfo("postgresql://dbr:dbr@[::1]:5432/dbr"))
    assert info["host"] == "::1"
    assert info["hostaddr"] == "::1"
