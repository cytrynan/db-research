"""bench のユニット: 表パース・指標の手計算・Markdown 生成."""

import math
from pathlib import Path

from dbr.features.bench.metrics import mrr, rank_of, recall_at
from dbr.features.bench.questions import load_questions, parse_row
from dbr.features.bench.report import to_markdown


def test_parse_row_extracts_backticked_paths_only() -> None:
    q = parse_row(
        "| Q10 | 扶養の判定はどこ | find | `references/fuyou.md`"
        "（制度は tax/nenshu-kabe-seido.md で別） | 備考 |"
    )
    assert q is not None
    assert q.id == "Q10" and q.kind == "find"
    assert q.expected == ("references/fuyou.md",)


def test_parse_row_multiple_paths_and_non_rows() -> None:
    q = parse_row(
        "| Q03 | x | find | `references/preferences.md`＋`references/home.md` §在庫 | |"
    )
    assert q is not None and q.expected == (
        "references/preferences.md",
        "references/home.md",
    )
    assert parse_row("| # | 質問 | 型 | 期待 | 備考 |") is None
    assert parse_row("普通の文") is None


def test_load_questions_from_file(tmp_path: Path) -> None:
    p = tmp_path / "q.md"
    p.write_text(
        "| # | 質問 | 型 | 期待 | 備考 |\n|---|---|---|---|---|\n"
        "| Q01 | a | find | `dev/a.md` | |\n| Q02 | b | count | v_by_bundle | |\n",
        encoding="utf-8",
    )
    qs = load_questions(p)
    assert [q.id for q in qs] == ["Q01", "Q02"]
    assert qs[1].expected == ()


def test_metrics_hand_calculation() -> None:
    ranks = [1, 3, None, 7]
    assert math.isclose(recall_at(ranks, 5), 2 / 4)
    assert math.isclose(recall_at(ranks, 20), 3 / 4)
    assert math.isclose(mrr(ranks), (1 + 1 / 3 + 1 / 7) / 4)
    assert recall_at([], 5) == 0.0 and mrr([]) == 0.0


def test_rank_of_first_matching_expected() -> None:
    assert rank_of(["dev/a.md", "dev/b.md"], ["dev/x.md", "dev/b.md", "dev/a.md"]) == 2
    assert rank_of(["dev/a.md"], ["dev/x.md"]) is None


def test_to_markdown_has_summary_and_per_question_rows() -> None:
    result = {
        "date": "2026-09-29",
        "git_sha": "abc1234",
        "model": "fake",
        "sudachi_dict": "sudachidict_core==x",
        "ef_search": 40,
        "question_count": 2,
        "modes": {
            "fts": {
                "recall@5": 0.5,
                "recall@20": 1.0,
                "mrr": 0.55,
                "per_question": [{"id": "Q01", "rank": 1}, {"id": "Q02", "rank": 9}],
            }
        },
    }
    md = to_markdown(result)
    assert "| fts | 0.50 | 1.00 | 0.550 | 0 |" in md
    assert "| Q02 | 9 |" in md
