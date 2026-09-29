import pytest

from dbr.shared.db import connect
from dbr.shared.db.migrate import migrate
from tests.integration.conftest import MIGRATIONS

pytestmark = pytest.mark.db


def test_migrate_second_run_is_noop(dsn: str) -> None:
    conn = connect(dsn)
    with conn:
        assert migrate(conn, MIGRATIONS) == []  # session fixture で適用済み
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT count(*) AS n FROM schema_migrations")
        row = cur.fetchone()
        assert row is not None and int(str(row["n"])) == len(
            list(MIGRATIONS.glob("*.sql"))
        )
        cur.execute("SELECT count(*) AS n FROM pg_views WHERE viewname LIKE 'v\\_%'")
        row = cur.fetchone()
        # 0004 の 4 本 + 0011 v_verified
        assert row is not None and int(str(row["n"])) == 5
