---
type: Bench Results
description: 検索品質の測定結果（転記）。一次記録は bench/results/*.json。find 10 問×4方式の recall@5 / recall@20 / MRR と、測定中に見つけた方法論の欠陥（AND クエリ・同点の揺れ・HNSW 未使用）
generated: { by: kuroko/claude-fable-5-1, at: 2026-09-29T08:40:00+09:00 }
status: draft
---

# 検索品質の測定結果

> 一次記録: `bench/results/20260929-find.json`（確定値・2回実行で JSON 一致）、`bench/results/20260929-find-v1-and-query.json`（初回・欠陥あり）。本書は転記。
> 条件: model `intfloat/multilingual-e5-small`（ローカル・CPU・384 次元）／`sudachidict_core==20260723.1`／ef_search=40（ただし下記のとおり HNSW は未使用）／対象 `references`（16 文書・220 断片）＋`dev`（53 文書・857 断片）／質問 `docs/questions.md` の find 10 問／正解はファイル一致。

## 確定値（v3・2026-09-29）

| 方式 | recall@5 | recall@20 | MRR | 未ヒット（上位20に無し） |
|---|---|---|---|---|
| fts（全文・OR） | 0.40 | 0.70 | 0.327 | 3 |
| embed（埋め込みのみ） | 0.80 | 1.00 | 0.539 | 0 |
| hybrid（RRF: fts＋embed） | 0.70 | 0.80 | 0.542 | 2 |
| **hybrid_ctx（RRF: fts＋文脈付き埋め込み）** | 0.80 | 1.00 | **0.675** | 0 |

質問別の順位（- は上位 20 文書に無し）:

| # | fts | embed | hybrid | hybrid_ctx |
|---|---|---|---|---|
| Q01 | 1 | 4 | 2 | 1 |
| Q02 | 9 | 2 | 2 | 1 |
| Q03 | 2 | 1 | 1 | 1 |
| Q04 | 2 | 2 | 1 | 1 |
| Q05 | - | 2 | 6 | 4 |
| Q06 | - | 17 | - | 9 |
| Q07 | 20 | 1 | 4 | 3 |
| Q08 | - | 13 | - | 18 |
| Q09 | 1 | 2 | 1 | 1 |
| Q10 | 9 | 1 | 1 | 1 |

## 読み方（この 10 問・この規模での観察。一般化しない）
- **文脈付与は効いた**: MRR 0.539（embed）→ 0.675（hybrid_ctx）。Q01/Q02（「何を飲んでるんだっけ」「度数どこ」）が 4位・2位 → 1位。Anthropic の Contextual Retrieval と同じ方向
- **全文検索は単体では弱い**: 言い換え質問（Q06「目が悪くなってきた」→ 視力・メガネ、Q08「スキャナ的なこと」→ OCR）は語が一致せず未ヒット。埋め込みはこれを拾う
- **素朴な RRF は fts の雑音で埋め込みを悪化させることがある**: hybrid（plain）は embed 単体より recall@5 が下がった（0.80→0.70）。OR クエリの fts 候補 100 件が弱い一致を大量に持ち込み、RRF の等重みで割り込む。次単位で fts 側の重み／候補数を振る
- Q06・Q08 は全方式で弱い＝**言い換えの語彙差**。並べ直し（cross-encoder）で改善するかが次の測定点

## 測定中に見つけた方法論の欠陥（v1→v3 の経緯・一次記録は JSON 2 本）
| 版 | 何を変えたか | fts recall@5 | embed | hybrid_ctx MRR |
|---|---|---|---|---|
| v1 | `plainto_tsquery`（全語 AND）＋機能語も索引 | 0.20（未ヒット 8） | 0.80 | 0.794 |
| v2 | 語を OR で結合＋助詞・助動詞・記号を索引から除外 | 0.40 | 0.80 | 0.708 ※ |
| v3 | ベクトル検索の同点を `c.id` で固定（確定値） | 0.40 | 0.80 | 0.675 |

※ v2 の JSON は同日再実行で上書きされ**残っていない**（コンソール表の写し。受入検証の指摘）。v1 と v3 は JSON あり。

1. **AND クエリ**: 日本語の質問は助詞が必ず入るので、全語 AND では該当断片がほぼ無くなる（10 問中 8 問がヒット 0）。方式の欠陥であって「fts が弱い」ではない。修正後も fts 単体は 0.40 で、これが実力
2. **同点の揺れ**: v1→v2 で embed の順位が変わった（Q06 17→未ヒット）。原因は同一本文の断片（＝同一ベクトル）の同点順が `UPDATE chunk` 後のヒープ順に依存していたため。`ORDER BY 距離, c.id` で固定し、以後 2 回実行で JSON 一致
3. **HNSW は使われていない**: `EXPLAIN` で Seq Scan（厳密計算）。約 2,000 行では planner が索引を選ばない。したがって本測定の `ef_search=40` は無効で、ef_search の比較実験は `SET LOCAL enable_seqscan = off` で索引を強制してから行う（未実施）
4. hybrid_ctx の MRR が v1（0.794）より v3（0.675）で低いのは、v1 の fts が「ほぼ空」だったため RRF が実質 embed 単体＝雑音が無かったから。**fts を直したら融合が悪化した**という逆説。等重み RRF の限界として記録

## 次の測定点（次単位）
- 並べ直し（ローカル cross-encoder）で Q06/Q08 が上がるか
- RRF の重み・fts 候補数（100→20）で hybrid が embed を上回るか
- `enable_seqscan=off` で ef_search 40/100/250 の recall とレイテンシ
- 20 問全体（count/asof/overview）は各機能の実装後
