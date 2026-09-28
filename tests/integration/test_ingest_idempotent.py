from datetime import UTC, datetime
from pathlib import Path

import pytest

from dbr.features.ingest import run
from dbr.shared.db import connect
from tests.integration.conftest import FIXTURES, count_rows

pytestmark = pytest.mark.db


def _formats(dsn: str) -> dict[str, str]:
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        cur.execute("SELECT rel_path, format FROM document")
        return {str(r["rel_path"]): str(r["format"]) for r in cur.fetchall()}


def test_three_fixtures_ingest_and_format_column(clean_db: str) -> None:
    r1 = run(FIXTURES / "okf-plain", "dev", clean_db, log=lambda _m: None)
    r2 = run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    assert (r1.inserted, r1.failed, r1.rejected) == (3, 0, 0)
    assert (r2.inserted, r2.failed, r2.rejected) == (4, 0, 0)
    assert any(
        "type 無し" in w for w in r1.warnings
    )  # notype.md は WARN・failed に数えない

    fmts = _formats(clean_db)
    assert fmts["alpha.md"] == "okf"
    assert fmts["notype.md"] == "okf"
    assert fmts["memory-note.md"] == "kuroko"
    assert fmts["dateonly.md"] == "kuroko"

    conn = connect(clean_db)
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT type, generated_at, verified_at, stale_after "
            "FROM document WHERE rel_path=%(r)s",
            {"r": "memory-note.md"},
        )
        row = cur.fetchone()
        assert row is not None
        assert row["type"] == "feedback"
        gen = row["generated_at"]
        assert isinstance(gen, datetime)
        assert gen.astimezone(UTC) == datetime(
            2026, 7, 18, 15, 21, 46, 156000, tzinfo=UTC
        )
        assert row["verified_at"] is not None
        cur.execute("SELECT type FROM document WHERE rel_path='notype.md'")
        row = cur.fetchone()
        assert row is not None and row["type"] is None
        cur.execute(
            "SELECT fm->'updated' AS u FROM document WHERE rel_path='updated.md'"
        )
        row = cur.fetchone()
        assert row is not None and row["u"] is not None  # 規約外キーは fm に残る


def test_second_run_does_not_add_rows(clean_db: str) -> None:
    run(FIXTURES / "okf-plain", "dev", clean_db, log=lambda _m: None)
    run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    before = (count_rows(clean_db, "document"), count_rows(clean_db, "chunk"))
    assert before[0] == 7 and before[1] > 0

    r1 = run(FIXTURES / "okf-plain", "dev", clean_db, log=lambda _m: None)
    r2 = run(FIXTURES / "kuroko", "memory", clean_db, log=lambda _m: None)
    after = (count_rows(clean_db, "document"), count_rows(clean_db, "chunk"))
    assert after == before  # before/after の差分ゼロ
    assert (r1.inserted, r1.updated, r1.skipped) == (0, 0, 3)
    assert (r2.inserted, r2.updated, r2.skipped) == (0, 0, 4)


def test_changed_file_is_updated_not_duplicated(clean_db: str, tmp_path: Path) -> None:
    src = tmp_path / "doc.md"
    src.write_text("---\ntype: Note\n---\n# v1\n\nold\n", encoding="utf-8")
    run(tmp_path, "dev", clean_db, log=lambda _m: None)
    src.write_text(
        "---\ntype: Note\n---\n# v2\n\nnew\n\n## more\n\nx\n", encoding="utf-8"
    )
    r = run(tmp_path, "dev", clean_db, log=lambda _m: None)
    assert (r.inserted, r.updated, r.skipped) == (0, 1, 0)
    assert count_rows(clean_db, "document") == 1
    assert count_rows(clean_db, "chunk") == 2  # 旧断片は消え、新断片だけ
