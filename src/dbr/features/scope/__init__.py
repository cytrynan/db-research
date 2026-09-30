"""質問の語から対象 bundle を推定し、証拠を絞る（filter）か優先する（boost）.

④ 全体の証拠と ① 探し物の上位文書が全 bundle 横断で選ばれ、「生活の効率化」に dev/ の技術
文書が入る問題（v9c）への対処。語彙ルールで始める（埋め込みや LLM で推定しない）。
固有名詞（商品名・人名）と両義の語（「ツール」「設定」「計画」）は語彙に入れない。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import Literal, get_args

from dbr.features.search import Hit

ScopeMode = Literal["none", "filter", "boost"]
SCOPES: tuple[str, ...] = get_args(ScopeMode)
# D-16（2026-09-30・v10）: none 0.90/0.861 → filter・boost(0.5〜2.0) はすべて 1.00/0.883（Q08 9→3 位）、
# ④ の期待文書は Q19 1/4→2/4・Q20 0/1→1/1。同点なので**柔らかい boost** を既定にし、w は Q19 の
# 上位 5 が全部 references になる最小の 1.0。技術語→dev の枝は bench に質問が無く未測定
DEFAULT_SCOPE: str = "boost"
DEFAULT_BOOST: float = 1.0

# bundle → 語彙（先勝ちでなく全部当てて和集合）
LEXICON: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "references",
        re.compile(
            r"生活|暮らし|健康|体調|病院|薬|サプリ|花粉|視力|メガネ|目が|睡眠|運動|筋トレ|"
            r"食べ|飲ん|飲む|好み|好き|在庫|買い物|家に|家の|家事|部屋|持ち物|服|"
            r"バイト|給料|締め日|お金|収入|支出|貯金|扶養|年収|税|"
            r"就活|職種|仕事|キャリア|転職|資格|卒業|授業|大学|予定|習慣|趣味"
        ),
    ),
    (
        "dev",
        re.compile(
            r"実装|コード|テスト|バグ|エラー|ライブラリ|パッケージ|API|SQL|データベース|"
            r"Docker|git|コミット|フック|エージェント|プロンプト|埋め込み|Python|PowerShell|"
            r"サーバ|デプロイ|ビルド|CLI|リポジトリ|スキル|マイグレーション"
        ),
    ),
    (
        "memory",
        re.compile(
            r"方針|決めた|決定|案件|プロジェクト|進捗|再開|経緯|却下|保留|申し送り"
        ),
    ),
)


@dataclass(frozen=True)
class BundleGuess:
    bundles: list[str] | None  # None ＝ 全 bundle
    reason: str


def guess_bundles(question: str) -> BundleGuess:
    """質問の語から bundle を推定。当たった bundle の和集合。無ければ None（全 bundle）."""
    hits: list[tuple[str, str]] = []
    for bundle, rx in LEXICON:
        m = rx.search(question)
        if m:
            hits.append((bundle, m.group(0)))
    if not hits:
        return BundleGuess(None, "語彙に当たらない → 全 bundle")
    return BundleGuess([b for b, _ in hits], " / ".join(f"{b}←{w}" for b, w in hits))


def boost_by_bundle(
    docs: list[Hit], bundles: list[str] | None, w: float = DEFAULT_BOOST
) -> list[Hit]:
    """推定 bundle の文書スコアを (1+w) 倍して並べ直す（決定的・同点は元の順位）.

    bundles が None か w<=0 なら恒等。推定外の文書どうしの相対順位は変えない。
    """
    if not bundles or w <= 0:
        return list(docs)
    scaled = [
        replace(d, score=d.score * (1 + w)) if d.bundle in bundles else d for d in docs
    ]
    order = sorted(range(len(scaled)), key=lambda i: (-scaled[i].score, i))
    return [scaled[i] for i in order]


__all__ = [
    "DEFAULT_BOOST",
    "DEFAULT_SCOPE",
    "LEXICON",
    "SCOPES",
    "BundleGuess",
    "ScopeMode",
    "boost_by_bundle",
    "guess_bundles",
]
