"""質問の語から対象 bundle を推定し、証拠を絞る（filter）か優先する（boost）.

④ 全体の証拠と ① 探し物の上位文書が全 bundle 横断で選ばれ、「生活の効率化」に dev/ の技術
文書が入る問題（v9c）への対処。語彙ルールで始める（埋め込みや LLM で推定しない）。
個人データ側の固有名詞（持ち物の商品名・人名）と両義の語（「ツール」「設定」「計画」）は
語彙に入れない。技術の名前（Docker・git・Python 等）は実装語として dev に入れる。

既知の限界（受入検証 2026-10-03・D-16 に記載）: 照合は部分一致で大文字小文字を区別する
（「専門家の」→「家の」、「克服」→「服」、「2つ目が」→「目が」で references に誤推定。
「python」は当たらない）。語彙は bench の質問を見ながら作った（in-sample）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, Literal, get_args

from dbr.features.scope.defaults import DEFAULT_BOOST, DEFAULT_SCOPE

if TYPE_CHECKING:  # Hit は型注釈だけ。実行時に search（→ psycopg）を引き込まない
    from dbr.features.search import Hit

ScopeMode = Literal["none", "filter", "boost"]
SCOPES: tuple[str, ...] = get_args(ScopeMode)
# D-16（2026-09-30・v10）: none 0.90/0.861 → filter・boost(0.5〜2.0) はすべて 1.00/0.883（Q08 9→3 位）、
# ④ の期待文書は Q19 1/4→2/4・Q20 0/1→1/1。同点なので**柔らかい boost** を既定にし、w は Q19 の
# 上位 5 が全部 references になる最小の 1.0。技術語→dev の枝は bench に質問が無く未測定。
# 値そのものは defaults.py（CLI が search/psycopg を読まずに既定値だけ取れるように分けた）

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


def _lift(score: float, factor: float) -> float:
    # 負のスコア（cosine・並べ直し器のロジット）に factor を掛けると下がるので割る。
    # 単調増加・0 で連続＝持ち上げで**スコア**が下がることはない（受入検証 R2）
    return score * factor if score >= 0 else score / factor


def boost_by_bundle(
    docs: list[Hit], bundles: list[str] | None, w: float = DEFAULT_BOOST
) -> list[Hit]:
    """推定 bundle の文書スコアを (1+w) 倍に持ち上げ、推定内・推定外の 2 列を安定マージする.

    bundles が None か w<=0 なら恒等。決定的。入力の並びを順位として扱い、**推定内どうし・
    推定外どうしの相対順位は入力がスコア降順でなくても変えない**（並べ直し付きモード ×
    agg=max は別尺度のスコアが連結されるので、全体をスコアで並べ直すと推定外の順位まで
    壊れた＝受入検証 R2）。2 列の先頭どうしを比べ、持ち上げ後のスコアが大きい方を先に出す
    （同点は元の順位が上の方）。入力がスコア降順（既定の rrf_top3）なら「持ち上げてから
    スコア降順・同点は元の順位」と同じ結果になる。

    保証するのは「各列の相対順位」と「推定内のスコアは下がらない」まで。入力がスコア降順で
    ないときは、推定内の文書の**順位**が後ろの推定外の文書に抜かれて下がることがある
    （[dev 0.3, ref 0.05, dev 0.85] → ref は 2 位 → 3 位。別尺度のスコアを先頭どうしで
    比べるため。既定の経路では起きない・並べ直し付きモードでの効き方は未測定）。
    """
    if not bundles or w <= 0:
        return list(docs)
    factor = 1.0 + w
    target = set(bundles)
    inside = [
        (i, replace(d, score=_lift(d.score, factor)))
        for i, d in enumerate(docs)
        if d.bundle in target
    ]
    outside = [(i, d) for i, d in enumerate(docs) if d.bundle not in target]
    out: list[Hit] = []
    a = b = 0
    while a < len(inside) and b < len(outside):
        (ia, da), (ib, db) = inside[a], outside[b]
        if da.score > db.score or (da.score == db.score and ia < ib):
            out.append(da)
            a += 1
        else:
            out.append(db)
            b += 1
    out.extend(d for _, d in inside[a:])
    out.extend(d for _, d in outside[b:])
    return out


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
