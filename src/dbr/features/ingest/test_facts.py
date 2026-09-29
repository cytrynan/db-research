from datetime import datetime

from dbr.features.ingest.facts import (
    DATE_VERB,
    extract_dated,
    extract_explicit,
    normalize_subject,
    parse_ymd,
)
from dbr.features.ingest.frontmatter import JST

NOW = datetime(2026, 9, 29, tzinfo=JST)


def test_date_verb_matches_heading_and_body_forms() -> None:
    assert DATE_VERB.search("収益目標（2026-07-26 K決定）")
    assert DATE_VERB.search("扶養・年収の壁（2026-08-11　分離）")  # 全角スペース
    assert DATE_VERB.search("2026-08-25 算出") and DATE_VERB.search("2026-08-24停止")
    assert not DATE_VERB.search("2026-08-11 に行った")  # 動詞なし
    assert DATE_VERB.search(
        "⛔2026-08-24 A枠の能動営業停止（受注0）"
    )  # 短い目的語を挟む
    assert not DATE_VERB.search(
        "2026-08-24 " + "x" * 25 + " 停止"
    )  # 20 字を超えたら拾わない
    assert not DATE_VERB.search("2026-08-24 途中\n停止")  # 行をまたがない
    assert parse_ymd("2026", "13", "40") is None  # 不正日付


def test_extract_dated_from_heading_and_lines_dedupes() -> None:
    rows = extract_dated(
        document_id=1,
        chunk_id=10,
        heading_path="A > 収益目標（2026-07-26 K決定）",
        body=(
            "- 候補は3つ（2026-08-11 K申告）\n"
            "- 候補は3つ（2026-08-11 K申告）\n- 日付なしの行\n"
        ),
        recorded_at=NOW,
    )
    dates = sorted(r.valid_from for r in rows)
    assert dates == [
        datetime(2026, 7, 26, tzinfo=JST),
        datetime(2026, 8, 11, tzinfo=JST),
    ]
    assert all(r.valid_source == "dated_text" and r.valid_to is None for r in rows)
    assert all(r.recorded_at == NOW for r in rows)
    assert len(rows) == 2  # 同じ行が 2 回あっても 1 件


def test_date_verb_window_stops_at_next_date() -> None:
    # 「08-01 に検討、08-11 決定」は 08-11 の決定だけ（受入検証 D3）
    line = "2026-08-01 に検討、2026-08-11 決定"
    assert [(m.group(3), m.group(4)) for m in DATE_VERB.finditer(line)] == [
        ("11", "決定")
    ]
    rows = extract_dated(
        document_id=1, chunk_id=1, heading_path="H", body=line, recorded_at=NOW
    )
    assert [r.valid_from for r in rows] == [datetime(2026, 8, 11, tzinfo=JST)]
    # 両方に動詞があれば両方拾う（1 行 2 事実）
    two = extract_dated(
        document_id=1,
        chunk_id=1,
        heading_path="H",
        body="2026-08-01 開始、2026-08-11 決定",
        recorded_at=NOW,
    )
    assert sorted(r.valid_from.day for r in two) == [1, 11]


def test_extract_dated_keeps_distinct_lines_with_same_heading_and_date() -> None:
    # 見出しが同じで日付＋動詞しか違わない 2 行は 2 件（subject で畳まない。D3）
    rows = extract_dated(
        document_id=1,
        chunk_id=1,
        heading_path="H",
        body="- 2026-08-11 決定\n- 2026-08-11 承認\n",
        recorded_at=NOW,
    )
    assert {r.value for r in rows} == {"- 2026-08-11 決定", "- 2026-08-11 承認"}


def test_recorded_at_falls_back_to_valid_from_when_no_generated() -> None:
    rows = extract_dated(
        document_id=1,
        chunk_id=1,
        heading_path="H",
        body="- 2026-08-11 決定",
        recorded_at=None,  # generated.at の無い文書
    )
    assert (
        rows[0].recorded_at == rows[0].valid_from == datetime(2026, 8, 11, tzinfo=JST)
    )
    ex = extract_explicit(
        document_id=1,
        fm={"valid": {"from": "2026-04-01"}},
        title="a.md",
        recorded_at=None,
    )
    assert ex is not None and ex.recorded_at == ex.valid_from


def test_normalize_subject_strips_date_and_verb() -> None:
    s = normalize_subject(
        "A > 収益目標（2026-07-26 K決定）", "- 候補は3つ（2026-08-11 K申告）"
    )
    assert "2026" not in s and "K申告" not in s and "K決定" not in s
    assert s.startswith("収益目標") and "候補は3つ" in s


def test_extract_explicit_from_valid_key() -> None:
    row = extract_explicit(
        document_id=1,
        fm={"description": "x", "valid": {"from": "2026-04-01", "to": "2027-03-31"}},
        title="a.md",
        recorded_at=NOW,
    )
    assert row is not None and row.valid_source == "explicit"
    assert row.valid_from == datetime(2026, 4, 1, tzinfo=JST)
    # 日付だけの to は最終日を含む＝排他的終端は翌日 0 時
    assert row.valid_to == datetime(2027, 4, 1, tzinfo=JST)
    with_time = extract_explicit(
        document_id=1,
        fm={"valid": {"from": "2026-04-01", "to": "2027-03-31T12:00:00+09:00"}},
        title="a.md",
        recorded_at=NOW,
    )
    assert with_time is not None
    assert with_time.valid_to == datetime(
        2027, 3, 31, 12, tzinfo=JST
    )  # 時刻つきはそのまま
    assert extract_explicit(document_id=1, fm={}, title="a.md", recorded_at=NOW) is None
    bad = extract_explicit(
        document_id=1, fm={"valid": {"from": "2026-04-01", "to": "2026-01-01"}},
        title="a.md", recorded_at=NOW,
    )  # fmt: skip
    assert bad is not None and bad.valid_to is None  # to <= from は捨てる
