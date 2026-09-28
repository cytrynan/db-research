"""型判定のユニット: questions.md の 20 問（テスト内に写す）で ≥ 18/20、unknown 2 例."""

import pytest

from dbr.features.classify import RuleClassifier

# docs/questions.md（2026-09-29 版）の写し。正解ラベルは K 確認前の draft
QUESTIONS: list[tuple[str, str]] = [
    ("花粉症の薬とサプリ、何を飲んでるんだっけ", "find"),
    ("メガネの度数どこに書いた？", "find"),
    ("ネスプレッソのカプセル、好みと在庫は", "find"),
    ("バイトの締め日と給料日は", "find"),
    ("就活で候補にしている職種は", "find"),
    ("目が悪くなってきた気がする。前の記録どこ", "find"),
    ("深煎りが好きって書いたのどこだっけ", "find"),
    ("家にあるスキャナ的なことできるツールある？", "find"),
    ("卒業までに取る資格の計画", "find"),
    ("扶養で気にする年収ラインの、K の判定はどこ", "find"),
    ("references のファイルは全部で何件？", "count"),
    ("K が確認済み（verified）の記録は references に何件ある？", "count"),
    ("期限切れ（stale_after 超過）の記録はいくつ？", "count"),
    ("type が Life Data のファイルは何件？", "count"),
    ("扶養の制度知識を references から別ファイルに分けたのはいつ？", "asof"),
    ("キャリアの候補職種は、2026-08 より前の時点では何と書いてあった？", "asof"),
    ("収益目標を決めたのはいつで、当時の3枠は？", "asof"),
    ("2026-09 時点で、営業（受託）の能動活動は動いていた？", "asof"),
    ("生活の「効率化」方針は、全体としてどのファイルにどう反映されてる？", "overview"),
    ("K の健康まわりの記録、全体として何が手厚くて何が薄い？", "overview"),
]


def test_twenty_questions_at_least_18_correct() -> None:
    c = RuleClassifier()
    results = [(q, k, c.classify(q).kind) for q, k in QUESTIONS]
    correct = sum(1 for _, k, got in results if k == got)
    wrong = [(q, k, got) for q, k, got in results if k != got]
    assert correct >= 18, wrong


def test_lookalike_words_do_not_trigger_other_kinds() -> None:
    c = RuleClassifier()
    # 「いつも」は asof でなく、「いくつか」は count でない（2026-09-29 受入検証の指摘）
    assert c.classify("いつも飲んでるサプリどこに書いた？").kind == "find"
    assert c.classify("いくつか候補は？").kind == "unknown"


@pytest.mark.parametrize("q", ["ありがとう", "今日は暑いね", "時間ある？", "何だっけ"])
def test_unknown_is_not_forced_to_find(q: str) -> None:
    r = RuleClassifier().classify(q)
    assert r.kind == "unknown"
    assert r.confidence == 0.0


def test_reason_names_the_matched_word() -> None:
    r = RuleClassifier().classify("全部で何件？")
    assert r.kind == "count" and "何件" in r.reason
