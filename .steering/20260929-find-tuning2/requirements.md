# 要求内容（brief）

> 厚さ: **T2**（永続スキーマ・課金・外部 API に触れない。仕様はこちらで決めるので受入基準と非スコープを付ける）。design.md は書かず、設計は本書の「やること」に内包する。

## 目的（brief）
① 探し物の最良は embed_ctx 単体（recall@5 0.90 / MRR 0.811・v5）。取りこぼしは Q08（言い換え「スキャナ的なこと」→ tools.md の OCR/PDF、順位 9）、順位 2 が Q04・Q09。一方 hybrid_ctx_rerank は Q08 を 4 位に上げるが、全文検索の候補ノイズで Q02（5 位）・Q06（18 位）を落とす。**並べ直しを「文脈付き埋め込みの候補だけ」に当てる**方式と、**断片→文書の集約**（最良断片だけでなく、同じ文書の複数断片の順位を足す）で、v5 の天井を超えるかを測る。

## やること
1. **モード `embed_ctx_rerank`**: `vector_search(ctx, limit=max(rerank_top, k))` → cross-encoder で上位 `rerank_top` を並べ直し → k 件。`ask --mode embed_ctx_rerank`／`bench --kind find` で使える。reranker の読み込み条件は「mode が `_rerank` で終わる」に一般化
2. **文書集約 `aggregate_by_document(hits, method)`**（順位ベース・モード非依存・決定的）:
   - `max`: 最良断片の順位（現行 `dedupe_by_document` と同値。別名として残す）
   - `rrf_all`: 文書スコア＝Σ_{その文書の全断片} 1/(60+断片順位)
   - `rrf_top3`: 同じ和を文書ごとの上位 3 断片まで
   - 同点は最良断片の順位が小さい方を先に。返す Hit は代表＝最良断片で、score は文書スコア
3. **bench `--kind tune`**: mode ∈ {embed_ctx, embed_ctx_rerank} × rerank_top ∈ {20, 50, 100, 150}（embed_ctx は 1 セル） × agg ∈ {max, rrf_all, rrf_top3}。検索は (mode, rerank_top) ごとに 1 回だけ行い、集約 3 種は同じ結果に後処理で当てる。JSON にセルごとの recall@5 / recall@20 / MRR と質問別順位。Markdown は「行＝mode/rerank_top・列＝agg」の表
4. `ask` の find 分岐に `--agg`（既定 max）
5. 実データ（references＋dev＋memory）で `bench --kind find --modes embed_ctx,embed_ctx_rerank,hybrid_ctx_rerank --label v8` と `bench --kind tune --label v8` → `docs/bench-results.md` v8 節に転記。**既定を変えるかは数値で決め、`docs/decisions.md` に D-14 として記録**（変えない結論もその理由とともに記録）

## 受入基準（correctness）
- [ ] `aggregate_by_document` の 3 方式が手計算どおり（ユニット: A=順位 1 のみ、B=順位 2,3,4 → `max` は A 先、`rrf_all`/`rrf_top3` は B 先。B に順位 5,6 も足すと `rrf_all` だけ B のスコアが増える）。同点は最良断片順位で安定。`dedupe_by_document(h) == aggregate_by_document(h, "max")`
- [ ] `search(mode="embed_ctx_rerank")` は k 件を返し、先頭 `rerank_top` 件は `source == "rerank"`、全文検索を呼ばない（統合: fake embedder＋fake reranker。fts の語が一致しない質問でも埋め込みの候補が返る）
- [ ] `bench --kind tune` が JSON（15 セル・各セルに per_question の rank）と Markdown を出す。`--kind find` に `embed_ctx_rerank` を含めても exit 0（統合: fake）
- [ ] 実データ v8 が `bench/results/` にあり、bench-results v8 節と D-14 が JSON の数値と一致する
- [ ] `bash scripts/gate.sh` が exit 0（ruff / mypy / pytest・カバレッジ 80%）

## 非スコープ
- 質問セットの追加・変更（20 問は固定。語彙一致が効く質問の追加は K に提案するに留める）
- HNSW・ef_search の再測定、埋め込みモデルの変更、LLM 要約、外部 API
- 並べ直し器の変更（`cross-encoder/mmarco-mMiniLMv2-L12-H384-v1` のまま）

## 識別子契約
- 前単位の契約を継承。追加: `agg` の値は固定語彙 3 つ（`AGGS`）で、語彙外は `ValueError`／CLI は exit 2。ユーザー入力を SQL に連結しない（集約は Python 側の後処理）
