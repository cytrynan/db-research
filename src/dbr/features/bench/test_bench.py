"""bench のユニット: 表パース・指標の手計算・Markdown 生成."""

import math
from pathlib import Path

import pytest

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


def test_sweep_grid_and_markdown() -> None:
    from dbr.features.bench.sweep import grid, sweep_markdown

    g = grid((0.0, 1.0), (20, 100))
    assert g == [(0.0, 20), (0.0, 100), (1.0, 20), (1.0, 100)]
    result = {
        "date": "2026-09-29",
        "git_sha": "abc",
        "mode": "hybrid_ctx",
        "question_count": 2,
        "cells": [
            {"w_fts": w, "candidates": c, "recall@5": 0.5, "recall@20": 1.0, "mrr": 0.6}
            for w, c in g
        ],
        "best": {"w_fts": 1.0, "candidates": 100},
    }
    md = sweep_markdown(result)
    assert "| w_fts \\ candidates | 20 | 100 |" in md
    assert "| 0.0 | 0.50 / 1.00 / 0.600 | 0.50 / 1.00 / 0.600 |" in md
    assert "w_fts=1.0, candidates=100" in md


def test_hnsw_overlap_and_markdown() -> None:
    from dbr.features.bench.hnsw import hnsw_markdown, overlap_at_k

    assert overlap_at_k([1, 2, 3, 4], [1, 2, 9, 8], 4) == 0.5
    assert overlap_at_k([1, 2], [1, 2], 2) == 1.0
    assert overlap_at_k([], [1], 1) == 0.0
    assert (
        overlap_at_k([1, 2, 3], [1, 2, 3], 5) == 1.0
    )  # 厳密が k 件未満なら分母はその件数
    assert overlap_at_k([1], [], 5) == 0.0
    with pytest.raises(ValueError):
        overlap_at_k([1], [1], 0)
    result = {
        "date": "2026-09-29",
        "git_sha": "abc",
        "model": "fake",
        "variant": "plain",
        "k": 20,
        "repeats": 3,
        "question_count": 10,
        "exact": {"latency_ms_median": 12.34},
        "index_used_when_forced": True,
        "ef": [
            {"ef_search": 40, "recall@20_vs_exact": 0.95, "latency_ms_median": 3.21}
        ],
    }
    md = hnsw_markdown(result)
    assert "12.3 ms" in md and "| 40 | 0.950 | 3.2 |" in md and "True" in md


def test_result_path_label_rules(tmp_path: Path) -> None:
    from dbr.features.bench.report import result_path, save_json

    plain = result_path(tmp_path, "find")
    labeled = result_path(tmp_path, "find", "v5")
    assert plain.name.endswith("-find.json") and labeled.name.endswith("-find-v5.json")
    assert plain != labeled
    for bad in ["", "a/b", "..", "日本語", "x" * 33, "v 5", "v5\n", "x" * 32 + "\n"]:
        with pytest.raises(ValueError):
            result_path(tmp_path, "find", bad)
    p = save_json({"a": 1}, tmp_path, "find", "v5")
    assert p.exists() and not plain.exists()  # ラベル付きは既存を上書きしない
