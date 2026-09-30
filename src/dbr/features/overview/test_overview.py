from dbr.features.overview import (
    Narrative,
    OverviewAnswer,
    evidence_text,
    narrate,
    unsupported_mentions,
)
from dbr.shared.llm import get_llm

EV = (
    "【references】references: 文書 16 / 種別: Life Data 14 / 未確認 15\n"
    "- references/bar.md: bar.md: 健康の記録\n見出し: 視力, 体重\n種別: Life Data\n"
    "- references/baz.md: baz.md: 期限 2026-09-29 の取り決め（53 件）"
)


def test_unsupported_mentions_hand_cases() -> None:
    text = "bar.md と foo.md を見た。53 件と 123 件。2026-09-29 と 2026-01-01。8 件。"
    # foo.md は証拠に無い・123 と 2026-01-01 も無い。53・2026-09-29 は有る。1 桁は見ない
    assert unsupported_mentions(text, EV) == ["foo.md", "123", "2026-01-01"]
    assert unsupported_mentions("references/bar.md にある", EV) == []  # bundle 付きも可
    assert unsupported_mentions("一覧には見当たらない。", EV) == []
    assert unsupported_mentions("16 文書のうち 14 が Life Data", EV) == []


def test_evidence_text_and_fake_narrate_are_deterministic() -> None:
    a = OverviewAnswer(
        bundles=["references"],
        bundle_summaries=[
            {"id": 1, "bundle": "references", "text": "references: 文書 16\n- x"}
        ],
        doc_summaries=[
            {
                "id": 2,
                "doc": "references/bar.md",
                "text": "bar.md: 健康の記録",
                "score": 1.0,
            },
            {
                "id": 3,
                "doc": "references/baz.md",
                "text": "baz.md: 取り決め",
                "score": 0.5,
            },
        ],
    )
    ev = evidence_text(a)
    assert ev.splitlines()[0] == "【references】references: 文書 16"  # 先頭行だけ
    assert "- references/bar.md: bar.md: 健康の記録" in ev
    n1 = narrate("健康は？", a, get_llm("fake"))
    n2 = narrate("健康は？", a, get_llm("fake"))
    assert isinstance(n1, Narrative) and n1.text == n2.text and n1.model == "fake"
    assert n1.unsupported == [] and n1.seconds >= 0  # 証拠の切り貼りなので根拠外は無い
