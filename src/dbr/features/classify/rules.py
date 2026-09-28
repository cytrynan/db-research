"""語彙ルールの型判定（F2）。順序が仕様: count → asof → overview → find → unknown.

質問文の固有語（商品名・人名）はルールに入れない。
判定不能は unknown（find に倒さない）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

Kind = Literal["find", "count", "asof", "overview", "unknown"]

# (kind, 名前, 正規表現) を先勝ちで評価する
RULES: tuple[tuple[Kind, str, re.Pattern[str]], ...] = (
    (
        "count",
        "件数を問う語",
        re.compile(r"何件|いくつ|何個|何本|合計|件数|何ファイル|内訳"),
    ),
    (
        "asof",
        "時点・履歴を問う語",
        re.compile(r"いつ|時点|当時|以前|より前|履歴|過去に|前は|変わった|変更した"),
    ),
    (
        "overview",
        "全体・傾向を問う語",
        re.compile(r"全体として|全体的|傾向|手厚|薄い|どう反映|まとめると|俯瞰|偏り"),
    ),
    (
        "find",
        "所在・記録を問う語",
        re.compile(
            r"どこ|どれ|書いた|記録|メモ|ツール|計画|方針|好み|在庫|飲んで|"
            r"締め日|給料日|職種|資格|判定|型番|手順|だっけ|ある[？?]?$"
        ),
    ),
)


@dataclass(frozen=True)
class Classification:
    kind: Kind
    reason: str
    confidence: float


class RuleClassifier:
    def classify(self, question: str) -> Classification:
        q = question.strip()
        for kind, name, pattern in RULES:
            m = pattern.search(q)
            if m:
                return Classification(kind, f"{name}「{m.group(0)}」", 0.9)
        return Classification("unknown", "既知の語彙に当たらない", 0.0)
