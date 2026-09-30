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
