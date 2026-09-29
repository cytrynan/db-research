from datetime import datetime

import pytest

from dbr.features.asof import as_of, history
from dbr.features.ingest import run
from dbr.features.ingest.facts import run_facts
from dbr.features.ingest.frontmatter import JST
from dbr.shared.db import connect
from tests.integration.conftest import FIXTURES

pytestmark = pytest.mark.db


def _count(dsn: str, source: str | None = None) -> int:
    conn = connect(dsn)
    with conn, conn.cursor() as cur:
        if source:
            cur.execute(
                "SELECT count(*) AS n FROM fact WHERE valid_source=%(s)s", {"s": source}
            )
        else:
            cur.execute("SELECT count(*) AS n FROM fact")
        row = cur.fetchone()
    assert row is not None
    return int(str(row["n"]))


def test_facts_counts_and_idempotent(clean_db: str) -> None:
    run(FIXTURES / "dated", "references", clean_db, log=lambda _m: None)
    r1 = run_facts("references", clean_db)
    # dated_text 5 = decisions-note 3 ＋ same-day 2（同じ見出し・同じ日付・動詞だけ違う
    # 2 行を 2 件として保持できる＝fact_uniq に md5(value) を含めた 0010。受入検証 D3）
    assert (r1.explicit, r1.dated_text, r1.inferred, r1.skipped_no_date) == (1, 5, 1, 0)
    n1 = _count(clean_db)
    assert n1 == 7
    r2 = run_facts("references", clean_db)
    assert (r2.explicit, r2.dated_text, r2.inferred) == (1, 5, 1)
    assert _count(clean_db) == n1  # 全削除→再挿入で行数不変
    assert _count(clean_db, "explicit") == 1 and _count(clean_db, "inferred") == 1


def test_recorded_at_fallback_and_v_verified(clean_db: str) -> None:
    from dbr.features.count import ask_view

    run(FIXTURES / "dated", "references", clean_db, log=lambda _m: None)
    r = run_facts("references", clean_db)
    assert r.recorded_from_valid == 2  # same-day.md（generated 無し）の 2 行
    conn = connect(clean_db)
    with conn, conn.cursor() as cur:
        cur.execute(
            "SELECT f.valid_from, f.recorded_at FROM fact f "
            "JOIN document d ON d.id = f.document_id WHERE d.rel_path = 'same-day.md'"
        )
        rows = cur.fetchall()
    assert len(rows) == 2 and all(r_["recorded_at"] == r_["valid_from"] for r_ in rows)
    assert ask_view("v_verified", clean_db) == [{"bundle": "references", "n": 1}]


def test_as_of_filters_by_time_and_history_is_ascending(clean_db: str) -> None:
    run(FIXTURES / "dated", "references", clean_db, log=lambda _m: None)
    run_facts("references", clean_db)
    mid = datetime(2026, 8, 15, 23, 59, 59, tzinfo=JST)
    hits = as_of("扶養 年収の壁", mid, dsn=clean_db)
    dates = {h.valid_from.date().isoformat() for h in hits}
    assert "2026-08-11" in dates and "2026-09-01" not in dates  # 未来の事実は返さない
    later = as_of("扶養 年収の壁", datetime(2026, 9, 30, tzinfo=JST), dsn=clean_db)
    assert "2026-09-01" in {h.valid_from.date().isoformat() for h in later}
    hist = history("扶養 年収の壁", dsn=clean_db)
    assert [h.valid_from for h in hist] == sorted(h.valid_from for h in hist)
    assert len(hist) >= 2 and all(h.valid_source == "dated_text" for h in hist)


def test_explicit_valid_window_and_inferred_are_queryable(clean_db: str) -> None:
    run(FIXTURES / "dated", "references", clean_db, log=lambda _m: None)
    run_facts("references", clean_db)
    # explicit の subject/value は description（「有効期間を持つ文書」）
    inside = as_of(
        "有効期間を持つ文書", datetime(2026, 10, 1, tzinfo=JST), dsn=clean_db
    )
    assert any(h.valid_source == "explicit" for h in inside)
    after = as_of("有効期間を持つ文書", datetime(2027, 6, 1, tzinfo=JST), dsn=clean_db)
    assert not any(
        h.valid_source == "explicit" for h in after
    )  # valid_to を過ぎたら出ない
    last_day = as_of(
        "有効期間を持つ文書",
        datetime(2027, 3, 31, 23, 59, 59, tzinfo=JST),
        dsn=clean_db,
    )
    assert any(h.valid_source == "explicit" for h in last_day)  # 最終日を含む
    inf = history("ただのメモ 日付", dsn=clean_db)
    assert any(h.valid_source == "inferred" for h in inf)
    assert as_of("", datetime(2026, 1, 1, tzinfo=JST), dsn=clean_db) == []
