from dbr.features.scope import SCOPES, boost_by_bundle, guess_bundles
from dbr.features.search import Hit


def _h(cid: int, bundle: str, rel: str, score: float) -> Hit:
    return Hit(cid, bundle, rel, "h", "b", score, "embed")


def test_guess_bundles_hand_cases() -> None:
    assert guess_bundles("花粉症の薬とサプリ、何を飲んでるんだっけ").bundles == [
        "references"
    ]
    assert guess_bundles(
        "生活の「効率化」方針は、全体としてどのファイルにどう反映されてる？"
    ).bundles == [
        "references",
        "memory",
    ]  # 生活 → references、方針 → memory（和集合・語彙順）
    assert guess_bundles("フックのテストが落ちる").bundles == ["dev"]
    g = guess_bundles("今日の天気は？")
    assert g.bundles is None and "全 bundle" in g.reason
    # 両義の語は入れていない（ツール／設定／計画 だけでは決めない）
    assert guess_bundles("ツールの設定と計画").bundles is None
    assert "references←薬" in guess_bundles("薬").reason


def test_boost_is_deterministic_identity_and_order_preserving() -> None:
    docs = [
        _h(1, "dev", "a.md", 0.05),
        _h(2, "references", "b.md", 0.04),
        _h(3, "memory", "c.md", 0.03),
        _h(4, "references", "d.md", 0.02),
    ]
    assert (
        boost_by_bundle(docs, None) == docs
        and boost_by_bundle(docs, ["dev"], 0) == docs
    )
    out = boost_by_bundle(docs, ["references"], 1.0)
    # b: 0.08, a: 0.05, d: 0.04, c: 0.03 → 推定外（a, c）の相対順位は不変
    assert [d.rel_path for d in out] == ["b.md", "a.md", "d.md", "c.md"]
    assert out[0].score == 0.08 and out[1].score == 0.05
    assert boost_by_bundle(docs, ["references"], 1.0) == out  # 同入力同出力
    # 同点は元の順位
    tie = [_h(1, "dev", "x.md", 0.04), _h(2, "references", "y.md", 0.02)]
    assert [d.rel_path for d in boost_by_bundle(tie, ["references"], 1.0)] == [
        "x.md",
        "y.md",
    ]
    assert SCOPES == ("none", "filter", "boost")


def test_boost_keeps_group_order_on_unsorted_input_and_never_lowers() -> None:
    """受入検証 R2: 並べ直し × agg=max はスコア降順でない列が来る。各群の相対順位は不変."""
    docs = [
        _h(1, "dev", "P.md", 0.2),
        _h(2, "dev", "Q.md", 0.9),
        _h(3, "references", "R.md", 0.1),
    ]
    out = boost_by_bundle(docs, ["references"], 1.0)
    # R は 0.2 に上がるが P（0.2・元の順位が上）と同点 → P, Q, R。P/Q は入れ替えない
    assert [d.rel_path for d in out] == ["P.md", "Q.md", "R.md"]
    assert out[2].score == 0.2
    # 負のスコア（cosine・ロジット）: 掛けると下がるので割る。B は C より上のまま
    neg = [
        _h(1, "dev", "A.md", 0.1),
        _h(2, "references", "B.md", -0.02),
        _h(3, "dev", "C.md", -0.03),
    ]
    out = boost_by_bundle(neg, ["references"], 1.0)
    assert [d.rel_path for d in out] == ["A.md", "B.md", "C.md"]
    assert out[1].score == -0.01
    assert boost_by_bundle([], ["references"], 1.0) == []


def _old_boost(docs: list[Hit], bundles: list[str], w: float) -> list[Hit]:
    """478f16e までの実装（全体をスコアで並べ直す）。差分ファジングの比較元."""
    from dataclasses import replace

    scaled = [
        replace(d, score=d.score * (1 + w)) if d.bundle in bundles else d for d in docs
    ]
    order = sorted(range(len(scaled)), key=lambda i: (-scaled[i].score, i))
    return [scaled[i] for i in order]


def test_boost_differential_fuzz_and_group_order_property() -> None:
    import random

    rng = random.Random(20261003)
    bundles_all = ["references", "dev", "memory"]
    for _ in range(500):
        n = rng.randint(0, 12)
        w = rng.choice([0.5, 1.0, 2.0])
        target = rng.sample(bundles_all, rng.randint(1, 2))
        # 同点を作るためスコアは粗い格子から引く
        raw = [
            _h(i, rng.choice(bundles_all), f"{i}.md", rng.randint(0, 8) / 8)
            for i in range(n)
        ]
        # 1) 非負・降順の入力（既定 rrf_top3 の形）では旧実装と同じ結果＝v10 の測定は不変
        desc = sorted(raw, key=lambda d: -d.score)
        assert boost_by_bundle(desc, target, w) == _old_boost(desc, target, w)
        # 2) 任意の並び・負を含むスコアでも、各群の相対順位は入力のまま・決定的
        anyo = [
            _h(d.chunk_id, d.bundle, d.rel_path, d.score - rng.choice([0.0, 0.5]))
            for d in raw
        ]
        out = boost_by_bundle(anyo, target, w)
        assert boost_by_bundle(anyo, target, w) == out
        for inside in (True, False):
            want = [d.rel_path for d in anyo if (d.bundle in target) == inside]
            got = [d.rel_path for d in out if (d.bundle in target) == inside]
            assert got == want
        before = {d.rel_path: d.score for d in anyo}
        for d in out:  # 推定内は下がらない・推定外はスコア不変
            if d.bundle in target:
                assert d.score >= before[d.rel_path]
            else:
                assert d.score == before[d.rel_path]
